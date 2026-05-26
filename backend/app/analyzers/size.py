"""시가총액 역가중 모듈 (SizeAnalyzer).

텐배거 = 아직 덜 발견된 종목의 10배 상승. 시총이 작을수록 상승 여력이 크다.
대형주(NVIDIA·Apple 등)가 전체 점수를 지배하는 것을 방지하는 핵심 보정 모듈.

데이터: Finviz "Market Cap" (예: "3.40T", "18.41B", "540.25M")

점수 기준:
  $2B 미만         : 100  ← 소형주 핵심 텐배거 구간
  $2B  ~ $10B      :  90
  $10B ~ $50B      :  70
  $50B ~ $200B     :  45
  $200B ~ $500B    :  20
  $500B ~ $1T      :   8
  $1T 이상         :   0  ← 메가캡, 텐배거 가능성 사실상 없음
"""

import logging
import re

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)

_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}

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


def _parse_cap(raw: str) -> float | None:
    """'3.40T' / '18.41B' / '540.25M' → float(USD)."""
    m = re.fullmatch(r"([\d.]+)([KMBT]?)", raw.strip().upper())
    if not m:
        return None
    try:
        num = float(m.group(1))
        suffix = m.group(2)
        return num * _SUFFIX.get(suffix, 1)
    except ValueError:
        return None


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
            metrics = finviz.get_metrics(ticker)
            raw = metrics.get("Market Cap")

            if not raw or raw in ("-", "N/A", ""):
                log.warning("[%s] size: Market Cap 없음 — confidence 0", ticker)
                return AnalyzerResult(
                    score=50.0,
                    signal="hold",
                    evidence={"market_cap_raw": raw, "note": "데이터 없음"},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            market_cap = _parse_cap(raw)
            if market_cap is None:
                log.warning("[%s] size: Market Cap 파싱 실패 (%s)", ticker, raw)
                return AnalyzerResult(
                    score=50.0,
                    signal="hold",
                    evidence={"market_cap_raw": raw, "note": "파싱 실패"},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            score = _cap_score(market_cap)
            cap_b = market_cap / 1e9

            return AnalyzerResult(
                score=score,
                signal=_signal(score),
                evidence={
                    "market_cap_raw": raw,
                    "market_cap_b": round(cap_b, 2),
                    "market_cap_usd": int(market_cap),
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
