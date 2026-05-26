"""종목 마스터 전체 대상 일괄 분석 배치.

GitHub Actions daily-batch.yml → bulk-analysis job에서 실행.
실행 흐름:
  1. stocks 마스터 → market_cap DESC 정렬 (중요 종목 우선)
  2. 24h 캐시 없는 종목만 분석 (최대 MAX_BATCH개)
  3. 분석 완료 후 ranking_snapshot 자동 실행
YouTube API 10,000 unit/일 한도 → 종목당 ~101 unit → MAX_BATCH=95 (여유분 확보)
"""

import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

from app.analyzers.analyst import AnalystAnalyzer
from app.analyzers.etf import EtfAnalyzer
from app.analyzers.reddit import RedditAnalyzer
from app.analyzers.size import SizeAnalyzer
from app.analyzers.trends import TrendsAnalyzer, jitter_sleep
from app.analyzers.youtube import YouTubeAnalyzer
from app.db import client as db
from app.jobs import ranking_snapshot
from app.scoring.engine import ScoringEngine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MAX_BATCH = int(os.getenv("BULK_BATCH_MAX", "95"))
_INTER_STOCK_SLEEP = 10.0  # 종목 간 대기 (Trends 429 방지)


def _get_candidate_tickers() -> list[str]:
    """stocks 마스터 전체를 market_cap DESC로 반환. NULL은 마지막."""
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )
    res = (
        client.table("stocks")
        .select("ticker, market_cap")
        .eq("is_active", True)
        .order("market_cap", desc=True, nullsfirst=False)
        .execute()
    )
    return [r["ticker"] for r in (res.data or [])]


def run() -> None:
    all_tickers = _get_candidate_tickers()
    if not all_tickers:
        log.warning("bulk_analysis_batch: stocks 마스터 비어 있음 — 스킵")
        return

    log.info("bulk_analysis_batch: 마스터 %d개, MAX_BATCH=%d", len(all_tickers), MAX_BATCH)

    engine = ScoringEngine(
        [SizeAnalyzer(), EtfAnalyzer(), AnalystAnalyzer(), TrendsAnalyzer(), YouTubeAnalyzer(), RedditAnalyzer()]
    )

    ok = fail = skipped = 0
    for ticker in all_tickers:
        if ok >= MAX_BATCH:
            log.info("bulk_analysis_batch: MAX_BATCH(%d) 도달 — 종료", MAX_BATCH)
            break

        if db.get_recent_analysis(ticker):
            skipped += 1
            continue

        sleep_s = jitter_sleep()
        log.info("[%s] 분석 시작 (pre-sleep %.1fs) [%d/%d]", ticker, sleep_s, ok + 1, MAX_BATCH)
        try:
            result = engine.analyze(ticker)
            db.save_analysis(result, trigger_source="scheduled")
            log.info("[%s] 완료 score=%.1f", ticker, result.total_score)
            ok += 1
        except Exception as e:
            log.error("[%s] 오류: %s", ticker, e)
            fail += 1

        time.sleep(_INTER_STOCK_SLEEP)

    log.info(
        "bulk_analysis_batch 완료: 분석=%d, 실패=%d, 캐시스킵=%d",
        ok, fail, skipped,
    )

    log.info("ranking_snapshot 실행")
    ranking_snapshot.run()


if __name__ == "__main__":
    run()
