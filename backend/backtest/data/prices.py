"""yfinance 기반 가격 시계열 backfill.

universe(Supabase stocks 마스터)의 종목들 OHLCV를 일괄 다운로드.
실행: python -m backtest.data.prices [--start 2014-01-01] [--batch 50]

특징:
- yfinance.download() 배치 호출 (네트워크 효율)
- 기존 데이터 있으면 마지막 날짜 이후만 incremental 수집
- API rate limit 회피용 배치 간 sleep
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()
from supabase import create_client

from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _get_universe() -> list[str]:
    """Supabase stocks 마스터에서 active 종목 ticker 리스트."""
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    res = client.table("stocks").select("ticker").eq("is_active", True).execute()
    return sorted({r["ticker"] for r in (res.data or [])})


def _last_date(con, ticker: str) -> date | None:
    row = con.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", [ticker]).fetchone()
    return row[0] if row and row[0] else None


def _download_batch(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """yfinance 배치 다운로드. group_by='ticker' 형태로 multi-index 반환."""
    df = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    return df


def _flatten(df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """multi-index df → long format (ticker, date, ohlcv) DataFrame."""
    rows = []
    for ticker in tickers:
        if ticker not in df.columns.get_level_values(0):
            continue
        sub = df[ticker].dropna(how="all").reset_index()
        if sub.empty:
            continue
        sub["ticker"] = ticker
        # yfinance 0.2.x → "Date" / 1.x → "index" (index.name이 None)
        sub = sub.rename(columns={
            "Date": "date", "index": "date", "Datetime": "date",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adj_close",
            "Volume": "volume",
        })
        rows.append(sub[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]])
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _upsert_prices(con, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    con.register("tmp_prices", df)
    con.execute("""
        INSERT INTO prices (ticker, date, open, high, low, close, adj_close, volume)
        SELECT ticker, date::DATE, open, high, low, close, adj_close, volume FROM tmp_prices
        ON CONFLICT (ticker, date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume
    """)
    con.unregister("tmp_prices")
    return len(df)


def run(start: str = "2014-01-01", batch_size: int = 50, inter_batch_sleep: float = 2.0) -> None:
    universe = _get_universe()
    log.info("Universe: %d tickers", len(universe))

    con = duckdb_store.connect()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_rows = 0
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]

        # incremental: 배치 내 가장 빠른 last_date 기준 (보수적)
        per_start = start
        last_dates = [_last_date(con, t) for t in batch]
        valid_dates = [d for d in last_dates if d]
        if len(valid_dates) == len(batch):
            min_last = min(valid_dates)
            per_start = (min_last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            if per_start >= end:
                log.info("[%d-%d] 모두 최신 — 스킵", i, i + len(batch))
                continue

        log.info("[%d/%d] batch %d개, %s ~ %s", i + len(batch), len(universe), len(batch), per_start, end)
        try:
            raw = _download_batch(batch, per_start, end)
            flat = _flatten(raw, batch)
            n = _upsert_prices(con, flat)
            total_rows += n
            log.info("  upsert %d rows (누적 %d)", n, total_rows)
        except Exception as e:
            log.error("  batch 실패: %s", e)

        time.sleep(inter_batch_sleep)

    log.info("완료: 총 %d rows upsert", total_rows)
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2014-01-01")
    p.add_argument("--batch", type=int, default=50)
    p.add_argument("--sleep", type=float, default=2.0)
    args = p.parse_args()
    run(start=args.start, batch_size=args.batch, inter_batch_sleep=args.sleep)
