"""Google Trends 관심도 분석 모듈.

데이터: pytrends (비공식 Google Trends API)
시그널 로직:
  - 52주(1y) 주간 데이터를 4분기로 분할: Q4(최근 3m) / Q3(3-6m) / Q2(6-9m) / Q1(9-12m)
  - 각 기간 대비 변화율 산출: rate_3m / rate_6m / rate_1y
  - 복합 변화율(50%·3m + 30%·6m + 20%·1y) → (rate+1)/3×100 정규화
  - 절대 관심도가 낮은 종목은 confidence 하향
"""

import logging
import random
import time
from datetime import datetime, timezone

import pandas as pd
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_TIMEFRAME_1Y = "today 12-m"   # 52주 주간 데이터
_PRE_REQUEST_JITTER = (3.0, 8.0)  # 배치 모드에서 429 방지용 랜덤 대기

# 분기 슬라이싱 (최신 기준, 주 단위)
_Q4_WEEKS = 13   # 최근 3m
_Q3_WEEKS = 13   # 3-6m
_Q2_WEEKS = 13   # 6-9m
# Q1 = 나머지 (oldest ~13주)

# 복합 변화율 가중치
_W3M, _W6M, _W1Y = 0.50, 0.30, 0.20

# 절대 관심도 하한 (Q4 평균이 이 미만이면 noise 처리)
_MIN_INTEREST = 5.0


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

    def _analyze(self, ticker: str, pre_sleep: float = 0.0) -> AnalyzerResult:
        from pytrends.request import TrendReq

        if pre_sleep > 0:
            time.sleep(pre_sleep)

        # retries/backoff_factor 파라미터는 urllib3 2.x와 충돌 → 제거, tenacity로 재시도
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        kw = f"{ticker} stock"
        pt.build_payload([kw], timeframe=_TIMEFRAME_1Y, geo="US")
        df: pd.DataFrame = _fetch_interest(pt)

        if df.empty or kw not in df.columns:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_data"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        series = df[kw].dropna()
        n = len(series)
        if n < _Q4_WEEKS * 2:  # 최소 6개월치 필요
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "insufficient_data", "weeks": n},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        # 분기별 평균 (최신 → 과거 방향)
        q4_avg = float(series.iloc[-_Q4_WEEKS:].mean())
        q3_avg = float(series.iloc[-(_Q4_WEEKS + _Q3_WEEKS):-_Q4_WEEKS].mean())
        q2_avg = float(series.iloc[-(_Q4_WEEKS + _Q3_WEEKS + _Q2_WEEKS):-(_Q4_WEEKS + _Q3_WEEKS)].mean()) if n >= _Q4_WEEKS * 3 else None
        q1_avg = float(series.iloc[:n - (_Q4_WEEKS + _Q3_WEEKS + _Q2_WEEKS)].mean()) if n >= _Q4_WEEKS * 4 else None

        def safe_rate(recent: float, base: float | None) -> float | None:
            if base is None or base < 1.0:
                return None
            return (recent / base) - 1.0

        rate_3m = safe_rate(q4_avg, q3_avg)
        rate_6m = safe_rate(q4_avg, q2_avg)
        rate_1y = safe_rate(q4_avg, q1_avg)

        # 가용한 기간만 사용하여 가중치 재정규화
        weighted_rates = [
            (_W3M, rate_3m),
            (_W6M, rate_6m),
            (_W1Y, rate_1y),
        ]
        valid = [(w, r) for w, r in weighted_rates if r is not None]
        if not valid:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_valid_rate", "q4_avg": round(q4_avg, 1)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        total_w = sum(w for w, _ in valid)
        composite_rate = sum(w * r for w, r in valid) / total_w

        # 정규화: rate ∈ [-1, +2] → score ∈ [0, 100]
        # rate=-1(관심 소멸)→0점, rate=0(보합)→33점, rate=+1(2배)→67점, rate=+2(3배)→100점
        raw_score = (composite_rate + 1.0) / 3.0 * 100.0
        score = min(100.0, max(0.0, raw_score))

        # 절대 관심도 낮으면 신뢰도 하향 (noise 가능성)
        confidence = 0.75 if q4_avg >= _MIN_INTEREST else 0.4

        evidence: dict = {
            "keyword": kw,
            "avg_3m": round(q4_avg, 1),
            "avg_6m_ago": round(q3_avg, 1),
            "composite_rate": round(composite_rate, 3),
            "rate_3m": round(rate_3m, 3) if rate_3m is not None else None,
            "rate_6m": round(rate_6m, 3) if rate_6m is not None else None,
            "rate_1y": round(rate_1y, 3) if rate_1y is not None else None,
            "weeks_fetched": n,
        }
        if q2_avg is not None:
            evidence["avg_9m_ago"] = round(q2_avg, 1)
        if q1_avg is not None:
            evidence["avg_12m_ago"] = round(q1_avg, 1)

        return AnalyzerResult(
            score=round(score, 2),
            signal=_score_to_signal(score),
            evidence=evidence,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


def _is_rate_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate" in msg


@retry(
    retry=retry_if_exception(_is_rate_limit),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=15, max=120),
    reraise=True,
)
def _fetch_interest(pt) -> pd.DataFrame:
    return pt.interest_over_time()


def jitter_sleep() -> float:
    """배치 루프에서 호출 전 랜덤 대기. 반환값을 _analyze(pre_sleep=)에 전달."""
    return random.uniform(*_PRE_REQUEST_JITTER)


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
