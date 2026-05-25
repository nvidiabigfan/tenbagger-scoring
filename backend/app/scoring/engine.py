import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.analyzers.base import Analyzer, AnalyzerResult, Signal


@dataclass
class EngineResult:
    ticker: str
    total_score: float
    signal: Signal
    confidence: float
    module_results: dict[str, AnalyzerResult]
    active_modules: list[str]
    analysis_duration_ms: int


class ScoringEngine:
    def __init__(self, analyzers: list[Analyzer], weights_path: Path | None = None):
        self._analyzers: dict[str, Analyzer] = {a.name: a for a in analyzers}
        path = weights_path or Path(__file__).parent / "weights.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        self._module_cfg: dict[str, dict] = config["modules"]
        self._scoring_cfg: dict = config["scoring"]

    def _active_modules(self) -> list[str]:
        return [
            name
            for name, cfg in self._module_cfg.items()
            if cfg.get("enabled", False) and name in self._analyzers
        ]

    def _weighted_score(self, results: dict[str, AnalyzerResult], active: list[str]) -> float:
        total_weight = sum(self._module_cfg[m]["weight"] for m in active)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(
            results[m].score * self._module_cfg[m]["weight"] for m in active
        )
        return round(weighted_sum / total_weight, 2)

    def _avg_confidence(self, results: dict[str, AnalyzerResult], active: list[str]) -> float:
        if not active:
            return 0.0
        return round(sum(results[m].confidence for m in active) / len(active), 3)

    def _to_signal(self, score: float) -> Signal:
        c = self._scoring_cfg
        if score >= c["strong_buy_threshold"]:
            return "strong_buy"
        if score >= c["buy_threshold"]:
            return "buy"
        if score >= c["hold_threshold"]:
            return "hold"
        return "sell"

    def analyze(self, ticker: str) -> EngineResult:
        ticker = ticker.upper().strip()
        active = self._active_modules()
        t0 = time.monotonic()

        results: dict[str, AnalyzerResult] = {}
        for name in active:
            results[name] = self._analyzers[name].analyze(ticker)

        total_score = self._weighted_score(results, active)
        confidence = self._avg_confidence(results, active)
        signal = self._to_signal(total_score)
        duration_ms = int((time.monotonic() - t0) * 1000)

        return EngineResult(
            ticker=ticker,
            total_score=total_score,
            signal=signal,
            confidence=confidence,
            module_results=results,
            active_modules=active,
            analysis_duration_ms=duration_ms,
        )
