"""수급 데이터 조회 + 온디맨드 수집 엔드포인트.

21 Supabase `supply_snapshots`를 단일 진실 공급원으로 직접 조회한다.
(이전: 14번 백엔드 localhost:8000 httpx 프록시 — 통합으로 제거됨)
데이터 적재는 supply_collect_batch.py(GitHub Actions) + 본 collect 엔드포인트.
"""

import asyncio
import re

from fastapi import APIRouter, HTTPException

from app.db import client as db

router = APIRouter(prefix="/supply", tags=["supply"])

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

_DATA_LAG_NOTES = {
    "short": "FINRA 반월 집계 (약 2주 지연, yfinance shortPercentOfFloat)",
    "inst_insider": "Finviz 분기 기관·내부자 거래 변화율",
}


def _validate(ticker: str) -> str:
    t = ticker.upper().strip()
    if not _TICKER_RE.match(t):
        raise HTTPException(status_code=400, detail="invalid ticker")
    return t


@router.get("/{ticker}")
async def get_supply(ticker: str):
    t = _validate(ticker)
    snap = await asyncio.to_thread(db.get_latest_supply, t)
    if not snap:
        raise HTTPException(status_code=404, detail="no supply data")
    snap["data_lag_notes"] = _DATA_LAG_NOTES
    return snap


@router.get("/{ticker}/history")
async def get_supply_history(ticker: str, limit: int = 60):
    t = _validate(ticker)
    return await asyncio.to_thread(db.get_supply_history, t, min(limit, 120))


_COLLECT_TIMEOUT_S = 60


@router.post("/{ticker}/collect")
async def collect_on_demand(ticker: str):
    t = _validate(ticker)
    from app.jobs.supply_collect_batch import collect_supply

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(collect_supply, t), timeout=_COLLECT_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="수급 수집 시간 초과")
    await asyncio.to_thread(db.save_supply_snapshot, data)
    return {
        "message": f"{t} 수급 수집 완료",
        "snapshot_date": data["snapshot_date"],
        "source_flags": data["source_flags"],
    }
