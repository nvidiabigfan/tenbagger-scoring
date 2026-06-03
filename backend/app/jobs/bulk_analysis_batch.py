"""종목 마스터 전체 대상 일괄 분석 배치.

GitHub Actions daily-batch.yml → bulk-analysis job에서 실행.
실행 흐름:
  1. stocks 마스터 → market_cap DESC 정렬 (중요 종목 우선)
  2. 24h 캐시 없는 종목만 분석 (최대 MAX_BATCH개)
  3. 분석 완료 후 ranking_snapshot 자동 실행
YouTube API 10,000 unit/일 한도 → 종목당 ~101 unit → YouTubeAnalyzer 내부 85회 hard limit
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from app.analyzers.analyst import AnalystAnalyzer
from app.analyzers.buzz import BuzzAnalyzer
from app.analyzers.congress import CongressAnalyzer
from app.analyzers.etf import EtfAnalyzer
from app.analyzers.insider import InsiderAnalyzer
from app.analyzers.momentum import MomentumAnalyzer
from app.analyzers.revenue import RevenueAccelerationAnalyzer
from app.analyzers.size import SizeAnalyzer
from app.db import client as db
from app.db.client import _get_client
from app.jobs import ranking_snapshot
from app.scoring.engine import ScoringEngine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

MAX_BATCH = int(os.getenv("BULK_BATCH_MAX", "500"))
FORCE_REANALYSIS = os.getenv("FORCE_REANALYSIS", "0") == "1"
STALE_DAYS = int(os.getenv("STALE_DAYS", "3"))  # N일 이상 분석 안 된 종목을 stale로 간주
_INTER_STOCK_SLEEP = 5.0  # 종목 간 대기 (Finviz rate limit 방지, 새벽 배치 기준)


def _get_candidate_tickers() -> list[str]:
    """stale 종목 우선 + market_cap DESC로 후보 반환.

    정렬 우선순위:
    1. 한 번도 분석 안 된 종목 (never analyzed)
    2. STALE_DAYS 이상 분석 안 된 종목 (stale), analyzed_at ASC
    3. 최근 분석된 종목, market_cap DESC
    """
    sb = _get_client()

    # 전체 active 종목
    stocks_res = (
        sb.table("stocks")
        .select("ticker, market_cap")
        .eq("is_active", True)
        .order("market_cap", desc=True, nullsfirst=False)
        .execute()
    )
    all_stocks: list[dict] = stocks_res.data or []
    market_cap_map = {r["ticker"]: r.get("market_cap") for r in all_stocks}
    all_tickers_ordered = [r["ticker"] for r in all_stocks]  # market_cap DESC

    # 최신 분석일 조회 (ticker당 1건)
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).isoformat()
    analysis_res = (
        sb.table("analysis_results")
        .select("ticker, analyzed_at")
        .order("analyzed_at", desc=True)
        .limit(5000)
        .execute()
    )
    latest_at: dict[str, str] = {}
    for row in (analysis_res.data or []):
        t = row["ticker"]
        if t not in latest_at:
            latest_at[t] = row["analyzed_at"]

    # 분류
    never: list[str] = []
    stale: list[str] = []
    fresh: list[str] = []
    for ticker in all_tickers_ordered:
        at = latest_at.get(ticker)
        if at is None:
            never.append(ticker)
        elif at < stale_cutoff:
            stale.append(ticker)
        else:
            fresh.append(ticker)

    # stale은 analyzed_at ASC (가장 오래된 것부터)
    stale.sort(key=lambda t: latest_at.get(t, ""))

    log.info(
        "후보: never=%d stale(>%dd)=%d fresh=%d",
        len(never), STALE_DAYS, len(stale), len(fresh),
    )
    return never + stale + fresh


def run() -> None:
    all_tickers = _get_candidate_tickers()
    if not all_tickers:
        log.warning("bulk_analysis_batch: stocks 마스터 비어 있음 — 스킵")
        return

    log.info("bulk_analysis_batch: 마스터 %d개, MAX_BATCH=%d, FORCE=%s", len(all_tickers), MAX_BATCH, FORCE_REANALYSIS)

    engine = ScoringEngine([
        RevenueAccelerationAnalyzer(), EtfAnalyzer(), AnalystAnalyzer(),
        SizeAnalyzer(), MomentumAnalyzer(), BuzzAnalyzer(), InsiderAnalyzer(),
        CongressAnalyzer(),
    ])

    ok = fail = skipped = 0
    for ticker in all_tickers:
        if ok >= MAX_BATCH:
            log.info("bulk_analysis_batch: MAX_BATCH(%d) 도달 — 종료", MAX_BATCH)
            break

        if not FORCE_REANALYSIS and db.get_recent_analysis(ticker):
            skipped += 1
            continue

        log.info("[%s] 분석 시작 [%d/%d]", ticker, ok + 1, MAX_BATCH)
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
