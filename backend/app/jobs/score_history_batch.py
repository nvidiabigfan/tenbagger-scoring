"""주간 성장 점수 스냅샷 저장.

GitHub Actions weekly-batch.yml (월요일 UTC 01:00) 에서 실행.
흐름:
  1. analysis_results 에서 최근 7일 내 분석 결과 조회 (ticker당 최신 1건)
  2. module_scores 에서 모듈별 점수 조회 → JSONB 빌드
  3. score_history 에 week_date(이번 주 월요일) 기준 upsert
재분석 없이 기존 캐시 데이터만 스냅샷하므로 API 소모 없음.
"""

import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_BATCH_SIZE = 500  # Supabase IN 절 최대 권장 크기


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def run() -> None:
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    week_date = _monday_of_week(date.today()).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    log.info("score_history_batch: week_date=%s, cutoff=%s", week_date, cutoff)

    # 1. 최근 7일 분석 결과 전체 조회
    res = (
        client.table("analysis_results")
        .select("id, ticker, total_score, signal, confidence, analyzed_at")
        .gte("analyzed_at", cutoff)
        .order("analyzed_at", desc=True)
        .limit(5000)
        .execute()
    )
    rows_all = res.data or []
    log.info("  최근 7일 분석 건수: %d", len(rows_all))

    if not rows_all:
        log.warning("분석 데이터 없음 — 스킵")
        return

    # ticker당 최신 1건만 유지
    latest: dict[str, dict] = {}
    for row in rows_all:
        ticker = row["ticker"]
        if ticker not in latest or row["analyzed_at"] > latest[ticker]["analyzed_at"]:
            latest[ticker] = row
    log.info("  유니크 ticker: %d", len(latest))

    # 2. module_scores 조회 (analysis_id 배치)
    analysis_ids = [r["id"] for r in latest.values()]
    modules_by_analysis: dict[str, dict] = defaultdict(dict)

    for i in range(0, len(analysis_ids), _BATCH_SIZE):
        batch_ids = analysis_ids[i : i + _BATCH_SIZE]
        ms_res = (
            client.table("module_scores")
            .select("analysis_id, module_name, score")
            .in_("analysis_id", batch_ids)
            .execute()
        )
        for ms in ms_res.data or []:
            modules_by_analysis[ms["analysis_id"]][ms["module_name"]] = float(ms["score"])

    # 3. score_history upsert rows 빌드
    upsert_rows = []
    for ticker, ar in latest.items():
        upsert_rows.append(
            {
                "ticker": ticker,
                "week_date": week_date,
                "total_score": float(ar["total_score"]),
                "signal": ar.get("signal"),
                "confidence": float(ar["confidence"]) if ar.get("confidence") else None,
                "modules": modules_by_analysis.get(ar["id"], {}),
            }
        )

    # 4. 배치 upsert
    saved = 0
    for i in range(0, len(upsert_rows), _BATCH_SIZE):
        batch = upsert_rows[i : i + _BATCH_SIZE]
        client.table("score_history").upsert(
            batch, on_conflict="ticker,week_date"
        ).execute()
        saved += len(batch)

    log.info("score_history_batch 완료: 저장=%d rows (week=%s)", saved, week_date)


if __name__ == "__main__":
    run()
