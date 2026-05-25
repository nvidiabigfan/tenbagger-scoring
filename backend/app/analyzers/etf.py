"""ETF 편입 분석 모듈.

데이터: Finviz (Inst Own %, Inst Trans %)
시그널 로직:
  - 기관 보유 비중(Inst Own)이 높을수록 ETF 포함 패시브 수요 강함
  - 기관 순매수 변화(Inst Trans) 양수면 가산점
  - S&P500 / 나스닥100 편입 여부 자체가 강한 패시브 수요 신호
  - score = inst_own_score + trans_bonus + index_bonus
"""

from datetime import datetime, timezone

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

# S&P500·나스닥100 포함 여부 체크용 (종목 마스터 import 시 exchange 세팅)
MAJOR_INDEX_EXCHANGES = {"NYSE", "NASDAQ"}


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

        inst_own = finviz.parse_float(metrics.get("Inst Own"))   # % (e.g. 67.2)
        inst_trans = finviz.parse_float(metrics.get("Inst Trans"))  # % 변화 (e.g. 2.5)
        shr_float = finviz.parse_float(metrics.get("Shs Float"))   # float 주식 수 (M)
        # index 편입 여부: finviz "Index" 컬럼 (S&P 500, DJIA, NDX 등)
        index_str = metrics.get("Index", "")

        if inst_own is None:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_inst_data"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # inst_own 기반 기본 점수 (70% 이상 → 70점)
        inst_own_score = min(70.0, inst_own)

        # 기관 순매수 변화 보너스 (최대 15점)
        trans_bonus = 0.0
        if inst_trans is not None:
            trans_bonus = min(15.0, max(-15.0, inst_trans * 3))

        # 주요 지수 편입 보너스
        index_bonus = 0.0
        if "S&P" in index_str:
            index_bonus += 10.0
        if "NDX" in index_str or "Nasdaq" in index_str.lower():
            index_bonus += 5.0

        score = min(100.0, max(0.0, inst_own_score + trans_bonus + index_bonus))
        confidence = 0.8 if inst_trans is not None else 0.6

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence={
                "inst_own_pct": inst_own,
                "inst_trans_pct": inst_trans,
                "index": index_str or None,
                "shs_float_m": shr_float,
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
