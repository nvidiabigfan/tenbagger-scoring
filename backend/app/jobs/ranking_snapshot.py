"""
랭킹 스냅샷 생성 배치.
GitHub Actions daily-batch.yml → ranking-snapshot job에서 실행.
수동 실행: python -m app.jobs.ranking_snapshot
"""

import logging
import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOP_N = 100


def _get_client():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def run(snapshot_date: date | None = None) -> None:
    target = snapshot_date or date.today()
    log.info("ranking_snapshot: %s 기준 실행", target)

    client = _get_client()

    # 1. 종목별 최신 분석 결과 (ticker당 가장 최근 1개)
    # limit=5000으로 Supabase 기본 1000행 제한 우회
    res = (
        client.table("analysis_results")
        .select("ticker, total_score, analyzed_at")
        .order("analyzed_at", desc=True)
        .limit(5000)
        .execute()
    )
    if not res.data:
        log.warning("분석 데이터 없음 — 스킵")
        return

    # ticker별 최신 점수만 유지
    seen: dict[str, float] = {}
    for row in res.data:
        t = row["ticker"]
        if t not in seen:
            seen[t] = float(row["total_score"])

    # 상위 TOP_N 정렬
    ranked = sorted(seen.items(), key=lambda x: x[1], reverse=True)[:TOP_N]

    # 2. 전일 순위 조회 (rank_change 계산용)
    yesterday = (target - timedelta(days=1)).isoformat()
    prev_res = (
        client.table("ranking_snapshots")
        .select("ticker, rank")
        .eq("date", yesterday)
        .execute()
    )
    prev_rank: dict[str, int] = {r["ticker"]: r["rank"] for r in (prev_res.data or [])}

    # 3. 오늘 스냅샷 rows 구성
    rows = []
    for rank, (ticker, score) in enumerate(ranked, start=1):
        prev = prev_rank.get(ticker)
        rank_change = (prev - rank) if prev is not None else None
        rows.append(
            {
                "date": target.isoformat(),
                "rank": rank,
                "ticker": ticker,
                "score": score,
                "rank_change": rank_change,
            }
        )

    # 4. upsert (같은 날 재실행 시 덮어쓰기)
    client.table("ranking_snapshots").upsert(rows, on_conflict="date,rank").execute()
    log.info("ranking_snapshot: %d개 저장 완료 (%s)", len(rows), target)


if __name__ == "__main__":
    run()
