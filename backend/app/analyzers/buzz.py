"""Wikipedia Pageviews + Yahoo Finance 뉴스량 기반 버즈 분석 모듈 (BuzzAnalyzer).

소셜 감성 분석 대신 "관심 증가의 흔적"을 간접 측정.
  - Wikipedia 공식 REST API: 90일 데이터, 30일 단위 MoM 비율 + 3개월 연속 상승 탐지
  - Yahoo Finance RSS: 최근 30일 뉴스 건수
  - 블렌딩: 위키 70% + 뉴스 30%

API 엔드포인트:
  Wikipedia search: en.wikipedia.org/w/api.php
  Pageviews:        wikimedia.org/api/rest_v1/metrics/pageviews/...
  Yahoo RSS:        feeds.finance.yahoo.com/rss/2.0/headline
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_TIMEOUT = 10
_USER_AGENT = "TenbaggerScoring/1.0 (https://github.com/nvidiabigfan/tenbagger-scoring; ohone4194@gmail.com)"
_WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
_WIKI_PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/{start}/{end}"


class BuzzAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "buzz"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("BuzzAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0, signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        # 회사명 조회 (Finviz) → Wikipedia 정확도 향상
        from app.core.finviz import get_stock_info
        try:
            info = get_stock_info(ticker)
            company_name = info.get("company_name") or ticker
        except Exception:
            company_name = ticker

        title = self._find_wiki_title(company_name)
        if not title:
            return AnalyzerResult(
                score=0.0, signal="hold",
                evidence={"note": "Wikipedia 페이지 없음"},
                confidence=0.0, timestamp=self.now_utc(),
            )

        views = self._get_pageviews(title)   # 90일치
        if len(views) < 30:
            return AnalyzerResult(
                score=0.0, signal="hold",
                evidence={"wiki_title": title, "note": "조회수 데이터 부족"},
                confidence=0.0, timestamp=self.now_utc(),
            )

        n = len(views)
        m1_avg = sum(views[-30:]) / 30                                              # 최근 30일
        m2_avg = sum(views[-60:-30]) / 30 if n >= 60 else sum(views[:-30]) / max(1, n - 30)  # 직전 30일
        m3_avg = sum(views[-90:-60]) / 30 if n >= 85 else None                     # 2개월 전 (API 지연 허용)

        # MoM 비율: recent_30d / prior_30d
        mom_ratio = m1_avg / max(1.0, m2_avg)

        # Wikipedia score: ratio=1(보합)→50, ratio=2(2배)→100, ratio=0.5(반감)→25
        wiki_score = min(100.0, max(0.0, 50.0 * mom_ratio))

        # 3개월 연속 상승 보너스 (+10점)
        consecutive_growth = (m3_avg is not None) and (m1_avg > m2_avg > m3_avg)
        if consecutive_growth:
            wiki_score = min(100.0, wiki_score + 10.0)

        # Yahoo Finance 뉴스량 보강 (30일 윈도우)
        news_score, news_count, news_ok = self._get_news_score(ticker)

        # 블렌딩: 위키 70% + 뉴스 30% (뉴스 성공 시)
        if news_ok:
            score = round(wiki_score * 0.7 + news_score * 0.3, 2)
        else:
            score = round(wiki_score, 2)

        # confidence: 30일 일평균 조회수 기준
        daily_avg = (m1_avg + m2_avg) / 2
        if daily_avg >= 500:
            confidence = 0.85
        elif daily_avg >= 50:
            confidence = 0.7
        elif daily_avg >= 5:
            confidence = 0.4
        else:
            confidence = 0.0

        evidence = {
            "wiki_title": title,
            "recent_30d_avg": round(m1_avg, 1),
            "prev_30d_avg": round(m2_avg, 1),
            "m3_30d_avg": round(m3_avg, 1) if m3_avg is not None else None,
            "mom_ratio": round(mom_ratio, 3),
            "consecutive_growth_3m": consecutive_growth,
            "days_collected": n,
            "news_count_30d": news_count if news_ok else None,
        }

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence=evidence,
            confidence=confidence,
            timestamp=self.now_utc(),
        )

    def _get_news_score(self, ticker: str) -> tuple[float, int, bool]:
        """Yahoo Finance RSS — 최근 30일 뉴스 건수 기반 점수. (score, count, success)"""
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            headers = {"User-Agent": _USER_AGENT}
            with httpx.Client(timeout=8, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return 0.0, 0, False
            root = ET.fromstring(resp.text)
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            count = 0
            for item in root.findall(".//item"):
                pub_raw = item.findtext("pubDate", "")
                try:
                    pub_dt = parsedate_to_datetime(pub_raw)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    if pub_dt >= cutoff:
                        count += 1
                except Exception:
                    count += 1
            # 0건→0, 20건→50, 40건→100 (월 단위 스케일)
            score = min(100.0, count * 2.5)
            return score, count, True
        except Exception as e:
            log.debug("BuzzAnalyzer news fetch [%s]: %s", ticker, e)
            return 0.0, 0, False

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(2),
        wait=wait_fixed(3),
        reraise=True,
    )
    def _find_wiki_title(self, query: str) -> str | None:
        """회사명 → Wikipedia 문서 제목. 없으면 None."""
        headers = {"User-Agent": _USER_AGENT}
        with httpx.Client(timeout=_TIMEOUT, headers=headers) as client:
            resp = client.get(
                _WIKI_SEARCH,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": 3,
                },
            )
            resp.raise_for_status()
            results = resp.json().get("query", {}).get("search", [])

        for r in results:
            title = r.get("title", "")
            snippet = r.get("snippet", "").lower()
            if any(kw in snippet for kw in ("company", "corporation", "inc.", "founded", "nasdaq", "nyse", "products")):
                return title
        return results[0]["title"] if results else None

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(2),
        wait=wait_fixed(3),
        reraise=True,
    )
    def _get_pageviews(self, title: str) -> list[int]:
        """최근 90일 일별 페이지뷰 리스트 반환."""
        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=90)
        url = _WIKI_PV.format(
            title=quote(title, safe=""),
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
        )
        headers = {"User-Agent": _USER_AGENT}
        with httpx.Client(timeout=_TIMEOUT, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])
        return [item.get("views", 0) for item in items]


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
