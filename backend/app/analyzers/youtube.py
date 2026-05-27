"""YouTube 컨텐츠 버즈 분석 모듈.

데이터: YouTube Data API v3 (YOUTUBE_API_KEY 필요)
시그널 로직:
  - 최근 7일 업로드 영상 수 → 콘텐츠 생산 활발도
  - 영상별 조회수 합산 → 실제 관심 규모
  - score = video_score(0~50) + view_score(0~50)
쿼터: search 1회=100 unit, videos.list 1회=1 unit
  → 종목당 ~101 unit, 일 한도 10,000 unit
  → _DAILY_SEARCH_LIMIT=85 (8,585 unit) — on-demand 여유분 포함
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from app.analyzers.base import Analyzer, AnalyzerResult

log = logging.getLogger(__name__)

_SEARCH_WINDOW_DAYS = 7
_MAX_RESULTS = 50
_DAILY_SEARCH_LIMIT = 85  # search.list() 호출 상한. 초과 시 confidence=0 반환

# 프로세스 내 일일 quota 카운터
_quota_used: int = 0
_quota_exhausted: bool = False  # 429 응답 시 True → 이후 모든 호출 차단


def _skip_result(reason: str) -> "AnalyzerResult":
    return AnalyzerResult(
        score=0.0,
        signal="hold",
        evidence={"error": reason},
        confidence=0.0,
        timestamp=datetime.now(timezone.utc),
    )


class YouTubeAnalyzer(Analyzer):
    @property
    def name(self) -> str:
        return "youtube"

    def analyze(self, ticker: str) -> AnalyzerResult:
        global _quota_used, _quota_exhausted
        if _quota_exhausted:
            log.debug("YouTube quota exhausted — skipping %s", ticker)
            return _skip_result("quota_exhausted")
        if _quota_used >= _DAILY_SEARCH_LIMIT:
            log.warning("YouTube daily search limit(%d) reached — skipping %s", _DAILY_SEARCH_LIMIT, ticker)
            _quota_exhausted = True
            return _skip_result("daily_limit_reached")
        try:
            result = self._analyze(ticker)
            _quota_used += 1
            return result
        except HttpError as e:
            if e.status_code == 429:
                log.warning("YouTube 429 — marking quota exhausted")
                _quota_exhausted = True
            else:
                log.warning("YouTubeAnalyzer error [%s]: %s", ticker, e)
            return _skip_result(f"http_{e.status_code}")
        except Exception as e:
            log.warning("YouTubeAnalyzer error [%s]: %s", ticker, e)
            return _skip_result(str(e))

    def _analyze(self, ticker: str) -> AnalyzerResult:
        """HttpError는 호출자(analyze)로 전파하여 quota guard가 처리."""
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            return _skip_result("YOUTUBE_API_KEY not set")

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


def _is_retryable(e: BaseException) -> bool:
    """429(quota)는 재시도해도 의미 없음 → 즉시 전파."""
    return not (isinstance(e, HttpError) and e.status_code == 429)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception(_is_retryable))
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


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception(_is_retryable))
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
