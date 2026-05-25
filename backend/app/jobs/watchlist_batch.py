"""
워치리스트 일일 재분석 배치.
GitHub Actions daily-batch.yml → watchlist-reanalysis job에서 실행.
"""

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def run() -> None:
    # TODO: Supabase에서 워치리스트 ticker 목록 조회
    # TODO: ScoringEngine으로 각 ticker 분석
    # TODO: AnalysisResult + ModuleScore DB 저장
    # TODO: 스코어 변화 임계치 초과 시 Resend 이메일 발송
    log.info("watchlist_batch: 스켈레톤 (미구현)")


if __name__ == "__main__":
    run()
