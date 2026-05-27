"""애널리스트 평가 변화 분석 모듈.

시그널 로직 (상대적 변화 측정):
  - Finviz 차트 이벤트에서 1년치 ratings 이력 수집
  - 1m / 3m / 6m / 1y 구간별 net_ratio = (upgrades - downgrades) / total
  - composite = 1m×50% + 3m×30% + 6m×20%  → 0~80점
  - upside_score = (목표가 - 현재가) / 현재가  → 0~20점
  - ratings 이력 부족 시: 현재 Recom 기반 fallback
"""

from datetime import datetime, timedelta, timezone

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz


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

        # ratings 이력 기반 점수
        ratings = finviz.get_ratings_history(ticker)
        if len(ratings) >= 2:
            score, confidence, evidence = _score_from_history(ratings, upside_score, target, price, upside)
        else:
            # fallback: 현재 Recom 절대값 기반
            score, confidence, evidence = _score_from_recom(recom_raw, upside_score, target, price, upside)

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence=evidence,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


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

    # 없는 구간은 0으로 처리 (중립)
    def coalesce(*vals):
        for v in vals:
            if v is not None:
                return v
        return 0.0

    # 가중 composite: 최근일수록 가중치 높음
    composite = (
        coalesce(net_1m) * 0.50
        + coalesce(net_3m, net_1m) * 0.30
        + coalesce(net_6m, net_3m, net_1m) * 0.20
    )
    # composite: -1 ~ +1 → 0 ~ 80점 (0 = 중립 40점)
    rating_score = (composite + 1) / 2 * 80

    score = min(100.0, rating_score + upside_score)
    confidence = 0.85 if net_1m is not None else 0.70

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
    recom_score = max(0.0, (5.0 - recom_raw) / 4.0 * 80.0)
    score = min(100.0, recom_score + upside_score)
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
