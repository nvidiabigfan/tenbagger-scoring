"""애널리스트 컨센서스 분석 모듈.

데이터: Finviz (Recom 1~5 척도, Target Price, 현재가)
시그널 로직:
  - Recom: 1=Strong Buy ~ 5=Strong Sell → (5 - recom) / 4 * 70점
  - Upside: (target - current) / current → 최대 30점 가산
  - score = recom_score + upside_bonus
"""

from datetime import datetime, timezone

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

        recom_raw = finviz.parse_float(metrics.get("Recom"))
        target = finviz.parse_float(metrics.get("Target Price"))
        price = finviz.parse_float(metrics.get("Price"))

        if recom_raw is None:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_analyst_data", "raw": metrics.get("Recom")},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # Recom: 1.0(Strong Buy) ~ 5.0(Strong Sell) → 점수 반전
        recom_score = max(0.0, (5.0 - recom_raw) / 4.0 * 70.0)

        upside = 0.0
        if target and price and price > 0:
            upside = (target - price) / price

        upside_bonus = min(30.0, max(0.0, upside * 100))
        score = min(100.0, recom_score + upside_bonus)

        # confidence: Recom이 있으면 0.7 기본, target도 있으면 0.85
        confidence = 0.85 if target else 0.70

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence={
                "recom": recom_raw,
                "current_price": price,
                "target_price": target,
                "upside_pct": round(upside * 100, 1) if upside else None,
            },
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
