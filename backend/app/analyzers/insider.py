"""내부자 거래 모듈 (InsiderAnalyzer).

Finviz 'Insider Trans' 지표 기반 (SEC Form 4 집계 데이터).
- Insider Trans > 0: 내부자 순매수 → 강한 구조변화 신호
- Insider Trans < 0: 내부자 순매도 → 부정적 신호

점수 기준:
  > +5%  → 100pt (강한 매수)
  0~+5%  → 50~100pt 선형
  -5~0%  → 20~50pt 선형
  < -5%  → 0~20pt 선형
"""

import logging
import re

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)


def _parse_pct(raw: str | None) -> float | None:
    if not raw or raw in ("-", "N/A", ""):
        return None
    try:
        return float(re.sub(r"[+%\s]", "", raw))
    except ValueError:
        return None


def _insider_score(trans_pct: float) -> float:
    if trans_pct >= 5.0:
        return 100.0
    if trans_pct >= 0.0:
        return 50.0 + trans_pct / 5.0 * 50
    if trans_pct >= -5.0:
        return 20.0 + (trans_pct + 5.0) / 5.0 * 30
    return max(0.0, 20.0 + trans_pct * 2)


def _signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 50:
        return "buy"
    if score >= 30:
        return "hold"
    return "sell"


class InsiderAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "insider"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            m = finviz.get_metrics(ticker)

            insider_trans = _parse_pct(m.get("Insider Trans"))
            insider_own = _parse_pct(m.get("Insider Own"))

            if insider_trans is None:
                return AnalyzerResult(
                    score=50.0, signal="hold",
                    evidence={"note": "Insider Trans 데이터 없음", "insider_own": insider_own},
                    confidence=0.0,
                    timestamp=self.now_utc(),
                )

            score = _insider_score(insider_trans)

            return AnalyzerResult(
                score=round(score, 2),
                signal=_signal(score),
                evidence={
                    "insider_trans_pct": insider_trans,
                    "insider_own_pct": insider_own,
                },
                confidence=0.9,
                timestamp=self.now_utc(),
            )

        except Exception as e:
            log.error("[%s] insider 분석 오류: %s", ticker, e)
            return AnalyzerResult(
                score=50.0, signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )
