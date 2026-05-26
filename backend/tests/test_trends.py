"""TrendsAnalyzer 단위 테스트 — pytrends를 mock해 외부 API 없이 검증."""
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.analyzers.trends import TrendsAnalyzer, _score_to_signal


def _make_series(values: list[float]) -> pd.DataFrame:
    """주간 시계열 DataFrame 생성 (oldest → newest)."""
    idx = pd.date_range(end="2026-05-26", periods=len(values), freq="W")
    return pd.DataFrame({"AAPL stock": values}, index=idx)


def _run(series_values: list[float], ticker: str = "AAPL"):
    """TrendReq + interest_over_time를 patch 후 _analyze 실행.
    _analyze 내부에서 `from pytrends.request import TrendReq`로 lazy import하므로
    실제 모듈 경로를 patch해야 함."""
    df = _make_series(series_values)
    with patch("pytrends.request.TrendReq") as MockTR:
        instance = MagicMock()
        instance.interest_over_time.return_value = df
        MockTR.return_value = instance
        analyzer = TrendsAnalyzer()
        return analyzer._analyze(ticker)


# ─── 정상 케이스 ───────────────────────────────────────────────────

class TestRateCalculation:
    def test_flat_trend_score_near_33(self):
        # 1y 동안 관심도 일정 → composite_rate ≈ 0 → score ≈ 33
        values = [50.0] * 52
        result = _run(values)
        assert 30 <= result.score <= 37, f"score={result.score}"

    def test_rising_trend_score_above_50(self):
        # 과거 25 → 현재 50 (2배 성장) → rate_3m ≈ +1 → score ≈ 67
        values = [25.0] * 39 + [50.0] * 13
        result = _run(values)
        assert result.score > 50

    def test_falling_trend_score_below_33(self):
        # 과거 80 → 현재 20 (75% 하락) → composite_rate < 0 → score < 33
        values = [80.0] * 39 + [20.0] * 13
        result = _run(values)
        assert result.score < 33

    def test_strong_rise_score_near_100(self):
        # 과거 10 → 현재 50 (5배): rate ≈ 4 → clamp to 100
        values = [10.0] * 39 + [50.0] * 13
        result = _run(values)
        assert result.score >= 90

    def test_evidence_has_required_keys(self):
        values = [40.0] * 52
        result = _run(values)
        ev = result.evidence
        assert "composite_rate" in ev
        assert "rate_3m" in ev
        assert "avg_3m" in ev
        assert "keyword" in ev


class TestConfidence:
    def test_high_interest_confidence_075(self):
        values = [50.0] * 52
        result = _run(values)
        assert result.confidence == 0.75

    def test_low_interest_confidence_04(self):
        # Q4 평균 < 5
        values = [3.0] * 52
        result = _run(values)
        assert result.confidence == 0.4


# ─── 엣지 케이스 ───────────────────────────────────────────────────

class TestEdgeCases:
    def test_insufficient_data_returns_zero(self):
        # 13주 미만 → score=0, confidence=0
        values = [50.0] * 10
        result = _run(values)
        assert result.score == 0.0
        assert result.confidence == 0.0
        assert "error" in result.evidence

    def test_no_data_empty_df(self):
        with patch("pytrends.request.TrendReq") as MockTR:
            instance = MagicMock()
            instance.interest_over_time.return_value = pd.DataFrame()
            MockTR.return_value = instance
            result = TrendsAnalyzer()._analyze("AAPL")
        assert result.score == 0.0
        assert result.evidence.get("error") == "no_data"

    def test_exception_returns_graceful_fail(self):
        with patch("pytrends.request.TrendReq", side_effect=RuntimeError("boom")):
            result = TrendsAnalyzer().analyze("AAPL")
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_zero_base_period_no_crash(self):
        # 과거 구간 전부 0 → safe_rate None → 가용 기간만 계산
        values = [0.0] * 39 + [30.0] * 13
        result = _run(values)
        # rate_3m=None (q3_avg=0 → base<1), 나머지도 None → no_valid_rate or score from q2/q1
        # 어느 경우든 crash 없어야 함
        assert isinstance(result.score, float)

    def test_score_clamped_0_to_100(self):
        for vals in ([0.0] * 52, [100.0] * 52):
            result = _run(vals)
            assert 0.0 <= result.score <= 100.0


# ─── signal 매핑 ────────────────────────────────────────────────────

class TestSignalMapping:
    @pytest.mark.parametrize("score,expected", [
        (80, "strong_buy"),
        (60, "buy"),
        (45, "hold"),
        (20, "sell"),
    ])
    def test_signal(self, score, expected):
        assert _score_to_signal(score) == expected
