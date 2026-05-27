"""Reddit 소셜 센티먼트 분석 모듈.

우선순위:
  1. PRAW OAuth (REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET 환경변수) — 공식 API, IP 차단 우회
  2. 공개 JSON API fallback — 서버 IP 차단 시 confidence=0 반환

시그널 로직:
  - 최근 7일 언급 포스트 수 → 화제성 (0~50)
  - 총 업보트 합산 → 실제 관심 규모 (0~50)
"""

import logging
import math
import os
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


class _RedditIPBlocked(Exception):
    """서버 IP 차단 감지 — confidence=0으로 모듈 제외."""


def _get_praw_client():
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    try:
        import praw
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=_USER_AGENT,
        )
    except Exception as e:
        log.warning("PRAW init failed: %s", e)
        return None


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
        reddit = _get_praw_client()
        if reddit:
            posts = _collect_posts_praw(reddit, ticker)
            method = "praw"
        else:
            try:
                posts = _collect_posts_public(ticker)
            except _RedditIPBlocked:
                return AnalyzerResult(
                    score=0.0,
                    signal="hold",
                    evidence={"error": "ip_blocked", "method": "public"},
                    confidence=0.0,
                    timestamp=datetime.now(timezone.utc),
                )
            method = "public"

        post_count = len(posts)
        total_upvotes = sum(p.get("score", 0) for p in posts if p.get("score", 0) > 0)

        post_score = min(50.0, post_count * 5.0)
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
                "method": method,
            },
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


def _collect_posts_praw(reddit, ticker: str) -> list[dict]:
    """PRAW 공식 API — rate limit 관대, IP 차단 없음."""
    cutoff = time.time() - _SEARCH_WINDOW_DAYS * 86400
    posts = []
    for subreddit in _SUBREDDITS:
        try:
            results = reddit.subreddit(subreddit).search(
                ticker, sort="new", time_filter="week", limit=25
            )
            for sub in results:
                if sub.created_utc >= cutoff:
                    posts.append({"score": sub.score, "created_utc": sub.created_utc})
            time.sleep(0.5)
        except Exception as e:
            log.warning("PRAW fetch error [r/%s, %s]: %s", subreddit, ticker, e)
    return posts


def _collect_posts_public(ticker: str) -> list[dict]:
    """공개 JSON API fallback — 서버 IP 차단 시 fast-fail."""
    headers = {"User-Agent": _USER_AGENT}
    cutoff = time.time() - _SEARCH_WINDOW_DAYS * 86400
    posts = []
    consecutive_fails = 0

    for subreddit in _SUBREDDITS:
        try:
            batch = _fetch_subreddit_public(ticker, subreddit, headers, cutoff)
            posts.extend(batch)
            consecutive_fails = 0
            time.sleep(1)
        except Exception as e:
            log.warning("Reddit public fetch error [r/%s, %s]: %s", subreddit, ticker, e)
            consecutive_fails += 1
            if consecutive_fails >= 2:
                log.warning("Reddit IP block detected for %s — skipping remaining", ticker)
                raise _RedditIPBlocked(ticker)

    return posts


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=2, max=8),
)
def _fetch_subreddit_public(ticker: str, subreddit: str, headers: dict, cutoff: float) -> list[dict]:
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
