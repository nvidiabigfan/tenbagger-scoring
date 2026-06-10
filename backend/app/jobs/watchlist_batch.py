"""워치리스트 일일 재분석 + 스코어 변화 알림 배치.

GitHub Actions daily-batch.yml → watchlist-reanalysis job에서 실행.
워치리스트 등록 종목 중 24h 캐시가 없는 것만 재분석 → alert_enabled 유저에게 이메일 발송.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client

from app.analyzers.analyst import AnalystAnalyzer
from app.analyzers.buzz import BuzzAnalyzer
from app.analyzers.congress import CongressAnalyzer
from app.analyzers.etf import EtfAnalyzer
from app.analyzers.insider import InsiderAnalyzer
from app.analyzers.momentum import MomentumAnalyzer
from app.analyzers.revenue import RevenueAccelerationAnalyzer
from app.analyzers.size import SizeAnalyzer
from app.core.email import send_score_alert
from app.db import client as db
from app.scoring.engine import ScoringEngine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_INTER_STOCK_SLEEP = 8.0
_DEFAULT_ALERT_THRESHOLD = 10.0  # 점수 변화 기본 임계값


def _supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def _get_watchlist() -> list[dict]:
    """watchlist 전체 조회 (user_id, ticker, alert_enabled, alert_threshold)."""
    res = _supabase().table("watchlist").select(
        "user_id, ticker, alert_enabled, alert_threshold"
    ).execute()
    return res.data or []


def _get_previous_score(ticker: str) -> float | None:
    """최근 48h 내 두 번째 분석 점수 조회 (오늘 분석 직전 점수)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    res = (
        _supabase()
        .table("analysis_results")
        .select("total_score")
        .eq("ticker", ticker)
        .gte("analyzed_at", cutoff)
        .order("analyzed_at", desc=True)
        .limit(2)
        .execute()
    )
    rows = res.data or []
    # rows[0] = 방금 저장한 오늘 분석, rows[1] = 그 이전 점수
    if len(rows) >= 2:
        return float(rows[1]["total_score"])
    return None


def _get_user_email(user_id: str) -> str | None:
    try:
        res = _supabase().auth.admin.get_user_by_id(user_id)
        return res.user.email if res.user else None
    except Exception as e:
        log.error("유저 이메일 조회 실패 (%s): %s", user_id, e)
        return None


def _save_alert_history(
    user_id: str, ticker: str, old_score: float, new_score: float
) -> None:
    try:
        _supabase().table("alert_history").insert({
            "user_id": user_id,
            "ticker": ticker,
            "old_score": old_score,
            "new_score": new_score,
            "delta": new_score - old_score,
            "channel": "email",
        }).execute()
    except Exception as e:
        log.error("alert_history 저장 실패 (%s): %s", ticker, e)


def _send_alerts(
    ticker: str,
    new_score: float,
    old_score: float,
    watchlist_entries: list[dict],
) -> None:
    """해당 ticker 워치리스트 유저 중 threshold 초과 시 이메일 발송."""
    for entry in watchlist_entries:
        if entry["ticker"] != ticker:
            continue
        if not entry.get("alert_enabled"):
            continue

        threshold = float(entry.get("alert_threshold") or _DEFAULT_ALERT_THRESHOLD)
        if abs(new_score - old_score) < threshold:
            continue

        user_id = entry["user_id"]
        email = _get_user_email(user_id)
        if not email:
            continue

        sent = send_score_alert(email, ticker, old_score, new_score)
        if sent:
            _save_alert_history(user_id, ticker, old_score, new_score)


def run() -> None:
    watchlist = _get_watchlist()
    if not watchlist:
        log.info("watchlist_batch: 워치리스트 없음 — 스킵")
        return

    tickers = list({e["ticker"] for e in watchlist})
    log.info("watchlist_batch: %d개 종목 / %d개 항목 대상", len(tickers), len(watchlist))

    engine = ScoringEngine([
        RevenueAccelerationAnalyzer(), EtfAnalyzer(), AnalystAnalyzer(),
        SizeAnalyzer(), MomentumAnalyzer(), BuzzAnalyzer(), InsiderAnalyzer(),
        CongressAnalyzer(),
    ])

    ok = fail = cached = 0
    for ticker in tickers:
        if db.get_recent_analysis(ticker):
            log.info("[%s] 캐시 히트 — 스킵", ticker)
            cached += 1
            continue

        # 분석 전 이전 점수 기록
        old_score_pre = _get_previous_score(ticker)

        try:
            log.info("[%s] 분석 시작", ticker)
            result = engine.analyze(ticker)
            db.save_analysis(result, trigger_source="scheduled")
            new_score = result.total_score
            log.info("[%s] 저장 완료 (score=%.1f)", ticker, new_score)
            ok += 1

            # 알림 발송
            if old_score_pre is not None:
                _send_alerts(ticker, new_score, old_score_pre, watchlist)
            else:
                log.info("[%s] 이전 점수 없음 — 알림 스킵", ticker)

        except Exception as e:
            log.error("[%s] 오류: %s", ticker, e)
            fail += 1

        time.sleep(_INTER_STOCK_SLEEP)

    log.info("watchlist_batch 완료: 성공=%d, 실패=%d, 캐시=%d", ok, fail, cached)


if __name__ == "__main__":
    run()
