"""종목 마스터 Supabase upsert.

소스: S&P500 + 나스닥100 (Wikipedia) + ARK ETF 보유종목 + 큐레이션 성장주
실행: python -m app.jobs.import_stock_master
소요: 약 2분
"""

import io
import json
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

# ARK ETF 보유종목 API (arkfunds.io 공개 API)
ARK_FUNDS = ["ARKK", "ARKW", "ARKG", "ARKF", "ARKX"]
ARK_API_URL = "https://arkfunds.io/api/v2/etf/holdings?symbol={fund}"

# 큐레이션 성장주: S&P500/NDX100 미포함 종목 중심
CURATED_STOCKS: list[dict] = [
    # AI / 반도체 소형 성장주
    {"ticker": "AI",    "company_name": "C3.ai Inc",                  "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "SMCI",  "company_name": "Super Micro Computer",        "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "ALAB",  "company_name": "Astera Labs",                 "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "SOUN",  "company_name": "SoundHound AI",               "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "BBAI",  "company_name": "BigBear.ai Holdings",         "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "IONQ",  "company_name": "IonQ Inc",                    "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "RGTI",  "company_name": "Rigetti Computing",           "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "QUBT",  "company_name": "Quantum Computing Inc",       "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "ARQQ",  "company_name": "Arqit Quantum",               "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "U",     "company_name": "Unity Software",              "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "PATH",  "company_name": "UiPath Inc",                  "sector": "Technology",             "exchange": "NYSE"},
    # 바이오 / 유전자 편집
    {"ticker": "CRSP",  "company_name": "CRISPR Therapeutics",         "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "BEAM",  "company_name": "Beam Therapeutics",           "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "EDIT",  "company_name": "Editas Medicine",             "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "NTLA",  "company_name": "Intellia Therapeutics",       "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "RXRX",  "company_name": "Recursion Pharmaceuticals",   "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "TWST",  "company_name": "Twist Bioscience",            "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "PACB",  "company_name": "Pacific Biosciences",         "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "NVAX",  "company_name": "Novavax Inc",                 "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "BNTX",  "company_name": "BioNTech SE",                 "sector": "Healthcare",             "exchange": "NASDAQ"},
    {"ticker": "HIMS",  "company_name": "Hims & Hers Health",          "sector": "Healthcare",             "exchange": "NYSE"},
    # 한국인 관심 글로벌 성장주
    {"ticker": "TSM",   "company_name": "Taiwan Semiconductor Mfg",    "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "BIDU",  "company_name": "Baidu Inc",                   "sector": "Communication Services", "exchange": "NASDAQ"},
    {"ticker": "BABA",  "company_name": "Alibaba Group",               "sector": "Consumer Cyclical",      "exchange": "NYSE"},
    {"ticker": "NIO",   "company_name": "NIO Inc",                     "sector": "Consumer Cyclical",      "exchange": "NYSE"},
    {"ticker": "LI",    "company_name": "Li Auto Inc",                 "sector": "Consumer Cyclical",      "exchange": "NASDAQ"},
    {"ticker": "XPEV",  "company_name": "XPeng Inc",                   "sector": "Consumer Cyclical",      "exchange": "NYSE"},
    {"ticker": "SHOP",  "company_name": "Shopify Inc",                 "sector": "Technology",             "exchange": "NYSE"},
    {"ticker": "HOOD",  "company_name": "Robinhood Markets",           "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "COIN",  "company_name": "Coinbase Global",             "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "MSTR",  "company_name": "MicroStrategy Inc",           "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "RIOT",  "company_name": "Riot Platforms",              "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "MARA",  "company_name": "Marathon Digital Holdings",   "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "CLSK",  "company_name": "CleanSpark Inc",              "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "HUT",   "company_name": "Hut 8 Corp",                  "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "SOFI",  "company_name": "SoFi Technologies",           "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "UPST",  "company_name": "Upstart Holdings",            "sector": "Financial Services",     "exchange": "NASDAQ"},
    {"ticker": "LYFT",  "company_name": "Lyft Inc",                    "sector": "Technology",             "exchange": "NASDAQ"},
    {"ticker": "SNAP",  "company_name": "Snap Inc",                    "sector": "Communication Services", "exchange": "NYSE"},
    {"ticker": "RBLX",  "company_name": "Roblox Corporation",          "sector": "Technology",             "exchange": "NYSE"},
    # 우주 / 에어택시
    {"ticker": "ACHR",  "company_name": "Archer Aviation",             "sector": "Industrials",            "exchange": "NYSE"},
    {"ticker": "JOBY",  "company_name": "Joby Aviation",               "sector": "Industrials",            "exchange": "NYSE"},
    {"ticker": "SPCE",  "company_name": "Virgin Galactic",             "sector": "Industrials",            "exchange": "NYSE"},
]


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


def fetch_midcap400_rows() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
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


def fetch_ark_rows() -> list[dict]:
    """ARK ETF 5종 보유종목 → stocks 행 목록 (arkfunds.io 공개 API)."""
    seen: dict[str, dict] = {}
    for fund in ARK_FUNDS:
        try:
            url = ARK_API_URL.format(fund=fund)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            count = 0
            for h in data.get("holdings", []):
                t = str(h.get("ticker", "")).strip().upper()
                if not t or len(t) > 5 or any(c.isdigit() for c in t):
                    continue
                if t not in seen:
                    seen[t] = {
                        "ticker": t,
                        "company_name": str(h.get("company", t)).strip(),
                        "sector": "Unknown",
                        "industry": None,
                        "market_cap": None,
                        "exchange": "NASDAQ",
                        "logo_url": None,
                        "is_active": True,
                    }
                    count += 1
            log.info("ARK %s: %d종목 수집", fund, count)
        except Exception as e:
            log.warning("ARK %s 수집 실패 (스킵): %s", fund, e)
    return list(seen.values())


def _make_row(r: dict) -> dict:
    return {
        "ticker": r["ticker"],
        "company_name": r["company_name"],
        "sector": r.get("sector", "Unknown"),
        "industry": r.get("industry"),
        "market_cap": None,
        "exchange": r.get("exchange", "NASDAQ"),
        "logo_url": None,
        "is_active": True,
    }


def upsert_batch(client, rows: list[dict], ignore_duplicates: bool = False) -> int:
    if not rows:
        return 0
    client.table("stocks").upsert(
        rows, on_conflict="ticker", ignore_duplicates=ignore_duplicates
    ).execute()
    return len(rows)


def main() -> None:
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # ── 1. S&P500 + 나스닥100 (우선순위 최상위, 섹터 정확)
    sp500 = {r["ticker"]: r for r in fetch_sp500_rows()}
    log.info("S&P500: %d종목", len(sp500))
    ndx100 = {r["ticker"]: r for r in fetch_nasdaq100_rows()}
    log.info("나스닥100: %d종목", len(ndx100))

    merged = {**ndx100, **sp500}
    for ticker in ndx100:
        if ticker in merged:
            merged[ticker]["exchange"] = "NASDAQ"

    base_rows = list(merged.values())
    log.info("S&P500+NDX100 합산: %d종목", len(base_rows))

    total = 0
    for i in range(0, len(base_rows), BATCH_SIZE):
        total += upsert_batch(client, base_rows[i:i + BATCH_SIZE])
    log.info("S&P500+NDX100 upsert 완료: %d행", total)

    # ── 2. S&P MidCap 400 (신규만 INSERT — 섹터 정보 있으므로 ignore_duplicates=False로 upsert)
    midcap_rows = fetch_midcap400_rows()
    log.info("미드캡400: %d종목", len(midcap_rows))
    midcap_new = 0
    for i in range(0, len(midcap_rows), BATCH_SIZE):
        midcap_new += upsert_batch(client, midcap_rows[i:i + BATCH_SIZE], ignore_duplicates=True)
    log.info("미드캡400 upsert 완료: %d행", midcap_new)

    # ── 3. ARK ETF 보유종목 (신규만 INSERT, 기존 레코드 덮어쓰지 않음)
    ark_rows = fetch_ark_rows()
    log.info("ARK 수집: %d종목", len(ark_rows))
    ark_new = 0
    for i in range(0, len(ark_rows), BATCH_SIZE):
        ark_new += upsert_batch(client, ark_rows[i:i + BATCH_SIZE], ignore_duplicates=True)
    log.info("ARK upsert 완료: %d행", ark_new)

    # ── 3. 큐레이션 성장주 (신규만 INSERT)
    curated_rows = [_make_row(r) for r in CURATED_STOCKS]
    log.info("큐레이션: %d종목", len(curated_rows))
    curated_new = 0
    for i in range(0, len(curated_rows), BATCH_SIZE):
        curated_new += upsert_batch(client, curated_rows[i:i + BATCH_SIZE], ignore_duplicates=True)
    log.info("큐레이션 upsert 완료: %d행", curated_new)

    log.info("전체 완료: base=%d + midcap=%d + ark=%d + curated=%d", total, midcap_new, ark_new, curated_new)


if __name__ == "__main__":
    main()
