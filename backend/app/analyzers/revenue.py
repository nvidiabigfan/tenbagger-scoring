"""매출 가속도 분석 모듈 (RevenueAccelerationAnalyzer).

텐배거 핵심 선행지표: 성장 "속도"가 아닌 성장 "가속도" 측정.
현재 분기 성장률이 장기 평균을 초과하는 정도를 주 신호로 사용.

데이터: Finviz (Sales Q/Q, Sales past 3/5Y, EPS Q/Q, EPS past 3/5Y, Gross Margin)
별도 API 불필요, 기존 Finviz 호출 재사용.

점수 구성:
  sales_score (0~50): 현재 매출 성장률 — 절대값 기반
  accel_score (0~30): 현재 - 5Y 평균 → 가속도 (음수 가능, floor 0)
  eps_score   (0~20): EPS Q/Q 가속도 확인
"""

import logging

from app.analyzers.base import Analyzer, AnalyzerResult
from app.core import finviz

log = logging.getLogger(__name__)


class RevenueAccelerationAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "revenue"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("RevenueAccelerationAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=self.now_utc(),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        m = finviz.get_metrics(ticker)

        sales_qoq = _pct(m.get("Sales Q/Q"))
        eps_qoq   = _pct(m.get("EPS Q/Q"))
        gross_margin = _pct(m.get("Gross Margin"))

        # "100.05% 66.90%" → (3Y avg, 5Y avg)
        sales_3y, sales_5y = _two_pct(m.get("Sales past 3/5Y"))
        eps_3y,   eps_5y   = _two_pct(m.get("EPS past 3/5Y"))

        baseline_sales = sales_5y if sales_5y is not None else sales_3y
        baseline_eps   = eps_5y   if eps_5y   is not None else eps_3y

        # 데이터 없으면 중립 처리 — 0점 패널티 없이 분모에 포함
        if sales_qoq is None:
            return AnalyzerResult(
                score=12.5, signal="hold",
                evidence={"note": "Sales Q/Q 없음 (중립 처리)"},
                confidence=0.5, timestamp=self.now_utc(),
            )

        # ── 점수 계산 ─────────────────────────────────────────
        # sales_score: 현재 분기 매출 성장률 절대값 (0~50)
        #   -50% 이하 → 0, 0% → 25, +100% → 50
        sales_score = max(0.0, min(50.0, 25.0 + sales_qoq * 0.25))

        # accel_score: 현재 성장률 vs 장기 평균 (0~30)
        #   가속도 -50% → 0, 0% → 15, +50% → 30
        if baseline_sales is not None:
            accel_delta = sales_qoq - baseline_sales
            accel_score = max(0.0, min(30.0, 15.0 + accel_delta * 0.3))
        else:
            # 장기 baseline 없음 → 현재 성장률만으로 부분 점수
            accel_score = max(0.0, min(15.0, 7.5 + sales_qoq * 0.075))

        # eps_score: EPS 가속도 (0~20)
        if eps_qoq is not None:
            if baseline_eps is not None:
                eps_delta = eps_qoq - baseline_eps
                eps_score = max(0.0, min(20.0, 10.0 + eps_delta * 0.1))
            else:
                eps_score = max(0.0, min(20.0, 10.0 + eps_qoq * 0.1))
        else:
            eps_score = 10.0  # 데이터 없으면 중립

        # neg→pos 전환 보너스: 성장 곡선이 꺾이는 순간 탐지
        transition_bonus = 0.0
        if baseline_sales is not None:
            if baseline_sales <= 0 and sales_qoq > 0:
                transition_bonus = 10.0  # 매출 음→양 전환
            elif (sales_qoq - baseline_sales) > 50:
                transition_bonus = 5.0   # 50%p 이상 급가속

        eps_flip_bonus = 0.0
        if eps_qoq is not None and baseline_eps is not None:
            if baseline_eps <= 0 and eps_qoq > 0:
                eps_flip_bonus = 5.0  # EPS 음→양 전환

        score = round(min(100.0, sales_score + accel_score + eps_score + transition_bonus + eps_flip_bonus), 2)

        # confidence: baseline 있으면 높음, 전환 감지 시 상향
        if baseline_sales is not None:
            confidence = 0.9 if transition_bonus > 0 else 0.85
        else:
            confidence = 0.6

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "sales_qoq_pct": sales_qoq,
                "sales_5y_avg_pct": sales_5y,
                "sales_3y_avg_pct": sales_3y,
                "accel_delta_pct": round(sales_qoq - baseline_sales, 2) if baseline_sales is not None else None,
                "eps_qoq_pct": eps_qoq,
                "eps_5y_avg_pct": eps_5y,
                "gross_margin_pct": gross_margin,
                "sales_score": round(sales_score, 2),
                "accel_score": round(accel_score, 2),
                "eps_score": round(eps_score, 2),
                "transition_bonus": transition_bonus if transition_bonus > 0 else None,
                "eps_flip_bonus": eps_flip_bonus if eps_flip_bonus > 0 else None,
            },
            confidence=confidence,
            timestamp=self.now_utc(),
        )


# ── 파서 헬퍼 ─────────────────────────────────────────────────

def _pct(raw: str | None) -> float | None:
    """'85.23%' → 85.23. None or '-' → None."""
    if not raw or raw.strip() in ("-", "N/A", ""):
        return None
    try:
        return float(raw.strip().rstrip("%").replace(",", ""))
    except ValueError:
        return None


def _two_pct(raw: str | None) -> tuple[float | None, float | None]:
    """'100.05% 66.90%' → (100.05, 66.90). 실패 시 (None, None)."""
    if not raw or raw.strip() in ("-", "N/A", ""):
        return None, None
    parts = raw.strip().split()
    if len(parts) == 2:
        return _pct(parts[0]), _pct(parts[1])
    if len(parts) == 1:
        return _pct(parts[0]), None
    return None, None


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
