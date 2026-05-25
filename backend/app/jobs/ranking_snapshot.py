"""
랭킹 스냅샷 생성 배치.
GitHub Actions daily-batch.yml → ranking-snapshot job에서 실행.
"""

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def run() -> None:
    # TODO: 전일 분석 결과에서 상위 100 종목 선정
    # TODO: RankingSnapshot row 생성 (rank_change 계산 포함)
    log.info("ranking_snapshot: 스켈레톤 (미구현)")


if __name__ == "__main__":
    run()
