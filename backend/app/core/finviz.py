"""Finviz 스냅샷 파서.

단일 종목 기본 지표를 Finviz quote 페이지에서 파싱.
반환값 예시: {"Recom": "1.27", "Target Price": "304.50", "Inst Own": "69.21%", "Index": "DJIA, NDX, S&P 500", ...}
"""

import re
import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)
TIMEOUT = 10


def get_metrics(ticker: str) -> dict[str, str]:
    """Finviz 스냅샷 테이블에서 key-value 지표 전부 반환."""
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    r = httpx.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return _parse_snapshot(r.text)


def _parse_snapshot(html: str) -> dict[str, str]:
    result: dict[str, str] = {}

    # 패턴 1: 레이블이 <a> 링크인 경우 → 값이 <span> 안에
    linked = re.findall(
        r'snapshot-td-label[^>]*>.*?<a[^>]*>([^<]+)</a>.*?snapshot-td-content[^>]*>(?:<[^>]+>)*([^<\s][^<]*)',
        html, re.DOTALL,
    )
    for k, v in linked:
        result[k.strip()] = v.strip()

    # 패턴 2: 레이블이 일반 텍스트인 경우 → 값이 <b> 안에 (Inst Own, Index, Inst Trans 등)
    plain = re.findall(
        r'snapshot-td-label">([^<]{2,40})</div></td><td[^>]*>.*?<b>(.*?)</b>',
        html, re.DOTALL,
    )
    for k, v in plain:
        key = k.strip()
        # <small> 등 내부 태그 제거
        val = re.sub(r"<[^>]+>", "", v).strip()
        if key and val:
            result[key] = val

    return result


def get_stock_info(ticker: str) -> dict[str, str]:
    """종목 기본 정보 반환: company_name, sector, industry, exchange."""
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    r = httpx.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return _parse_stock_info(r.text)


def _parse_stock_info(html: str) -> dict[str, str]:
    # tab-link 순서: company / sector / industry / country / size / exchange / ...
    tabs = re.findall(r"tab-link[^>]*>([^<]+)</a>", html)
    tabs = [re.sub(r"&amp;", "&", t.strip()) for t in tabs if t.strip()]

    result: dict[str, str] = {}
    if len(tabs) >= 1:
        result["company_name"] = tabs[0]
    if len(tabs) >= 2:
        result["sector"] = tabs[1]
    if len(tabs) >= 3:
        result["industry"] = tabs[2]
    if len(tabs) >= 6:
        result["exchange"] = tabs[5]
    return result


def parse_float(value: str | None) -> float | None:
    if not value or value in ("-", "N/A", ""):
        return None
    cleaned = re.sub(r"[%,\s]", "", value.split()[0])
    try:
        return float(cleaned)
    except ValueError:
        return None
