import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from supabase import Client, create_client

from app.scoring.engine import EngineResult


@lru_cache(maxsize=1)
def _get_client() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def get_recent_analysis(ticker: str, hours: int = 24) -> dict | None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    res = (
        _get_client()
        .table("analysis_results")
        .select("*, module_scores(*)")
        .eq("ticker", ticker)
        .gte("analyzed_at", cutoff)
        .order("analyzed_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def ensure_stock_exists(ticker: str) -> None:
    """stocks 마스터에 없는 종목을 on-demand로 등록.
    이미 섹터가 채워진 종목은 덮어쓰지 않음. Unknown이면 Finviz로 재시도."""
    from app.core import finviz as _fv

    existing = (
        _get_client().table("stocks").select("sector").eq("ticker", ticker).maybe_single().execute()
    )
    if existing.data and existing.data.get("sector") not in (None, "Unknown"):
        return  # 이미 정상 데이터 있음

    try:
        info = _fv.get_stock_info(ticker)
    except Exception:
        info = {}

    _get_client().table("stocks").upsert(
        {
            "ticker": ticker,
            "company_name": info.get("company_name", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange", "US"),
        },
        on_conflict="ticker",
    ).execute()


def save_analysis(
    result: EngineResult, trigger_source: str = "on_demand"
) -> tuple[str, str, str]:
    """Returns (analysis_id, analyzed_at_iso, report_md)."""
    ensure_stock_exists(result.ticker)
    client = _get_client()
    report_md = _build_report(result)

    ar_res = (
        client.table("analysis_results")
        .insert(
            {
                "ticker": result.ticker,
                "total_score": result.total_score,
                "signal": result.signal,
                "confidence": result.confidence,
                "trigger_source": trigger_source,
                "report_md": report_md,
                "analysis_duration_ms": result.analysis_duration_ms,
            }
        )
        .execute()
    )
    row = ar_res.data[0]
    analysis_id: str = row["id"]
    analyzed_at: str = row["analyzed_at"]

    if result.module_results:
        module_rows = [
            {
                "analysis_id": analysis_id,
                "module_name": name,
                "score": r.score,
                "signal": r.signal,
                "confidence": r.confidence,
                "evidence": r.evidence,
                "data_collected_at": r.timestamp.isoformat(),
                "schema_version": r.schema_version,
            }
            for name, r in result.module_results.items()
        ]
        client.table("module_scores").insert(module_rows).execute()

    return analysis_id, analyzed_at, report_md


def get_latest_supply(ticker: str) -> dict | None:
    """최신 수급 스냅샷 1건."""
    res = (
        _get_client()
        .table("supply_snapshots")
        .select("*")
        .eq("ticker", ticker)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_supply_history(ticker: str, limit: int = 60) -> list[dict]:
    """수급 히스토리 (최신순, 최대 limit일)."""
    res = (
        _get_client()
        .table("supply_snapshots")
        .select("snapshot_date, close_price, short_interest_pct, volume_vs_avg, pc_ratio")
        .eq("ticker", ticker)
        .order("snapshot_date", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def save_supply_snapshot(data: dict) -> None:
    """수급 스냅샷 upsert (ticker+snapshot_date 유니크)."""
    _get_client().table("supply_snapshots").upsert(
        data, on_conflict="ticker,snapshot_date"
    ).execute()


def _build_report(result: EngineResult) -> str:
    signal_display = {
        "strong_buy": "강한 주목 시그널",
        "buy": "긍정 시그널",
        "hold": "중립",
        "sell": "부정 시그널",
    }.get(result.signal, result.signal)

    lines = [
        f"# {result.ticker} 분석 리포트",
        "",
        "| 항목 | 값 |",
        "|------|-----|",
        f"| 통합 점수 | **{result.total_score}/100** |",
        f"| 시그널 | {signal_display} |",
        f"| 신뢰도 | {result.confidence:.0%} |",
        "",
        "## 모듈별 분석",
        "",
    ]

    for name, r in result.module_results.items():
        ev_lines = "  \n".join(
            f"  {k}: {v}"
            for k, v in r.evidence.items()
            if v is not None and k not in ("error", "note", "keyword")
        )
        lines += [
            f"### {name.upper()}",
            f"- 점수: {r.score}/100 · 신뢰도: {r.confidence:.0%}",
            f"- 근거:\n{ev_lines}" if ev_lines else "- 근거: 없음",
            "",
        ]

    lines += [
        "---",
        "*본 서비스는 투자 자문이 아니며 참고용입니다.*",
    ]
    return "\n".join(lines)
