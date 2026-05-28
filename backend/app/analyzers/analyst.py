"""애널리스트 평가 변화 분석 모듈.

시그널 로직 (상대적 변화 측정):
  - Finviz 차트 이벤트에서 1년치 ratings 이력 수집
  - 1m / 3m / 6m / 1y 구간별 net_ratio = (upgrades - downgrades) / total
  - composite = 1m×40% + 3m×30% + 6m×20% + 1y×10%  → 0~65점
  - upside_score = (목표가 - 현재가) / 현재가  → 0~20점
  - coverage_bonus = 90일간 ratings_count 증가율 비교  → 0~15점
  - ratings 이력 부족 시: 현재 Recom 기반 fallback
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)


class AnalystAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "analyst"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        metrics = finviz.get_metrics(ticker)
        target = finviz.parse_float(metrics.get("Target Price"))
        price = finviz.parse_float(metrics.get("Price"))
        recom_raw = finviz.parse_float(metrics.get("Recom"))

        upside = (target - price) / price if (target and price and price > 0) else 0.0
        upside_score = min(20.0, max(0.0, upside * 100))

        ratings = finviz.get_ratings_history(ticker)
        ratings_count_1y = len(ratings)

        if ratings_count_1y >= 2:
            score, confidence, evidence = _score_from_history(ratings, upside_score, target, price, upside)
        else:
            score, confidence, evidence = _score_from_recom(recom_raw, upside_score, target, price, upside)

        # coverage expansion 보너스 (0~15점): 90일간 커버리지 증가 감지
        coverage_bonus, coverage_evidence = _coverage_bonus(ticker, ratings_count_1y)
        score = min(100.0, score + coverage_bonus)
        evidence.update(coverage_evidence)

        # analyst density 보너스 (0~5점): 소형주에 analyst가 붙는 현상 탐지
        density_bonus, density_evidence = _density_bonus(ratings_count_1y, metrics.get("Market Cap"))
        score = min(100.0, score + density_bonus)
        evidence.update(density_evidence)

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence=evidence,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


def _coverage_bonus(ticker: str, current_count: int) -> tuple[float, dict]:
    """analyst_snapshots DB에서 90일 전 스냅샷과 비교해 coverage 증가 보너스 반환.
    DB 미연결/스냅샷 없으면 보너스 0 + 오늘자 스냅샷 저장 시도.
    """
    try:
        from supabase import create_client

        client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )

        today = date.today().isoformat()
        past_date = (date.today() - timedelta(days=90)).isoformat()

        # 오늘 스냅샷 upsert (매 분석마다 갱신)
        client.table("analyst_snapshots").upsert(
            {"ticker": ticker, "snapshot_date": today, "ratings_count_1y": current_count},
            on_conflict="ticker,snapshot_date",
        ).execute()

        # 90일 전 스냅샷 조회
        res = (
            client.table("analyst_snapshots")
            .select("ratings_count_1y, snapshot_date")
            .eq("ticker", ticker)
            .lte("snapshot_date", past_date)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )

        if not res.data:
            return 0.0, {"coverage_growth_3m": None, "coverage_count_now": current_count}

        past_count = res.data[0]["ratings_count_1y"]
        past_snap_date = res.data[0]["snapshot_date"]

        if past_count == 0:
            # 과거 0 → 현재 N : 신규 커버리지 발생, 최대 보너스
            growth = 1.0 if current_count > 0 else 0.0
        else:
            growth = (current_count - past_count) / past_count  # 음수 가능

        # 50% 성장 → 15점, 100% 성장 → 15점(상한), 감소 → 0점
        bonus = min(15.0, max(0.0, growth * 30.0))

        return round(bonus, 2), {
            "coverage_count_now": current_count,
            "coverage_count_90d_ago": past_count,
            "coverage_growth_3m": round(growth * 100, 1),
            "coverage_snapshot_date": past_snap_date,
        }
    except Exception as e:
        log.debug("coverage_bonus skip [%s]: %s", ticker, e)
        return 0.0, {"coverage_growth_3m": None, "coverage_count_now": current_count}


def _density_bonus(analyst_count: int, market_cap_raw: str | None) -> tuple[float, dict]:
    """시총 대비 analyst 수 밀도 보너스. 소형주에 analyst가 붙기 시작 = 초기 발견 신호."""
    if analyst_count == 0 or not market_cap_raw:
        return 0.0, {}
    try:
        mc = finviz.parse_market_cap(market_cap_raw)
        if mc is None or mc <= 0:
            return 0.0, {}
        mc_b = mc / 1e9
        if mc_b < 1:
            tier_max, factor = 5.0, 0.50
        elif mc_b < 10:
            tier_max, factor = 4.0, 0.40
        elif mc_b < 50:
            tier_max, factor = 2.0, 0.20
        else:
            return 0.0, {}
        bonus = min(tier_max, analyst_count * factor)
        return round(bonus, 2), {"analyst_density_bonus": round(bonus, 2), "mc_billions": round(mc_b, 1)}
    except Exception:
        return 0.0, {}


def _net_ratio(ratings: list[dict], months_back: int, months_end: int = 0) -> float | None:
    """구간 [now - months_back, now - months_end] 내 net_ratio = (up - down) / total."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=months_back * 30)
    end = now - timedelta(days=months_end * 30)
    bucket = [r for r in ratings if start <= r["date"] < end]
    total = len(bucket)
    if total == 0:
        return None
    upgrades = sum(1 for r in bucket if r["action"] in ("upgrade", "init"))
    downgrades = sum(1 for r in bucket if r["action"] == "downgrade")
    return (upgrades - downgrades) / total  # -1 ~ +1


