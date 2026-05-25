from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Signal = Literal["strong_buy", "buy", "hold", "sell"]


@dataclass
class AnalyzerResult:
    score: float           # 0~100
    signal: Signal
    evidence: dict[str, Any]
    confidence: float      # 0~1
    timestamp: datetime
    schema_version: str = "1.0"


class Analyzer(ABC):
    """모든 분석 모듈의 공통 인터페이스 (허브-스포크 스포크)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """weights.yaml 키와 반드시 일치."""
        ...

    @abstractmethod
    def analyze(self, ticker: str) -> AnalyzerResult:
        """
        ticker: 검증된 대문자 알파벳 (A-Z + 점 1개 이내, 5자 이하).
        외부 API 오류 시 confidence=0, score=0 으로 graceful fail.
        절대 예외를 caller까지 전파하지 말 것.
        """
        ...

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)
