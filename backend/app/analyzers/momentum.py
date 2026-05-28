"""주가 모멘텀 모듈 (MomentumAnalyzer).

Finviz 성과 지표 기반 단기~중기 모멘텀 측정.
- Perf: 1W/1M/3M 수익률 (-30%=0pt, 0%=50pt, +30%=100pt)
- RSI(14): 45~65 모멘텀 구간 = 100pt
- 52W Range position: 52W 고점 근접도
"""

import logging
import re

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)


def _parse_pct(raw: str | None) -> float | None:
    """'+5.23%' / '-3.41%' / '12.50' → float."""
    if not raw or raw in ("-", "N/A", ""):
        return None
    try:
        return float(re.sub(r"[+%\s]", "", raw))
    except ValueError:
        return None


def _perf_to_score(pct: float) -> float:
    """수익률 % → 0~100점. -30%=0, 0%=50, +30%=100."""
    return max(0.0, min(100.0, (pct + 30) / 60 * 100))


def _rsi_score(rsi: float) -> float:
    """RSI → 0~100점. 45~65 구간 최고점."""
    if 45 <= rsi <= 65:
        return 100.0
    if 30 <= rsi < 45:
        return 50.0 + (rsi - 30) / 15 * 50
    if 65 < rsi <= 75:
        return 100.0 - (rsi - 65) / 10 * 50
    return max(0.0, 30.0 - abs(rsi - 50) * 0.5)


def _range_score(high_pct: float, low_pct: float) -> float:
    """52W 범위 내 위치 → 0~100점.

    Finviz: 52W High = % below 52W high (음수), 52W Low = % above 52W low (양수).
    high_pct < 0 → -15.25 = 52W 고점 15.25% 아래
    low_pct > 0  → +45.23 = 52W 저점 45.23% 위
    """
    below_high = abs(high_pct)
    above_low = low_pct
    total = below_high + above_low
    if total <= 0:
        return 50.0
    return max(0.0, min(100.0, above_low / total * 100))


def _signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 50:
        return "buy"
    if score >= 30:
        return "hold"
    return "sell"


class MomentumAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "momentum"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            m = finviz.get_metrics(ticker)

            perf_1w = _parse_pct(m.get("Perf Week"))
            perf_1m = _parse_pct(m.get("Perf Month"))
            perf_3m = _parse_pct(m.get("Perf Quarter"))
            rsi_raw = _parse_pct(m.get("RSI (14)"))
            high_52 = _parse_pct(m.get("52W High"))
            low_52 = _parse_pct(m.get("52W Low"))

            # Perf composite (1W:30% 1M:40% 3M:30%)
            perf_vals = [(perf_1w, 0.30), (perf_1m, 0.40), (perf_3m, 0.30)]
            available = [(v, w) for v, w in perf_vals if v is not None]

            if not available:
                return AnalyzerResult(
                    score=50.0, signal="hold",
                    evidence={"note": "성과 데이터 없음"},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            w_total = sum(w for _, w in available)
            perf_composite = sum(_perf_to_score(v) * w for v, w in available) / w_total

            rsi_s = _rsi_score(rsi_raw) if rsi_raw is not None else 50.0
            range_s = _range_score(high_52, low_52) if (high_52 is not None and low_52 is not None) else 50.0

            # 최종 합산: perf 50% + RSI 30% + 52W 20%
            score = perf_composite * 0.50 + rsi_s * 0.30 + range_s * 0.20

            confidence = 0.9 if len(available) == 3 else 0.6

            return AnalyzerResult(
                score=round(score, 2),
                signal=_signal(score),
                evidence={
                    "perf_1w": perf_1w,
                    "perf_1m": perf_1m,
                    "perf_3m": perf_3m,
                    "perf_composite": round(perf_composite, 1),
                    "rsi": rsi_raw,
                    "rsi_score": round(rsi_s, 1),
                    "range_52w": round(range_s, 1),
                },
                confidence=confidence,
                timestamp=self.now_utc(),
            )

        except Exception as e:
            log.error("[%s] momentum 분석 오류: %s", ticker, e)
            return AnalyzerResult(
                score=50.0, signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )
