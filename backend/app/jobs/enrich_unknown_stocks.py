"""Unknown 섹터 종목 일괄 보완.

Supabase에서 sector='Unknown' 종목 조회 → Finviz에서 회사명/섹터/업종 fetch → 업데이트.
실행: python -m app.jobs.enrich_unknown_stocks
"""

import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client
from app.core import finviz

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_SLEEP_BETWEEN = 2.5   # Finviz 429 방지


def run() -> None:
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    res = client.table("stocks").select("ticker,company_name,sector").eq("sector", "Unknown").execute()
    rows = res.data or []
    log.info("Unknown 섹터 종목: %d개", len(rows))

    ok = 0
    fail = 0
    for row in rows:
        ticker = row["ticker"]
        try:
            info = finviz.get_stock_info(ticker)
            if not info.get("sector") or info["sector"] == "Unknown":
                log.warning("[%s] sector 파싱 실패 — 건너뜀", ticker)
                fail += 1
                continue

            client.table("stocks").update({
                "company_name": info.get("company_name", ticker),
                "sector":       info["sector"],
                "industry":     info.get("industry"),
                "exchange":     info.get("exchange", "US"),
                "updated_at":   "now()",
            }).eq("ticker", ticker).execute()

            log.info("[%s] %s / %s / %s", ticker, info.get("company_name"), info.get("sector"), info.get("industry"))
            ok += 1
        except Exception as e:
            log.warning("[%s] 오류: %s", ticker, e)
            fail += 1

        time.sleep(_SLEEP_BETWEEN)

    log.info("완료: 성공 %d / 실패 %d", ok, fail)


if __name__ == "__main__":
    run()
