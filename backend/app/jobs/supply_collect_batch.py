"""워치리스트 종목 수급 데이터 수집 배치.

GitHub Actions daily-batch.yml → supply-collection job에서 실행.
워치리스트 종목만 수집 (전종목 X). Finviz + yfinance 사용.
"""

import logging
import os
import time
from datetime import date

from dotenv import load_dotenv

load_dotenv()

import yfinance as yf
from supabase import create_client

from app.core import finviz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]


def collect_supply(ticker: str) -> dict:
    today = date.today().isoformat()
    result: dict = {
        "ticker": ticker,
        "snapshot_date": today,
        "close_price": None,
        "price_change_1m_pct": None,
        "price_change_1w_pct": None,
        "short_interest_pct": None,
        "volume_vs_avg": None,
        "pc_ratio": None,
        "institutional_net": None,
        "insider_net": None,
        "source_flags": {},
    }

    # --- yfinance: 종가·거래량·공매도 ---
    try:
        yf_t = yf.Ticker(ticker)
        hist = yf_t.history(period="30d", auto_adjust=True)
        if not hist.empty:
            closes = hist["Close"]
            last_close = float(closes.iloc[-1])
            result["close_price"] = round(last_close, 4)
            # 전월대비: 30일 윈도우 첫날(약 1개월 전) 종가 대비
            if len(closes) >= 2:
                first_close = float(closes.iloc[0])
                if first_close > 0:
                    result["price_change_1m_pct"] = round((last_close / first_close - 1) * 100, 2)
            # 전주대비: 5거래일 전 종가 대비
            if len(closes) >= 6:
                week_ago = float(closes.iloc[-6])
                if week_ago > 0:
                    result["price_change_1w_pct"] = round((last_close / week_ago - 1) * 100, 2)
            avg_vol = float(hist["Volume"].tail(20).mean())
            cur_vol = float(hist["Volume"].iloc[-1])
            if avg_vol > 0:
                result["volume_vs_avg"] = round(cur_vol / avg_vol, 3)
            result["source_flags"]["yfinance"] = True

        info = yf_t.info
        spof = info.get("shortPercentOfFloat")
        if spof is not None:
            result["short_interest_pct"] = round(float(spof), 4)
    except Exception as e:
        log.warning(f"{ticker} yfinance 오류: {e}")
        result["source_flags"]["yfinance"] = False

    # --- Finviz: 기관·내부자 ---
    try:
        metrics = finviz.get_metrics(ticker)
        inst = finviz.parse_float(metrics.get("Inst Trans"))
        if inst is not None:
            result["institutional_net"] = round(float(inst), 4)
            result["source_flags"]["finviz_inst"] = True
        insider = finviz.parse_float(metrics.get("Insider Trans"))
        if insider is not None:
            result["insider_net"] = round(float(insider), 4)
            result["source_flags"]["finviz_insider"] = True
    except Exception as e:
        log.warning(f"{ticker} Finviz 오류: {e}")

    # --- yfinance options: P/C ratio (실패해도 무시) ---
    try:
        exps = yf_t.options
        if exps:
            chain = yf_t.option_chain(exps[0])
            put_oi = int(chain.puts["openInterest"].fillna(0).sum())
            call_oi = int(chain.calls["openInterest"].fillna(0).sum())
            if call_oi > 0:
                result["pc_ratio"] = round(put_oi / call_oi, 3)
                result["source_flags"]["options"] = True
    except Exception:
        pass

    return result


def main() -> None:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    rows = sb.table("watchlist").select("ticker").execute().data
    tickers = sorted({r["ticker"] for r in rows})
    log.info(f"워치리스트 {len(tickers)}종목 수급 수집 시작")

    ok = fail = 0
    for ticker in tickers:
        try:
            data = collect_supply(ticker)
            sb.table("supply_snapshots").upsert(
                data, on_conflict="ticker,snapshot_date"
            ).execute()
            log.info(f"✓ {ticker} close={data['close_price']} vol_x={data['volume_vs_avg']}")
            ok += 1
        except Exception as e:
            log.error(f"✗ {ticker}: {e}")
            fail += 1
        time.sleep(1)  # Finviz rate limit 방지

    log.info(f"완료: ok={ok} fail={fail} / {len(tickers)}")


if __name__ == "__main__":
    main()