def _score_from_history(ratings, upside_score, target, price, upside):
    net_1m = _net_ratio(ratings, 1)
    net_3m = _net_ratio(ratings, 3)
    net_6m = _net_ratio(ratings, 6)
    net_1y = _net_ratio(ratings, 12)

    def nz(v):
        return v if v is not None else 0.0

    # composite: -1 ~ +1 → 0 ~ 65점 (0 = 중립 32.5점)
    composite = (
        nz(net_1m) * 0.40
        + nz(net_3m) * 0.30
        + nz(net_6m) * 0.20
        + nz(net_1y) * 0.10
    )
    rating_score = (composite + 1) / 2 * 65

    score = min(85.0, rating_score + upside_score)  # coverage_bonus 위한 여유 (max 85 before bonus)
    has_recent = net_3m is not None
    confidence = 0.85 if has_recent else (0.70 if len(ratings) > 0 else 0.55)

    evidence = {
        "net_ratio_1m": round(net_1m, 3) if net_1m is not None else None,
        "net_ratio_3m": round(net_3m, 3) if net_3m is not None else None,
        "net_ratio_6m": round(net_6m, 3) if net_6m is not None else None,
        "net_ratio_1y": round(net_1y, 3) if net_1y is not None else None,
        "composite_net": round(composite, 3),
        "ratings_count": len(ratings),
        "target_price": target,
        "current_price": price,
        "upside_pct": round(upside * 100, 1) if upside else None,
        "mode": "history",
    }
    return score, confidence, evidence


def _score_from_recom(recom_raw, upside_score, target, price, upside):
    if recom_raw is None:
        return 0.0, 0.0, {"error": "no_analyst_data"}
    recom_score = max(0.0, (5.0 - recom_raw) / 4.0 * 65.0)
    score = min(85.0, recom_score + upside_score)
    confidence = 0.70 if target else 0.55
    evidence = {
        "recom": recom_raw,
        "target_price": target,
        "current_price": price,
        "upside_pct": round(upside * 100, 1) if upside else None,
        "mode": "recom_fallback",
    }
    return score, confidence, evidence


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
