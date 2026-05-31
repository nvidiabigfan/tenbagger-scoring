"""수급 데이터 조회 + 온디맨드 수집 엔드포인트.
14번 백엔드(localhost:8000)를 내부 프록시로 사용.
"""

import os
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/supply", tags=["supply"])

_SUPPLY_BACKEND = os.getenv("SUPPLY_BACKEND_URL", "http://localhost:8000")
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _validate(ticker: str) -> str:
    t = ticker.upper().strip()
    if not _TICKER_RE.match(t):
        raise HTTPException(status_code=400, detail="invalid ticker")
    return t


@router.get("/{ticker}")
async def get_supply(ticker: str):
    t = _validate(ticker)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_SUPPLY_BACKEND}/supply/{t}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="no supply data")
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail="supply backend error")
    return r.json()


@router.get("/{ticker}/history")
async def get_supply_history(ticker: str, limit: int = 60):
    t = _validate(ticker)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_SUPPLY_BACKEND}/supply/{t}/history", params={"limit": min(limit, 120)})
    if not r.is_success:
        return []
    return r.json()


@router.post("/{ticker}/collect")
async def collect_on_demand(ticker: str):
    t = _validate(ticker)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{_SUPPLY_BACKEND}/supply/{t}/collect")
    if not r.is_success:
        raise HTTPException(status_code=r.status_code, detail="collect failed")
    return r.json()
