from app.analyzers.base import Analyzer, AnalyzerResult


class DummyAnalyzer(Analyzer):
    """end-to-end 흐름 검증 전용. 실제 배포 시 weights.yaml에서 비활성화."""

    def __init__(self, module_name: str = "dummy", fixed_score: float = 50.0):
        self._name = module_name
        self._fixed_score = fixed_score

    @property
    def name(self) -> str:
        return self._name

    def analyze(self, ticker: str) -> AnalyzerResult:
        return AnalyzerResult(
            score=self._fixed_score,
            signal="hold",
            evidence={"ticker": ticker, "source": "dummy"},
            confidence=0.5,
            timestamp=self.now_utc(),
        )
