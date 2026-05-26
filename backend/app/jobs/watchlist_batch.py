"""워치리스트 일일 재분석 배치.

GitHub Actions daily-batch.yml → watchlist-reanalysis job에서 실행.
워치리스트 등록 종목 중 24h 캐시가 없는 것만 재분석.
"""

import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

from app.analyzers.analyst import AnalystAnalyzer
from app.analyzers.etf import EtfAnalyzer
from app.analyzers.trends import TrendsAnalyzer, jitter_sleep
from app.analyzers.youtube import YouTubeAnalyzer
from app.db import client as db
from app.scoring.engine import ScoringEngine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_INTER_STOCK_SLEEP = 8.0  # 종목 간 기본 대기 (Trends 429 방지)


def _get_watchlist_tickers() -> list[str]:
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    res = client.table("watchlist").select("ticker").execute()
    return list({r["ticker"] for r in (res.data or [])})


def run() -> None:
    tickers = _get_watchlist_tickers()
    if not tickers:
        log.info("watchlist_batch: 워치리스트 없음 — 스킵")
        return

    log.info("watchlist_batch: %d개 종목 대상", len(tickers))

    engine = ScoringEngine(
        [EtfAnalyzer(), AnalystAnalyzer(), TrendsAnalyzer(), YouTubeAnalyzer()]
    )

    ok = fail = cached = 0
    for ticker in tickers:
        if db.get_recent_analysis(ticker):
            log.info("[%s] 캐시 히트 — 스킵", ticker)
            cached += 1
            continue

        try:
            sleep_s = jitter_sleep()
            log.info("[%s] 분석 시작 (pre-sleep %.1fs)", ticker, sleep_s)
            result = engine.analyze(ticker)
            db.save_analysis(result, trigger_source="scheduled")
            log.info("[%s] 저장 완료 (score=%.1f)", ticker, result.total_score)
            ok += 1
        except Exception as e:
            log.error("[%s] 오류: %s", ticker, e)
            fail += 1

        time.sleep(_INTER_STOCK_SLEEP)

    log.info("watchlist_batch 완료: 성공=%d, 실패=%d, 캐시=%d", ok, fail, cached)


if __name__ == "__main__":
    run()
