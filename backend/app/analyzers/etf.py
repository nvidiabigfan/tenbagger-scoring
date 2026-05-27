"""ETF·기관 수요 변화 분석 모듈.

시그널 로직 (상대적 변화 측정):
  - Inst Trans (%): 분기 기관 순매수 변화율 → 핵심 지표 (0~60점)
    -10% 이하=0점, 0%=30점, +10% 이상=60점
  - Rel Volume: 현재 거래량 / 평균 거래량 → 시장 관심 변화 (0~20점)
    0.5 이하=0점, 1.0=10점, 1.5 이상=20점
  - Inst Own (%): 기관 보유 비중 → 보조 (0~15점)
  - Index 편입 여부 → 보조 (0~5점)
"""

from datetime import datetime, timezone

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz


class EtfAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "etf"

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

        inst_trans = finviz.parse_float(metrics.get("Inst Trans"))  # % 변화 (분기)
        rel_volume = finviz.parse_float(metrics.get("Rel Volume"))  # 현재/평균 거래량
        inst_own = finviz.parse_float(metrics.get("Inst Own"))      # 기관 보유 비중 %
        index_str = metrics.get("Index", "")

        if inst_trans is None and inst_own is None:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_inst_data"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # 핵심: 분기 기관 순매수 변화율 → 0~60점
        # -10% → 0점, 0% → 30점, +10% → 60점 (선형)
        if inst_trans is not None:
            inst_trans_score = max(0.0, min(60.0, (inst_trans + 10.0) * 3.0))
        else:
            inst_trans_score = 30.0  # 데이터 없으면 중립

        # 거래량 모멘텀: Rel Volume → 0~20점
        # 0.5 → 0점, 1.0 → 10점, 1.5+ → 20점
        if rel_volume is not None:
            rel_volume_score = max(0.0, min(20.0, (rel_volume - 0.5) * 20.0))
        else:
            rel_volume_score = 10.0  # 데이터 없으면 중립

        # 기관 보유 비중 보조 → 0~15점 (100% = 15점)
        inst_own_score = min(15.0, inst_own * 0.15) if inst_own is not None else 0.0

        # 주요 지수 편입 보너스 → 0~5점
        index_bonus = 5.0 if ("S&P" in index_str or "NDX" in index_str) else 0.0

        score = min(100.0, inst_trans_score + rel_volume_score + inst_own_score + index_bonus)

        # confidence: inst_trans가 핵심, 없으면 낮음
        confidence = 0.85 if inst_trans is not None else 0.55

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence={
                "inst_trans_pct": inst_trans,
                "rel_volume": rel_volume,
                "inst_own_pct": inst_own,
                "index": index_str or None,
                "inst_trans_score": round(inst_trans_score, 1),
                "rel_volume_score": round(rel_volume_score, 1),
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
