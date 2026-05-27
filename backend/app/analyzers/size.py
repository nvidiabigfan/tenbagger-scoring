"""시가총액 비대칭 모듈 (SizeAnalyzer) — 벨커브 방식.

텐배거 sweet spot: $300M ~ $5B 구간 우대.
  $2B 부근 최고점 (100점)
  너무 작은 microcap (<$50M): fraud 리스크 → 자연 감점
  mega-cap (>$500B): 10배 여력 없음 → 자연 감점

공식: 100 × exp(−(log10(cap_b / 2))² / (2 × 1.5²))
  $300M ≈ 86점, $2B = 100점, $10B ≈ 90점, $50B ≈ 65점, $500B ≈ 28점

데이터: Finviz "Market Cap"
"""

import logging
import math
import re

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)

_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}

_TARGET_CAP_B = 2.0   # sweet spot 중심: $2B
_SIGMA        = 1.5   # log10 스케일 σ (클수록 완만)


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
    """가우시안 벨커브: $2B 중심, log10 스케일."""
    cap_b = market_cap / 1e9
    if cap_b <= 0:
        return 0.0
    log_ratio = math.log10(cap_b / _TARGET_CAP_B)
    score = 100.0 * math.exp(-(log_ratio ** 2) / (2 * _SIGMA ** 2))
    return round(max(0.0, min(100.0, score)), 2)


def _signal(score: float) -> str:
    if score >= 80:
        return "strong_buy"
    if score >= 60:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"


def _cap_zone(cap_b: float) -> str:
    if cap_b < 0.05:
        return "nano-cap"
    if cap_b < 0.3:
        return "micro-cap"
    if cap_b < 2.0:
        return "small-cap"
    if cap_b < 10.0:
        return "sweet-spot"
    if cap_b < 100.0:
        return "mid-cap"
    if cap_b < 500.0:
        return "large-cap"
    return "mega-cap"


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
                    "cap_zone": _cap_zone(cap_b),
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
