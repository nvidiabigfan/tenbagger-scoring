import pytest
import yaml
from pathlib import Path

from app.analyzers.dummy import DummyAnalyzer
from app.scoring.engine import ScoringEngine


@pytest.fixture
def weights_file(tmp_path: Path) -> Path:
    config = {
        "modules": {
            "etf":     {"weight": 20, "enabled": True},
            "analyst": {"weight": 25, "enabled": True},
            "reddit":  {"weight": 30, "enabled": False},
            "youtube": {"weight": 25, "enabled": False},
        },
        "scoring": {
            "strong_buy_threshold": 75,
            "buy_threshold": 55,
            "hold_threshold": 35,
            "min_confidence": 0.3,
        },
    }
    p = tmp_path / "weights.yaml"
    p.write_text(yaml.dump(config))
    return p


def make_engine(weights_file: Path, etf_score: float = 60.0, analyst_score: float = 80.0) -> ScoringEngine:
    return ScoringEngine(
        analyzers=[DummyAnalyzer("etf", etf_score), DummyAnalyzer("analyst", analyst_score)],
        weights_path=weights_file,
    )


def test_active_modules_only(weights_file: Path):
    engine = make_engine(weights_file)
    result = engine.analyze("AAPL")
    assert set(result.active_modules) == {"etf", "analyst"}


def test_weighted_score_normalization(weights_file: Path):
    # etf(20)*60 + analyst(25)*80 = 1200+2000=3200 / 45 = 71.11
    engine = make_engine(weights_file, etf_score=60.0, analyst_score=80.0)
    result = engine.analyze("AAPL")
    assert abs(result.total_score - 71.11) < 0.1


def test_signal_buy(weights_file: Path):
    engine = make_engine(weights_file, etf_score=60.0, analyst_score=80.0)
    result = engine.analyze("AAPL")
    assert result.signal == "buy"   # 71.11 → buy (55~75)


def test_signal_strong_buy(weights_file: Path):
    engine = make_engine(weights_file, etf_score=90.0, analyst_score=90.0)
    result = engine.analyze("NVDA")
    assert result.signal == "strong_buy"


def test_signal_hold(weights_file: Path):
    engine = make_engine(weights_file, etf_score=35.0, analyst_score=35.0)
    result = engine.analyze("XYZ")
    assert result.signal == "hold"


def test_ticker_uppercase(weights_file: Path):
    engine = make_engine(weights_file)
    result = engine.analyze("aapl")
    assert result.ticker == "AAPL"


def test_duration_recorded(weights_file: Path):
    engine = make_engine(weights_file)
    result = engine.analyze("MSFT")
    assert result.analysis_duration_ms >= 0


def test_low_confidence_module_excluded(weights_file: Path):
    """confidence < min_confidence(0.3) 모듈은 가중평균에서 제외되어야 함."""
    # etf(weight=20) confidence=0.0 → excluded / analyst(weight=25) confidence=0.5 → included
    # 결과: analyst 점수만 반영 → 80.0
    engine = ScoringEngine(
        analyzers=[
            DummyAnalyzer("etf", fixed_score=0.0, fixed_confidence=0.0),
            DummyAnalyzer("analyst", fixed_score=80.0, fixed_confidence=0.5),
        ],
        weights_path=weights_file,
    )
    result = engine.analyze("AAPL")
    assert abs(result.total_score - 80.0) < 0.1, f"expected 80.0, got {result.total_score}"


def test_all_low_confidence_returns_zero(weights_file: Path):
    """모든 모듈이 confidence < min_confidence 이면 score=0."""
    engine = ScoringEngine(
        analyzers=[
            DummyAnalyzer("etf", fixed_score=90.0, fixed_confidence=0.0),
            DummyAnalyzer("analyst", fixed_score=90.0, fixed_confidence=0.1),
        ],
        weights_path=weights_file,
    )
    result = engine.analyze("AAPL")
    assert result.total_score == 0.0
