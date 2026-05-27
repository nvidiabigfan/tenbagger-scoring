"""Reddit 소셜 데이터 수집 배치.

GitHub Actions에서 실행 — 공개 JSON API 사용.
Actions는 매 실행마다 새 IP이므로 서버 IP 차단 우회 가능.
수집 결과는 reddit_snapshots 테이블에 저장.
백엔드 RedditAnalyzer는 이 테이블을 읽어 스코어 계산.

실행: python -m app.jobs.reddit_batch
"""

import logging
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_SUBREDDITS = ["stocks", "investing", "wallstreetbets", "StockMarket"]
_USER_AGENT = "tenbagger-scoring/1.0 (data collection bot)"
_TIMEOUT = 10
_INTER_SUBREDDIT_SLEEP = 1.0
_INTER_TICKER_SLEEP = 1.0
_SEARCH_WINDOW_DAYS = 7

REDDIT_BATCH_MAX = int(os.getenv("REDDIT_BATCH_MAX", "200"))


def _get_active_tickers(client) -> list[str]:
    res = (
        client.table("stocks")
        .select("ticker, market_cap")
        .eq("is_active", True)
        .order("market_cap", desc=True, nullsfirst=False)
        .limit(REDDIT_BATCH_MAX)
        .execute()
    )
    return [r["ticker"] for r in (res.data or [])]


def _fetch_subreddit(ticker: str, subreddit: str) -> list[dict] | None:
    """None: 차단/403. 빈 list: 정상 수집 but 게시물 없음."""
    headers = {"User-Agent": _USER_AGENT}
    cutoff = time.time() - _SEARCH_WINDOW_DAYS * 86400
    try:
        resp = requests.get(
            f"https://www.reddit.com/r/{subreddit}/search.json",
            params={"q": ticker, "restrict_sr": "1", "sort": "new", "t": "week", "limit": 25},
            headers=headers,
            timeout=_TIMEOUT,
        )
        if resp.status_code in (403, 429):
            log.warning("Reddit blocked/rate-limited [r/%s, %s]: %d", subreddit, ticker, resp.status_code)
            return None
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        return [
            c["data"] for c in children
            if c.get("data", {}).get("created_utc", 0) >= cutoff
        ]
    except Exception as e:
        log.warning("fetch error [r/%s, %s]: %s", subreddit, ticker, e)
        return None


def _collect(ticker: str) -> dict | None:
    """None 반환 시 모든 서브레딧 수집 실패 — DB 저장 스킵."""
    posts = []
    fetch_errors = 0
    for sub in _SUBREDDITS:
        result = _fetch_subreddit(ticker, sub)
        if result is None:  # 403/차단
            fetch_errors += 1
        else:
            posts.extend(result)
        time.sleep(_INTER_SUBREDDIT_SLEEP)
    if fetch_errors == len(_SUBREDDITS):
        return None  # 전 서브레딧 차단 → 저장 안 함
    post_count = len(posts)
    total_upvotes = sum(p.get("score", 0) for p in posts if p.get("score", 0) > 0)
    return {"post_count": post_count, "total_upvotes": total_upvotes}


def run() -> None:
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    tickers = _get_active_tickers(client)
    if not tickers:
        log.warning("reddit_batch: 종목 없음 — 스킵")
        return

    log.info("reddit_batch: %d종목 수집 시작 (REDDIT_BATCH_MAX=%d)", len(tickers), REDDIT_BATCH_MAX)
    ok = fail = 0
    now = datetime.now(timezone.utc).isoformat()

    blocked = 0
    for ticker in tickers:
        try:
            data = _collect(ticker)
            if data is None:
                blocked += 1
                continue  # 전 서브레딧 차단 → 저장 스킵
            client.table("reddit_snapshots").insert({
                "ticker": ticker,
                "post_count": data["post_count"],
                "total_upvotes": data["total_upvotes"],
                "collected_at": now,
            }).execute()
            log.info("[%s] post=%d upvotes=%d", ticker, data["post_count"], data["total_upvotes"])
            ok += 1
        except Exception as e:
            log.error("[%s] 오류: %s", ticker, e)
            fail += 1
        time.sleep(_INTER_TICKER_SLEEP)

    log.info("reddit_batch 완료: ok=%d fail=%d blocked=%d", ok, fail, blocked)


if __name__ == "__main__":
    run()
