"""yfinance 기반 분기 재무제표 backfill.

universe 전 종목의 quarterly_income_stmt(매출/이익/EPS)를 DuckDB에 적재.
Revenue 모듈 PIT 백테스트에 사용.

핵심 설계:
  avail_date = period_end + 45일
  → 분기 말 후 45일이 지나야 해당 분기 데이터를 '사용 가능'으로 처리.
  → 어닝 발표 래그를 보수적으로 모델링해 look-ahead bias 차단.

실행: python -m backtest.data.fundamentals [--batch 50] [--sleep 2]
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import timedelta

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
from supabase import create_client

from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_LAG_DAYS = 45  # 분기 말 → 어닝 발표 보수적 래그


def _get_universe() -> list[str]:
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    res = client.table("stocks").select("ticker").eq("is_active", True).execute()
    return sorted({r["ticker"] for r in (res.data or [])})


def _fetch_quarterly(ticker: str) -> pd.DataFrame:
    """yfinance quarterly_income_stmt → long DataFrame."""
    t = yf.Ticker(ticker)
    try:
        stmt = t.quarterly_income_stmt
    except Exception:
        return pd.DataFrame()

    if stmt is None or stmt.empty:
        return pd.DataFrame()

    rows = []
    for col in stmt.columns:
        period_end = pd.Timestamp(col).date()
        avail_date = period_end + timedelta(days=_LAG_DAYS)

        def _get(key):
            for k in stmt.index:
                if key.lower() in k.lower():
                    val = stmt.loc[k, col]
                    return float(val) if pd.notna(val) else None
            return None

        revenue     = _get("total revenue")
        gross       = _get("gross profit")
        net_income  = _get("net income")
        eps         = _get("diluted eps")

        if revenue is None:
            continue

        rows.append({
            "ticker":       ticker,
            "period_end":   period_end,
            "avail_date":   avail_date,
            "total_revenue": revenue,
            "gross_profit":  gross,
            "net_income":    net_income,
            "eps_diluted":   eps,
        })

    return pd.DataFrame(rows)


def _upsert(con, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    con.register("_tmp_qf", df)
    con.execute("""
        INSERT INTO quarterly_fundamentals
            (ticker, period_end, avail_date, total_revenue, gross_profit, net_income, eps_diluted)
        SELECT ticker, period_end::DATE, avail_date::DATE,
               total_revenue, gross_profit, net_income, eps_diluted
        FROM _tmp_qf
        ON CONFLICT (ticker, period_end) DO UPDATE SET
            total_revenue = EXCLUDED.total_revenue,
            gross_profit  = EXCLUDED.gross_profit,
            net_income    = EXCLUDED.net_income,
            eps_diluted   = EXCLUDED.eps_diluted
    """)
    con.unregister("_tmp_qf")
    return len(df)


def run(batch_size: int = 50, inter_batch_sleep: float = 2.0) -> None:
    universe = _get_universe()
    log.info("Universe: %d tickers", len(universe))

    con = duckdb_store.connect()
    total = 0

    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]
        batch_rows = []

        for ticker in batch:
            df = _fetch_quarterly(ticker)
            if not df.empty:
                batch_rows.append(df)

        if batch_rows:
            combined = pd.concat(batch_rows, ignore_index=True)
            n = _upsert(con, combined)
            total += n

        log.info("[%d/%d] batch 완료 — 누적 %d rows", i + len(batch), len(universe), total)
        time.sleep(inter_batch_sleep)

    log.info("완료: 총 %d rows", total)
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=50)
    p.add_argument("--sleep", type=float, default=2.0)
    args = p.parse_args()
    run(batch_size=args.batch, inter_batch_sleep=args.sleep)
