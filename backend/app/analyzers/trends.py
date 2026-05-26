"""Google Trends 관심도 분석 모듈.

데이터: pytrends (비공식 Google Trends API)
시그널 로직:
  - 최근 7일 평균 관심도(0~100 상대값) → 기본 점수
  - 최근 3일 vs 이전 4일 모멘텀 → 보너스/페널티 (±10점)
  - 상대값이므로 절대적 검색량과 무관, 종목 자체의 관심 추세를 반영
"""

import logging
import time
from datetime import datetime, timezone

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_TIMEFRAME = "today 1-m"   # 30일 → 마지막 7일 슬라이싱


class TrendsAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "trends"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("TrendsAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        from pytrends.request import TrendReq

        # retries/backoff_factor 파라미터는 urllib3 2.x와 충돌 → 제거, tenacity로 재시도
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        kw = f"{ticker} stock"
        pt.build_payload([kw], timeframe=_TIMEFRAME, geo="US")
        df: pd.DataFrame = _fetch_interest(pt)

        if df.empty or kw not in df.columns:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_data"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        series = df[kw].dropna().tail(7)
        if len(series) < 3:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "insufficient_data"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        avg_7d = float(series.mean())
        recent_3 = float(series.iloc[-3:].mean())
        prior_4 = float(series.iloc[:-3].mean()) if len(series) > 3 else avg_7d

        # 모멘텀 보너스: 최근 3일 / 이전 4일 비율 기반
        if prior_4 > 0:
            momentum_ratio = (recent_3 / prior_4) - 1.0
        else:
            momentum_ratio = 0.0

        momentum_bonus = max(-10.0, min(10.0, momentum_ratio * 20))
        score = min(100.0, max(0.0, avg_7d + momentum_bonus))
        # 데이터가 전부 0이면 신뢰도 낮음
        confidence = 0.7 if avg_7d > 5 else 0.4

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence={
                "avg_interest_7d": round(avg_7d, 1),
                "recent_3d_avg": round(recent_3, 1),
                "prior_4d_avg": round(prior_4, 1),
                "momentum_ratio": round(momentum_ratio, 3),
                "keyword": kw,
            },
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_interest(pt) -> pd.DataFrame:
    return pt.interest_over_time()


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
