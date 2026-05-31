"""수급 데이터 조회 + 온디맨드 수집 엔드포인트."""

import re

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.db.client import _get_client
from app.jobs.supply_collect_batch import collect_supply

router = APIRouter(prefix="/supply", tags=["supply"])

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _validate(ticker: str) -> str:
    t = ticker.upper().strip()
    if not _TICKER_RE.match(t):
        raise HTTPException(status_code=400, detail="invalid ticker")
    return t


@router.get("/{ticker}")
def get_supply(ticker: str):
    t = _validate(ticker)
    res = (
        _get_client()
        .table("supply_snapshots")
        .select("*")
        .eq("ticker", t)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="no supply data")
    return res.data[0]


@router.get("/{ticker}/history")
def get_supply_history(ticker: str, limit: int = 60):
    t = _validate(ticker)
    res = (
        _get_client()
        .table("supply_snapshots")
        .select("snapshot_date,close_price,short_interest_pct,pc_ratio,volume_vs_avg")
        .eq("ticker", t)
        .order("snapshot_date", desc=True)
        .limit(min(limit, 120))
        .execute()
    )
    return res.data


@router.post("/{ticker}/collect")
def collect_on_demand(ticker: str, background_tasks: BackgroundTasks):
    t = _validate(ticker)

    def _run():
        data = collect_supply(t)
        _get_client().table("supply_snapshots").upsert(
            data, on_conflict="ticker,snapshot_date"
        ).execute()

    background_tasks.add_task(_run)
    return {"status": "collecting", "ticker": t}
