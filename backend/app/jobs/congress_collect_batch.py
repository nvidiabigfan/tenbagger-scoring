"""미 국회의원 주식 매매 수집 배치.

GitHub Actions daily-batch.yml → congress-collection job에서 실행.
Quiver Quantitative 공개 피드(/beta/live/congresstrading)에서 최근 거래를
받아 congress_trades 테이블에 upsert. 매일 1회 누적되며 1000건 윈도우 한계를
자체적으로 보완한다.

비용: Quiver free 엔드포인트 $0 (1일 1회, rate-limit 내).
"""

import logging
import os
from datetime import date

import httpx
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

QUIVER_URL = "https://api.quiverquant.com/beta/live/congresstrading"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# 이 엔드포인트는 Authorization 헤더 '존재'만 체크(공개 위젯용). 무료키 발급 시
# QUIVER_API_KEY로 넣으면 그대로 사용 — 향후 Quiver가 검증 강화해도 코드 변경 불필요.
QUIVER_API_KEY = os.environ.get("QUIVER_API_KEY", "public")


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_date(v) -> str | None:
    if not v:
        return None
    return str(v)[:10]


def _side(transaction: str | None) -> str:
    t = (transaction or "").lower()
    if "purchase" in t:
        return "buy"
    if "sale" in t:
        return "sell"
    return "other"


def fetch_trades() -> list[dict]:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Authorization": f"Token {QUIVER_API_KEY}",
    }
    with httpx.Client(timeout=30.0, headers=headers) as c:
        r = c.get(QUIVER_URL)
        r.raise_for_status()
        return r.json()


def to_row(x: dict, snapshot: str) -> dict | None:
    ticker = (x.get("Ticker") or "").strip().upper()
    if not ticker or len(ticker) > 6:
        return None
    return {
        "ticker": ticker,
        "representative": x.get("Representative"),
        "bioguide_id": x.get("BioGuideID"),
        "party": x.get("Party"),
        "house": x.get("House"),
        "transaction": x.get("Transaction"),
        "side": _side(x.get("Transaction")),
        "transaction_date": _to_date(x.get("TransactionDate")),
        "report_date": _to_date(x.get("ReportDate")),
        "amount_min": _to_float(x.get("Amount")),
        "range_text": x.get("Range"),
        "ticker_type": x.get("TickerType"),
        "excess_return": _to_float(x.get("ExcessReturn")),
        "price_change": _to_float(x.get("PriceChange")),
        "spy_change": _to_float(x.get("SPYChange")),
        "last_modified": _to_date(x.get("last_modified")),
        "snapshot_date": snapshot,
    }


def main() -> None:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    snapshot = date.today().isoformat()

    trades = fetch_trades()
    log.info(f"Quiver 피드 {len(trades)}건 수신")

    rows = [r for r in (to_row(x, snapshot) for x in trades) if r is not None]
    # bioguide_id 등 None이면 UNIQUE 충돌 dedupe가 약하므로 키 누락 행은 건너뜀
    rows = [r for r in rows if r["bioguide_id"] and r["transaction_date"]]

    # 피드 내 conflict-key 중복 제거 (같은 청크에 들어가면 ON CONFLICT 21000 에러)
    deduped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["bioguide_id"], r["ticker"], r["transaction_date"], r["transaction"], r["amount_min"])
        deduped[key] = r  # 마지막 값 유지
    rows = list(deduped.values())
    log.info(f"유효 거래 {len(rows)}건 적재 시작 (dedup 후)")

    ok = fail = 0
    # 100건씩 배치 upsert
    for i in range(0, len(rows), 100):
        chunk = rows[i : i + 100]
        try:
            sb.table("congress_trades").upsert(
                chunk,
                on_conflict="bioguide_id,ticker,transaction_date,transaction,amount_min",
            ).execute()
            ok += len(chunk)
        except Exception as e:
            log.error(f"✗ chunk {i}: {e}")
            fail += len(chunk)

    log.info(f"완료: ok={ok} fail={fail} / {len(rows)} (snapshot={snapshot})")


if __name__ == "__main__":
    main()
