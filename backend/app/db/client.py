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


def save_analysis(
    result: EngineResult, trigger_source: str = "on_demand"
) -> tuple[str, str, str]:
    """Returns (analysis_id, analyzed_at_iso, report_md)."""
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
        lines += [
            f"### {name.upper()}",
            f"- 점수: {r.score}/100 · 신뢰도: {r.confidence:.0%}",
            f"- 근거: `{r.evidence}`",
            "",
        ]

    lines += [
        "---",
        "*본 서비스는 투자 자문이 아니며 참고용입니다.*",
    ]
    return "\n".join(lines)
