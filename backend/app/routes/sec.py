"""SEC EDGAR 최근 파일링 조회 (10-K / 10-Q / 8-K).

EDGAR public API (무료, 인증 불필요):
  CIK 조회: www.sec.gov/files/company_tickers.json
  파일링 목록: data.sec.gov/submissions/CIK{}.json
  재무 수치: data.sec.gov/api/xbrl/companyfacts/CIK{}.json

AI 요약은 백엔드 GROQ_API_KEY 미등록으로 미구현 (null 반환).
risk_flags는 XBRL 재무 수치 기반 rule-based 탐지.
결과는 24h 인메모리 캐시.
"""

import asyncio
import logging
import os
import time

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/sec", tags=["sec"])
log = logging.getLogger(__name__)

_EDGAR_COMPANY = "https://www.sec.gov/files/company_tickers.json"
_EDGAR_BASE = "https://data.sec.gov"
_HEADERS = {
    "User-Agent": os.getenv("EDGAR_USER_AGENT", "tenbagger-scoring contact@example.com"),
    "Accept-Encoding": "gzip, deflate",
}
_TARGET_FORMS = {"10-K", "10-Q", "8-K"}
_MAX_FILINGS = 8
_CACHE_TTL = 86400  # 24h

_cache: dict[str, tuple[float, list]] = {}


async def _get(client: httpx.AsyncClient, url: str) -> dict:
    await asyncio.sleep(0.15)  # EDGAR: ~10 req/s 허용
    resp = await client.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


async def _get_cik(ticker: str) -> str | None:
    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, _EDGAR_COMPANY)
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker:
                    return str(entry["cik_str"]).zfill(10)
        except Exception as e:
            log.warning("CIK lookup %s: %s", ticker, e)
    return None


def _detect_risk_flags(facts: dict) -> list[str]:
    """XBRL company_facts에서 rule-based risk_flags 탐지."""
    flags: list[str] = []
    try:
        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        def _latest_two(concept: str) -> tuple[float | None, float | None]:
            """가장 최근 annual 값 2개 반환 (newest, prev)."""
            units = us_gaap.get(concept, {}).get("units", {})
            vals = [
                v for v in units.get("USD", [])
                if v.get("form") in ("10-K", "10-Q") and v.get("val") is not None
            ]
            vals.sort(key=lambda v: v.get("end", ""), reverse=True)
            if len(vals) >= 2:
                return float(vals[0]["val"]), float(vals[1]["val"])
            return None, None

        # 매출 감소
        rev_now, rev_prev = _latest_two("RevenueFromContractWithCustomerExcludingAssessedTax")
        if rev_now is None:
            rev_now, rev_prev = _latest_two("Revenues")
        if rev_now is not None and rev_prev is not None and rev_prev > 0:
            if rev_now < rev_prev * 0.95:
                flags.append("revenue_decline")

        # 순이익 마진 압박
        ni_now, ni_prev = _latest_two("NetIncomeLoss")
        if rev_now and rev_now > 0 and ni_now is not None and ni_prev is not None:
            margin_now = ni_now / rev_now
            margin_prev = ni_prev / rev_prev if rev_prev else 0
            if margin_now < margin_prev - 0.05:
                flags.append("margin_pressure")

        # 부채 우려: 부채/자산 > 0.8
        assets = us_gaap.get("Assets", {}).get("units", {}).get("USD", [])
        liab = us_gaap.get("Liabilities", {}).get("units", {}).get("USD", [])
        if assets and liab:
            a = sorted(assets, key=lambda v: v.get("end", ""), reverse=True)
            l_ = sorted(liab, key=lambda v: v.get("end", ""), reverse=True)
            if a and l_:
                ratio = float(l_[0]["val"]) / float(a[0]["val"]) if float(a[0]["val"]) > 0 else 0
                if ratio > 0.8:
                    flags.append("debt_concern")

    except Exception as e:
        log.debug("risk_flags detection error: %s", e)
    return flags


async def _fetch(ticker: str) -> list[dict]:
    now = time.time()
    if ticker in _cache:
        ts, data = _cache[ticker]
        if now - ts < _CACHE_TTL:
            return data

    cik = await _get_cik(ticker)
    if not cik:
        _cache[ticker] = (now, [])
        return []

    cik_int = int(cik)
    filings: list[dict] = []

    async with httpx.AsyncClient() as client:
        try:
            subs = await _get(client, f"{_EDGAR_BASE}/submissions/CIK{cik}.json")
        except Exception as e:
            log.error("Submissions %s: %s", ticker, e)
            return []

        recent = subs.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        periods = recent.get("reportDate", [])
        items_list = recent.get("items", [])

        for i, (form, date_, acc, period) in enumerate(zip(forms, dates, accs, periods)):
            if form not in _TARGET_FORMS:
                continue
            acc_clean = acc.replace("-", "")
            edgar_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{acc}-index.htm"
            raw_items = items_list[i] if i < len(items_list) else ""
            items = [x.strip() for x in raw_items.split(",") if x.strip()] if raw_items else []
            filings.append({
                "id": acc,
                "ticker": ticker,
                "form_type": form,
                "filed_date": date_,
                "report_period": period or None,
                "edgar_url": edgar_url,
                "items": items,
                "ai_summary": None,
                "risk_flags": None,
                "analyzed_at": None,
            })
            if len(filings) >= _MAX_FILINGS:
                break

        # 10-K/10-Q가 있을 때만 XBRL risk_flags 탐지 (별도 요청)
        has_fundamental = any(f["form_type"] in ("10-K", "10-Q") for f in filings)
        if has_fundamental:
            try:
                facts = await _get(client, f"{_EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
                flags = _detect_risk_flags(facts)
                for f in filings:
                    if f["form_type"] in ("10-K", "10-Q"):
                        f["risk_flags"] = flags if flags else []
            except Exception as e:
                log.debug("XBRL facts %s: %s", ticker, e)

    _cache[ticker] = (now, filings)
    return filings


@router.get("/{ticker}")
async def get_sec_filings(ticker: str):
    t = ticker.upper().strip()
    if not t.isalpha() or len(t) > 5:
        raise HTTPException(status_code=400, detail="invalid ticker")
    return await _fetch(t)
