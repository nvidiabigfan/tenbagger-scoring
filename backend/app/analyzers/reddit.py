"""Reddit 소셜 센티먼트 분석 모듈.

reddit_snapshots 테이블에서 최근 24h 데이터를 읽어 스코어 계산.
수집은 GitHub Actions reddit_batch.py에서 담당 (서버 IP 차단 우회).
스냅샷 없으면 confidence=0 → ScoringEngine 자동 제외.
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)


class RedditAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "reddit"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("RedditAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        from supabase import create_client

        client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        res = (
            client.table("reddit_snapshots")
            .select("post_count, total_upvotes, collected_at")
            .eq("ticker", ticker)
            .gte("collected_at", cutoff)
            .order("collected_at", desc=True)
            .limit(1)
            .execute()
        )

        if not res.data:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "no_snapshot"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        row = res.data[0]
        post_count = row["post_count"]
        total_upvotes = row["total_upvotes"]

        post_score = min(50.0, post_count * 5.0)
        upvote_score = min(50.0, math.log10(total_upvotes + 1) * 12.5) if total_upvotes > 0 else 0.0
        score = round(post_score + upvote_score, 2)
        # post_count=0은 수집 실패(API 차단 등)와 구별 불가 → confidence=0 으로 엔진 제외
        confidence = 0.85 if post_count >= 5 else (0.6 if post_count >= 1 else 0.0)

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "post_count_7d": post_count,
                "total_upvotes_7d": total_upvotes,
                "avg_upvotes": round(total_upvotes / post_count, 0) if post_count else 0,
                "post_score": round(post_score, 2),
                "upvote_score": round(upvote_score, 2),
                "collected_at": row["collected_at"],
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
