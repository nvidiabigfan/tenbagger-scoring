"""YouTube 컨텐츠 버즈 분석 모듈.

데이터: YouTube Data API v3 (YOUTUBE_API_KEY 필요)
시그널 로직:
  - 최근 7일 업로드 영상 수 → 콘텐츠 생산 활발도
  - 영상별 조회수 합산 → 실제 관심 규모
  - score = video_score(0~50) + view_score(0~50)
쿼터: 검색 1회=100 unit, 통계 조회 1회=1 unit × N개
  → 종목당 약 101~150 unit 소비 (일 한도 10,000 unit 기준 ~66종목/일)
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_fixed

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_SEARCH_WINDOW_DAYS = 7
_MAX_RESULTS = 50


class YouTubeAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "youtube"

    def analyze(self, ticker: str) -> AnalyzerResult:
        try:
            return self._analyze(ticker)
        except Exception as e:
            log.warning("YouTubeAnalyzer error [%s]: %s", ticker, e)
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": str(e)},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

    def _analyze(self, ticker: str) -> AnalyzerResult:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            return AnalyzerResult(
                score=0.0,
                signal="hold",
                evidence={"error": "YOUTUBE_API_KEY not set"},
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=_SEARCH_WINDOW_DAYS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        video_ids = _search_videos(yt, ticker, published_after)
        video_count = len(video_ids)

        total_views = 0
        if video_ids:
            total_views = _get_total_views(yt, video_ids)

        # 영상 수 점수 (0~50): 25개 이상 만점
        video_score = min(50.0, video_count * 2.0)

        # 조회수 점수 (0~50): log10 스케일, 10만 뷰 이상 만점
        if total_views > 0:
            view_score = min(50.0, math.log10(total_views) * 10.0)
        else:
            view_score = 0.0

        score = round(video_score + view_score, 2)
        confidence = 0.85 if video_count >= 5 else (0.6 if video_count >= 1 else 0.3)

        return AnalyzerResult(
            score=score,
            signal=_score_to_signal(score),
            evidence={
                "video_count_7d": video_count,
                "total_views_7d": total_views,
                "avg_views": round(total_views / video_count, 0) if video_count else 0,
                "query": f"{ticker} stock",
            },
            confidence=confidence,
            timestamp=datetime.now(timezone.utc),
        )


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _search_videos(yt, ticker: str, published_after: str) -> list[str]:
    resp = (
        yt.search()
        .list(
            q=f"{ticker} stock",
            type="video",
            part="id",
            maxResults=_MAX_RESULTS,
            publishedAfter=published_after,
            order="viewCount",
            relevanceLanguage="en",
        )
        .execute()
    )
    return [item["id"]["videoId"] for item in resp.get("items", [])]


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _get_total_views(yt, video_ids: list[str]) -> int:
    resp = (
        yt.videos()
        .list(
            id=",".join(video_ids),
            part="statistics",
        )
        .execute()
    )
    total = 0
    for item in resp.get("items", []):
        vc = item.get("statistics", {}).get("viewCount")
        if vc:
            total += int(vc)
    return total


def _score_to_signal(score: float) -> str:
    if score >= 75:
        return "strong_buy"
    if score >= 55:
        return "buy"
    if score >= 35:
        return "hold"
    return "sell"
