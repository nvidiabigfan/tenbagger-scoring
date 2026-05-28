"""Finviz 일일 snapshot 수집.

매일 1회 universe 전 종목의 Finviz get_metrics() 결과를 JSON으로 저장.
사후 어떤 필드든 추출 가능 (스키마 변경 불필요).

실행:
  python -m backtest.jobs.daily_snapshot

스케줄: GitHub Actions daily-batch.yml에 신규 job으로 추가.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
from supabase import create_client

from app.core import finviz
from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_INTER_TICKER_SLEEP = 1.5  # Finviz rate limit 회피


def _get_universe() -> list[str]:
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    res = client.table("stocks").select("ticker").eq("is_active", True).execute()
    return sorted({r["ticker"] for r in (res.data or [])})


def _upsert_snapshot(con, ticker: str, metrics: dict, today: datetime) -> None:
    con.execute("""
        INSERT INTO finviz_snapshots (ticker, snapshot_date, metrics_json, fetched_at)
        VALUES (?, ?::DATE, ?::JSON, ?)
        ON CONFLICT (ticker, snapshot_date) DO UPDATE SET
            metrics_json = EXCLUDED.metrics_json,
            fetched_at = EXCLUDED.fetched_at
    """, [ticker, today.date(), json.dumps(metrics), today])


def run() -> None:
    universe = _get_universe()
    today = datetime.now(timezone.utc)
    log.info("Finviz snapshot 시작: %d 종목 (%s)", len(universe), today.date())

    con = duckdb_store.connect()
    ok = fail = 0

    for i, ticker in enumerate(universe, 1):
        try:
            metrics = finviz.get_metrics(ticker)
            _upsert_snapshot(con, ticker, metrics, today)
            ok += 1
            if i % 50 == 0:
                log.info("진행 %d/%d (ok=%d fail=%d)", i, len(universe), ok, fail)
        except Exception as e:
            fail += 1
            log.warning("[%s] 실패: %s", ticker, e)
        time.sleep(_INTER_TICKER_SLEEP)

    log.info("완료: ok=%d, fail=%d", ok, fail)
    con.close()


if __name__ == "__main__":
    run()
