"""StockTwits 소셜 센티먼트 분석 모듈.

공개 API (인증 불필요): api.stocktwits.com/api/2/streams/symbol/{ticker}.json
최근 30개 메시지의 볼륨 + Bullish/Bearish 비율로 스코어 계산.
"""

import logging
from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_TIMEOUT = 10


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))


class StockTwitsAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "stocktwits"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("StockTwitsAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=5, max=20),
        reraise=True,
    )
    def _fetch(self, ticker: str) -> dict:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(_BASE_URL.format(ticker=ticker))
            if resp.status_code == 404:
                return {}  # 미등록 종목 — 빈 결과
            if resp.status_code == 429:
                raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp.json()

    def _analyze(self, ticker: str) -> AnalyzerResult:
        data = self._fetch(ticker)
        messages = data.get("messages") or []

        msg_count = len(messages)
        bull_count = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}) and
               m["entities"]["sentiment"].get("basic") == "Bullish"
        )
        bear_count = sum(
            1 for m in messages
            if (m.get("entities") or {}).get("sentiment", {}) and
               m["entities"]["sentiment"].get("basic") == "Bearish"
        )
        total_sentiment = bull_count + bear_count
        bull_ratio = bull_count / total_sentiment if total_sentiment > 0 else 0.5

        # 볼륨: 30개 만점 기준
        volume_score = min(50.0, msg_count / 30 * 50)
        # 센티먼트: 레이블 3개 이상일 때만 반영, 미만은 중립(25점)
        sentiment_score = (bull_ratio * 50) if total_sentiment >= 3 else 25.0
        score = round(volume_score + sentiment_score, 2)

        # confidence: 레이블 데이터가 있어야 신뢰 가능
        if total_sentiment >= 5:
            confidence = 0.8
        elif msg_count >= 3:
            confidence = 0.5
        else:
            confidence = 0.0

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "msg_count_recent": msg_count,
                "bull_count": bull_count,
                "bear_count": bear_count,
                "bull_ratio": round(bull_ratio, 3),
                "volume_score": round(volume_score, 2),
                "sentiment_score": round(sentiment_score, 2),
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
