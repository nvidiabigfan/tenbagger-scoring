"""시가총액 역가중 모듈 (SizeAnalyzer).

텐배거 = 아직 덜 발견된 종목의 10배 상승. 시총이 작을수록 상승 여력이 크다.
대형주(NVIDIA·Apple 등)가 전체 점수를 지배하는 것을 방지하는 핵심 보정 모듈.

점수 기준 (market_cap 기준):
  $2B 미만         : 100  ← 소형주 핵심 텐배거 구간
  $2B  ~ $10B      :  90
  $10B ~ $50B      :  70
  $50B ~ $200B     :  45
  $200B ~ $500B    :  20
  $500B ~ $1T      :   8
  $1T 이상         :   0  ← 메가캡, 텐배거 가능성 사실상 없음
"""

import logging

import yfinance as yf

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

# (상한 시총(USD), 점수)  — None은 상한 없음
_TIERS: list[tuple[float | None, float]] = [
    (2e9,   100),
    (10e9,   90),
    (50e9,   70),
    (200e9,  45),
    (500e9,  20),
    (1e12,    8),
    (None,    0),
]


def _cap_score(market_cap: float) -> float:
    for cap_limit, score in _TIERS:
        if cap_limit is None or market_cap < cap_limit:
            return score
    return 0.0


def _signal(score: float) -> str:
    if score >= 80:
        return "strong_buy"
    if score >= 60:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"


class SizeAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "size"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            info = yf.Ticker(ticker).info
            market_cap = info.get("marketCap")

            if not market_cap:
                log.warning("[%s] size: marketCap 없음 — confidence 0", ticker)
                return AnalyzerResult(
                    score=50.0,  # 정보 없으면 중립 처리
                    signal="hold",
                    evidence={"market_cap": None, "note": "데이터 없음"},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            score = _cap_score(market_cap)
            cap_b = market_cap / 1e9

            return AnalyzerResult(
                score=score,
                signal=_signal(score),
                evidence={
                    "market_cap_usd": market_cap,
                    "market_cap_b": round(cap_b, 1),
                    "tier": f"${cap_b:.0f}B",
                },
                confidence=1.0,
                timestamp=self.now_utc(),
            )

        except Exception as e:
            log.error("[%s] size 분석 오류: %s", ticker, e)
            return AnalyzerResult(
                score=50.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )
