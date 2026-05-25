"""S&P500 + 나스닥100 종목 마스터 Supabase upsert.

데이터 소스: Wikipedia (yfinance rate limit 우회)
실행: python -m app.jobs.import_stock_master
소요: 약 1분
"""

import io
import os
import logging
import urllib.request
import pandas as pd
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
BATCH_SIZE = 100


def _read_html_wiki(url: str) -> list[pd.DataFrame]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        html = resp.read()
    return pd.read_html(io.BytesIO(html))


def fetch_sp500_rows() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = _read_html_wiki(url)
    df = next(t for t in tables if "Symbol" in t.columns)
    rows = []
    for _, row in df.iterrows():
        ticker = str(row["Symbol"]).replace(".", "-").strip()
        industry = row.get("GICS Sub-Industry")
        rows.append({
            "ticker": ticker,
            "company_name": str(row.get("Security", ticker)),
            "sector": str(row.get("GICS Sector", "Unknown")),
            "industry": str(industry) if pd.notna(industry) else None,
            "market_cap": None,
            "exchange": "NYSE",
            "logo_url": None,
            "is_active": True,
        })
    return rows


def fetch_nasdaq100_rows() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    tables = _read_html_wiki(url)
    for t in tables:
        str_cols = [c for c in t.columns if isinstance(c, str)]
        lower = [c.lower() for c in str_cols]
        if "ticker" in lower or "symbol" in lower:
            col = next(c for c in str_cols if c.lower() in ("ticker", "symbol"))
            name_col = next((c for c in str_cols if c.lower() in ("company", "security", "name")), None)
            sector_col = next((c for c in str_cols if "sector" in c.lower()), None)
            rows = []
            for _, row in t.iterrows():
                ticker = str(row[col]).replace(".", "-").strip()
                rows.append({
                    "ticker": ticker,
                    "company_name": str(row[name_col]) if name_col else ticker,
                    "sector": str(row[sector_col]) if sector_col else "Unknown",
                    "industry": None,
                    "market_cap": None,
                    "exchange": "NASDAQ",
                    "logo_url": None,
                    "is_active": True,
                })
            return rows
    raise ValueError("나스닥100 테이블 파싱 실패")


def upsert_batch(client, rows: list[dict]) -> int:
    if not rows:
        return 0
    client.table("stocks").upsert(rows, on_conflict="ticker").execute()
    return len(rows)


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    sp500 = {r["ticker"]: r for r in fetch_sp500_rows()}
    log.info("S&P500: %d종목", len(sp500))

    ndx100 = {r["ticker"]: r for r in fetch_nasdaq100_rows()}
    log.info("나스닥100: %d종목", len(ndx100))

    # 중복 시 S&P500 우선 (섹터 정보 더 정확), NASDAQ 종목은 exchange 보정
    merged = {**ndx100, **sp500}
    for ticker in ndx100:
        if ticker in merged:
            merged[ticker]["exchange"] = "NASDAQ"

    rows = list(merged.values())
    log.info("합산(중복제거): %d종목", len(rows))

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        total += upsert_batch(client, batch)
        log.info("upserted %d / %d", total, len(rows))

    log.info("완료: stocks 테이블 %d행", total)


if __name__ == "__main__":
    main()
