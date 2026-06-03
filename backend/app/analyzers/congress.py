"""미 의회(상·하원) 매매 모듈 (CongressAnalyzer).

STOCK Act 공시 기반(Quiver Quantitative). congress_trades 테이블에 누적된
최근 90일 거래를 모아 티커별 의회 순매수(net buy)를 점수화한다.

성격:
- 공시지연 중앙값 24일 → **후행/확인 지표**. 가중치를 낮게(2점) 둔다.
- 데이터·집계는 congress_collect_batch 배치가 이미 적재. 여기선 조회·점수화만.

점수 기준(net = 매수건수 - 매도건수, 최근 90일):
  net >= +5  → 100pt (다수 의원 순매수)
  net  0     → 50pt  (중립)
  net <= -5  → 0pt   (순매도)
  선형 보간. 참여 의원 수(breadth)가 많을수록 신뢰도 상향.
거래 자체가 없으면 confidence=0 → 엔진이 가중평균에서 자동 제외.
"""

import logging

from app.analyzers.base import Analyzer, AnalyzerResult
from app.db import client as db

log = logging.getLogger(__name__)


def _congress_score(net: int) -> float:
    """net(매수-매도)을 ±5 구간에서 0~100으로 선형 매핑."""
    clamped = max(-5, min(5, net))
    return 50.0 + clamped * 10.0


def _signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 50:
        return "buy"
    if score >= 30:
        return "hold"
    return "sell"


class CongressAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "congress"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            agg = db.get_congress_netbuy(ticker, since_days=90)

            if agg["trades"] == 0:
                return AnalyzerResult(
                    score=50.0, signal="hold",
                    evidence={"note": "최근 90일 의회 매매 내역 없음"},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            score = _congress_score(agg["net"])

            # 후행 지표 → 신뢰도 상한 0.6. 거래 건수·참여 의원 수로 가산.
            total = agg["buys"] + agg["sells"]
            confidence = min(0.6, 0.25 + 0.05 * total + 0.05 * agg["buy_reps"])

            return AnalyzerResult(
                score=round(score, 2),
                signal=_signal(score),
                evidence={
                    "net_buy": agg["net"],
                    "buys": agg["buys"],
                    "sells": agg["sells"],
                    "buy_reps": agg["buy_reps"],
                    "avg_excess_return_pct": agg["avg_excess_return"],
                    "window_days": 90,
                },
                confidence=round(confidence, 3),
                timestamp=self.now_utc(),
            )

        except Exception as e:
            log.error("[%s] congress 분석 오류: %s", ticker, e)
            return AnalyzerResult(
                score=50.0, signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )
