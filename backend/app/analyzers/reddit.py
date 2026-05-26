"""Reddit 소셜 센티먼트 분석 모듈.

데이터: Reddit 공개 JSON API (인증 불필요)
시그널 로직:
  - 최근 7일 언급 포스트 수 → 화제성 (0~50)
  - 총 업보트 합산 → 실제 관심 규모 (0~50)
요청: User-Agent 헤더 필수, 서브레딧 간 1초 간격
"""

import logging
import math
import time
from datetime import datetime, timezone

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_SEARCH_WINDOW_DAYS = 7
_SUBREDDITS = ["stocks", "investing", "wallstreetbets", "StockMarket"]
_USER_AGENT = "tenbagger-scoring/1.0 (data collection bot)"
_TIMEOUT = 10


class RedditAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "reddit"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("RedditAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        posts = _collect_posts(ticker)

        post_count = len(posts)
        total_upvotes = sum(p.get("score", 0) for p in posts if p.get("score", 0) > 0)

        # 포스트 수 점수 (0~50): 10개 이상 만점
        post_score = min(50.0, post_count * 5.0)

        # 업보트 점수 (0~50): log10 스케일, 10,000 업보트 이상 만점
        upvote_score = min(50.0, math.log10(total_upvotes + 1) * 12.5) if total_upvotes > 0 else 0.0

        score = round(post_score + upvote_score, 2)
        confidence = 0.85 if post_count >= 5 else (0.6 if post_count >= 1 else 0.3)

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "post_count_7d": post_count,
                "total_upvotes_7d": total_upvotes,
                "avg_upvotes": round(total_upvotes / post_count, 0) if post_count else 0,
                "post_score": round(post_score, 2),
                "upvote_score": round(upvote_score, 2),
            },
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


def _collect_posts(ticker: str) -> list[dict]:
    headers = {"User-Agent": _USER_AGENT}
    cutoff = time.time() - _SEARCH_WINDOW_DAYS * 86400
    posts = []

    for subreddit in _SUBREDDITS:
        try:
            batch = _fetch_subreddit(ticker, subreddit, headers, cutoff)
            posts.extend(batch)
            time.sleep(1)
        except Exception as e:
            log.warning("Reddit fetch error [r/%s, %s]: %s", subreddit, ticker, e)

    return posts


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=5, max=30),
)
def _fetch_subreddit(ticker: str, subreddit: str, headers: dict, cutoff: float) -> list[dict]:
    resp = requests.get(
        f"https://www.reddit.com/r/{subreddit}/search.json",
        params={"q": ticker, "restrict_sr": "1", "sort": "new", "t": "week", "limit": 25},
        headers=headers,
        timeout=_TIMEOUT,
    )
    if resp.status_code == 429:
        raise requests.RequestException(f"rate limited on r/{subreddit}")
    resp.raise_for_status()

    return [
        child["data"]
        for child in resp.json().get("data", {}).get("children", [])
        if child.get("data", {}).get("created_utc", 0) >= cutoff
    ]


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
