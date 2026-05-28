"""Finviz 스냅샷 파서.

단일 종목 기본 지표를 Finviz quote 페이지에서 파싱.
반환값 예시: {"Recom": "1.27", "Target Price": "304.50", "Inst Own": "69.21%", "Index": "DJIA, NDX, S&P 500", ...}
get_ratings_history(): 차트 이벤트에서 analyst ratings 변경 이력 반환.
"""

import json
import re
from datetime import datetime, timezone

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


def get_ratings_history(ticker: str) -> list[dict]:
    """Finviz 차트 이벤트에서 analyst ratings 변경 이력 반환.

    반환 형식: [{"date": datetime, "action": "Upgrade"|"Downgrade"|"Reiterate"|"Init", "analyst": str, "target": float|None}]
    최근 1~2년치 주요 변경 포함. 데이터 없으면 빈 리스트.
    """
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    r = httpx.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return _parse_ratings_history(r.text)


def _parse_ratings_history(html: str) -> list[dict]:
    pattern = r'\{"dateTimestamp":(\d+),"eventType":"chartEvent/ratings","ratings":\[([^\]]+)\]\}'
    results = []
    for ts_str, ratings_json_str in re.findall(pattern, html):
        ts = int(ts_str)
        date = datetime.fromtimestamp(ts, tz=timezone.utc)
        try:
            ratings = json.loads(f"[{ratings_json_str}]")
        except json.JSONDecodeError:
            continue
        for entry in ratings:
            action_raw = entry.get("action", "")
            action = _normalize_action(action_raw)
            target_str = entry.get("targetPrice", "").replace("$", "").replace(",", "")
            target = None
            try:
                if target_str:
                    target = float(target_str)
            except ValueError:
                pass
            results.append({
                "date": date,
                "action": action,
                "analyst": entry.get("analyst", ""),
                "target": target,
            })
    results.sort(key=lambda x: x["date"], reverse=True)
    return results


def _normalize_action(raw: str) -> str:
    low = raw.lower()
    if low in ("upgrade",):
        return "upgrade"
    if low in ("downgrade",):
        return "downgrade"
    if low in ("initiated", "init", "initiate"):
        return "init"
    if low in ("reiterate", "reiterates", "maintains"):
        return "reiterate"
    return "other"


def parse_float(value: str | None) -> float | None:
    if not value or value in ("-", "N/A", ""):
        return None
    cleaned = re.sub(r"[%,\s]", "", value.split()[0])
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_market_cap(value: str | None) -> float | None:
    """'5.23T' → 5.23e12, '27.3B' → 2.73e10, '500M' → 5e8. None on failure."""
    if not value or value in ("-", "N/A", ""):
        return None
    v = value.strip().upper()
    multipliers = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    for suffix, mult in multipliers.items():
        if v.endswith(suffix):
            try:
                return float(v[:-1]) * mult
            except ValueError:
                return None
    try:
        return float(v)
    except ValueError:
        return None
