"""forward_returns → ret_12m / ret_24m / ret_36m 일괄 보완.

features.py의 연도별 배치 분할에서 LEAD 창이 연말에 잘려
ret_12m 이상이 모두 NULL인 문제 수정.
prices 전체(2.67M rows)에서 LEAD(252/504/756) 일괄 계산 후 UPDATE.

실행: python -m backtest.compute.extend_forward_returns
"""

from __future__ import annotations

import logging
import os

from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_COMPUTE_SQL = """
WITH month_ends AS (
    SELECT MAX(date) AS eom_date
    FROM prices
    WHERE ticker = 'AAPL'
    GROUP BY YEAR(date), MONTH(date)
),
full_lags AS (
    SELECT
        ticker,
        date,
        adj_close,
        LEAD(adj_close, 252) OVER (PARTITION BY ticker ORDER BY date) AS p_12m,
        LEAD(adj_close, 504) OVER (PARTITION BY ticker ORDER BY date) AS p_24m,
        LEAD(adj_close, 756) OVER (PARTITION BY ticker ORDER BY date) AS p_36m
    FROM prices
)
SELECT
    fl.ticker,
    fl.date                                     AS as_of_date,
    fl.p_12m / NULLIF(fl.adj_close, 0) - 1     AS ret_12m,
    fl.p_24m / NULLIF(fl.adj_close, 0) - 1     AS ret_24m,
    fl.p_36m / NULLIF(fl.adj_close, 0) - 1     AS ret_36m
FROM full_lags fl
JOIN month_ends me ON fl.date = me.eom_date
"""


def run() -> None:
    log.info("forward_returns 장기 수익률 보완 시작")
    os.makedirs("/tmp/duckdb_tmp", exist_ok=True)

    con = duckdb_store.connect()
    con.execute("SET memory_limit='800MB'")
    con.execute("SET temp_directory='/tmp/duckdb_tmp'")

    n_prices = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    log.info("prices 총 %d rows", n_prices)

    log.info("LEAD(252/504/756) 전체 계산 중... (3~8분 예상)")
    df = con.execute(_COMPUTE_SQL).df()

    n12 = int(df["ret_12m"].notna().sum())
    n24 = int(df["ret_24m"].notna().sum())
    n36 = int(df["ret_36m"].notna().sum())
    log.info(
        "계산 완료: %d rows | 유효 ret_12m=%d / ret_24m=%d / ret_36m=%d",
        len(df), n12, n24, n36,
    )

    log.info("forward_returns UPDATE 중...")
    con.register("_lr", df)
    con.execute("""
        UPDATE forward_returns
        SET ret_12m = lr.ret_12m,
            ret_24m = lr.ret_24m,
            ret_36m = lr.ret_36m
        FROM _lr lr
        WHERE forward_returns.ticker     = lr.ticker
          AND forward_returns.as_of_date = lr.as_of_date::DATE
    """)
    con.unregister("_lr")

    counts = con.execute("""
        SELECT
            COUNT(*) FILTER (WHERE ret_12m IS NOT NULL) AS n_12m,
            COUNT(*) FILTER (WHERE ret_24m IS NOT NULL) AS n_24m,
            COUNT(*) FILTER (WHERE ret_36m IS NOT NULL) AS n_36m
        FROM forward_returns
    """).fetchone()
    log.info("업데이트 확인 — ret_12m=%d / ret_24m=%d / ret_36m=%d", *counts)

    con.close()
    log.info("완료")


if __name__ == "__main__":
    run()
