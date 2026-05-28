"""SEC EDGAR 분기 재무 데이터 역사적 backfill.

Source : https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
Rate   : 10 req/sec (SEC fair-use 정책)
Coverage: 2009~현재, 전 SEC 신고 기업

실행:
  python -m backtest.data.edgar_backfill [--start-year 2014] [--tickers AAPL MSFT ...]
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date

import pandas as pd
import requests

from backtest.storage import duckdb_store

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

EDGAR_BASE = "https://data.sec.gov"
HEADERS    = {"User-Agent": "tenbagger-scoring research ohone4194@gmail.com"}

# Revenue XBRL 개념 — 존재하는 첫 번째 사용
_REV_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
_NI_CONCEPTS = ["NetIncomeLoss", "NetIncome", "ProfitLoss"]
_EPS_CONCEPTS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]


# ── EDGAR 유틸 ────────────────────────────────────────────────────────────

def _get_cik_map() -> dict[str, str]:
    """ticker → 10자리 zero-padded CIK."""
    resp = requests.get("https://www.sec.gov/files/company_tickers.json",
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return {v["ticker"]: str(v["cik_str"]).zfill(10) for v in resp.json().values()}


def _fetch_facts(cik: str) -> dict | None:
    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug("EDGAR 실패 CIK=%s: %s", cik, e)
        return None


def _extract_quarterly(facts: dict, concept: str, unit_filter: str = "USD") -> dict[date, dict]:
    """us-gaap concept → {period_end: {filed, value}} (분기 데이터만)."""
    try:
        entries = facts["facts"]["us-gaap"][concept]["units"][unit_filter]
    except KeyError:
        return {}

    result: dict[date, dict] = {}
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K"):
            continue
        try:
            start    = date.fromisoformat(e["start"])
            end      = date.fromisoformat(e["end"])
            duration = (end - start).days
            if not (75 <= duration <= 105):   # 분기 = ~91일 ± 여유
                continue
            filed = date.fromisoformat(e["filed"])
        except (KeyError, ValueError):
            continue

        # 동일 period_end → 최초 공시(filed 빠른 것) 우선
        if end not in result or filed < result[end]["filed"]:
            result[end] = {"filed": filed, "value": e["val"]}

    return result


def _first_concept(facts: dict, concepts: list[str], unit: str = "USD") -> dict[date, dict]:
    for c in concepts:
        rows = _extract_quarterly(facts, c, unit)
        if rows:
            return rows
    return {}


def _build_rows(ticker: str, facts: dict, start_year: int) -> list[dict]:
    rev_map = _first_concept(facts, _REV_CONCEPTS)
    ni_map  = _first_concept(facts, _NI_CONCEPTS)
    eps_map = _first_concept(facts, _EPS_CONCEPTS, unit="USD/shares")

    all_periods = sorted(
        pe for pe in (set(rev_map) | set(ni_map) | set(eps_map))
        if pe.year >= start_year
    )

    rows = []
    for pe in all_periods:
        rev = rev_map.get(pe)
        ni  = ni_map.get(pe)
        eps = eps_map.get(pe)

        # avail_date = 실제 SEC 공시일 (PIT 보장)
        filed_dates = [r["filed"] for r in [rev, ni, eps] if r]
        if not filed_dates:
            continue
        avail_date = max(filed_dates)   # 모든 항목 공시 완료 시점

        rows.append({
            "ticker":        ticker,
            "period_end":    pe,
            "avail_date":    avail_date,
            "total_revenue": rev["value"] if rev else None,
            "gross_profit":  None,               # EDGAR income stmt에 없음
            "net_income":    ni["value"] if ni else None,
            "eps_diluted":   eps["value"] if eps else None,
        })
    return rows


def _upsert(con, rows: list[dict]) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    con.register("_tmp_edgar", df)
    con.execute("""
        INSERT INTO quarterly_fundamentals
            (ticker, period_end, avail_date, total_revenue, gross_profit, net_income, eps_diluted)
        SELECT ticker, period_end::DATE, avail_date::DATE,
               total_revenue, gross_profit, net_income, eps_diluted
        FROM _tmp_edgar
        ON CONFLICT (ticker, period_end) DO UPDATE SET
            avail_date    = EXCLUDED.avail_date,
            total_revenue = COALESCE(EXCLUDED.total_revenue, quarterly_fundamentals.total_revenue),
            net_income    = COALESCE(EXCLUDED.net_income,    quarterly_fundamentals.net_income),
            eps_diluted   = COALESCE(EXCLUDED.eps_diluted,   quarterly_fundamentals.eps_diluted)
    """)
    con.unregister("_tmp_edgar")
    return len(rows)


# ── main ──────────────────────────────────────────────────────────────────

def run(tickers: list[str] | None = None, start_year: int = 2014) -> None:
    log.info("SEC EDGAR backfill 시작 (start_year=%d)", start_year)
    con = duckdb_store.connect()

    log.info("CIK 매핑 다운로드...")
    cik_map = _get_cik_map()
    log.info("CIK 매핑: %d tickers", len(cik_map))

    if tickers is None:
        result  = con.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker").fetchall()
        tickers = [r[0] for r in result]
    log.info("대상: %d tickers", len(tickers))

    ok = fail = skip = total_rows = 0
    for i, ticker in enumerate(tickers, 1):
        cik = cik_map.get(ticker)
        if not cik:
            skip += 1
            continue

        facts = _fetch_facts(cik)
        if facts is None:
            fail += 1
            time.sleep(0.12)
            continue

        rows = _build_rows(ticker, facts, start_year)
        n    = _upsert(con, rows)
        total_rows += n
        ok += 1

        if i % 10 == 0:
            log.info("진행 %d/%d | ok=%d fail=%d skip=%d rows=%d",
                     i, len(tickers), ok, fail, skip, total_rows)

        time.sleep(0.12)   # SEC fair-use: 10 req/s 이하

    log.info("완료 | ok=%d fail=%d skip=%d total_rows=%d", ok, fail, skip, total_rows)

    r = con.execute("""
        SELECT COUNT(DISTINCT ticker), MIN(period_end), MAX(period_end), COUNT(*)
        FROM quarterly_fundamentals
    """).fetchone()
    log.info("quarterly_fundamentals: tickers=%d period=%s~%s rows=%d", *r)
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="SEC EDGAR quarterly fundamentals backfill")
    p.add_argument("--start-year", type=int, default=2014)
    p.add_argument("--tickers", nargs="+", help="특정 ticker만 처리 (기본: prices 전체)")
    args = p.parse_args()
    run(tickers=args.tickers, start_year=args.start_year)
