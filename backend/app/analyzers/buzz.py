"""Wikipedia Pageviews 기반 버즈 분석 모듈 (BuzzAnalyzer).

소셜 감성 분석 대신 "관심 증가의 흔적"을 간접 측정.
Wikipedia 공식 REST API 사용 — 인증 불필요, 레이트 리밋 없음.

측정 방식:
  - 최근 7일 평균 조회수 vs. 직전 21일 평균 조회수 비율
  - ratio > 1 = 관심 증가, < 1 = 감소
  - 절대 조회수가 매우 낮으면 confidence 하향 (노이즈 처리)

API 엔드포인트:
  Wikipedia search: en.wikipedia.org/w/api.php
  Pageviews:        wikimedia.org/api/rest_v1/metrics/pageviews/...
"""

import logging
from datetime import datetime, timedelta, timezone
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
            company_name = info.get("company") or ticker
        except Exception:
            company_name = ticker

        title = self._find_wiki_title(company_name)
        if not title:
            return AnalyzerResult(
                score=0.0, signal="hold",
                evidence={"note": "Wikipedia 페이지 없음"},
                confidence=0.0, timestamp=self.now_utc(),
            )

        views = self._get_pageviews(title)
        if len(views) < 14:
            return AnalyzerResult(
                score=0.0, signal="hold",
                evidence={"wiki_title": title, "note": "조회수 데이터 부족"},
                confidence=0.0, timestamp=self.now_utc(),
            )

        recent_7  = sum(views[-7:]) / 7
        prev_21   = sum(views[:-7]) / max(1, len(views) - 7)
        ratio     = recent_7 / max(1, prev_21)

        # score: ratio=1(중립)→50, ratio=2→100, ratio=0.5→25
        score = round(min(100.0, max(0.0, 50.0 * ratio)), 2)

        # confidence: 절대 조회수 기준 (너무 낮으면 노이즈)
        avg_views = (recent_7 + prev_21) / 2
        if avg_views >= 500:
            confidence = 0.8
        elif avg_views >= 50:
            confidence = 0.6
        elif avg_views >= 5:
            confidence = 0.4
        else:
            confidence = 0.0

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "wiki_title": title,
                "recent_7d_avg": round(recent_7, 1),
                "prev_21d_avg": round(prev_21, 1),
                "view_ratio": round(ratio, 3),
                "days_collected": len(views),
            },
            confidence=confidence,
            timestamp=self.now_utc(),
        )

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
        """최근 28일 일별 페이지뷰 리스트 반환."""
        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=28)
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
