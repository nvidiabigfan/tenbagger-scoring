"""DuckDB 가격 데이터 → 월말 momentum features 추출.

perf(1W/1M/3M), RSI(14), 52W range position, forward returns 계산.
모든 연산은 DuckDB window functions으로 단일 패스 처리.
"""

from __future__ import annotations

import duckdb
import pandas as pd

# AAPL을 기준 거래일 달력으로 사용 (상장 10년+ 연속 거래)
# params: [start, end, lookback_start, end]
# lookback_start = start - 400days (52W warmup용)
_FEATURES_SQL = """
WITH
-- 월말 기준일: AAPL 기준 각 (연, 월)의 마지막 거래일 (start~end 범위만)
month_ends AS (
    SELECT MAX(date) AS eom_date
    FROM prices
    WHERE ticker = 'AAPL'
      AND date BETWEEN ?::DATE AND ?::DATE
    GROUP BY YEAR(date), MONTH(date)
),

-- 가격 window features (lookback_start~end 범위만 읽어 메모리 절약)
-- perf / forward return / 52W 범위 / delta
base AS (
    SELECT
        p.ticker,
        p.date,
        p.adj_close,
        -- performance (배당 조정 종가 기준)
        p.adj_close / NULLIF(LAG(p.adj_close, 5)   OVER w, 0) - 1  AS perf_1w,
        p.adj_close / NULLIF(LAG(p.adj_close, 21)  OVER w, 0) - 1  AS perf_1m,
        p.adj_close / NULLIF(LAG(p.adj_close, 63)  OVER w, 0) - 1  AS perf_3m,
        -- forward returns (IC 검증 타겟 — 신호 계산에는 미사용)
        LEAD(p.adj_close, 21)  OVER w / NULLIF(p.adj_close, 0) - 1 AS fwd_1m,
        LEAD(p.adj_close, 63)  OVER w / NULLIF(p.adj_close, 0) - 1 AS fwd_3m,
        LEAD(p.adj_close, 126) OVER w / NULLIF(p.adj_close, 0) - 1 AS fwd_6m,
        LEAD(p.adj_close, 252) OVER w / NULLIF(p.adj_close, 0) - 1 AS fwd_12m,
        -- 52W 고저 (251 preceding + current = 252 거래일 ≈ 1년)
        MAX(p.adj_close) OVER (PARTITION BY p.ticker ORDER BY p.date
                               ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,
        MIN(p.adj_close) OVER (PARTITION BY p.ticker ORDER BY p.date
                               ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS low_52w,
        -- RSI delta
        p.adj_close - LAG(p.adj_close, 1) OVER w AS delta
    FROM prices p
    WHERE p.date BETWEEN ?::DATE AND ?::DATE   -- lookback_start ~ end
    WINDOW w AS (PARTITION BY p.ticker ORDER BY p.date)
),

-- RSI(14): 14일 SMA 기반 (Wilder's 근사)
rsi_calc AS (
    SELECT
        *,
        AVG(GREATEST(delta, 0.0))  OVER (PARTITION BY ticker ORDER BY date
                                          ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain,
        AVG(GREATEST(-delta, 0.0)) OVER (PARTITION BY ticker ORDER BY date
                                          ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss
    FROM base
    WHERE delta IS NOT NULL
)

SELECT
    r.ticker,
    r.date                   AS as_of_date,
    r.perf_1w,
    r.perf_1m,
    r.perf_3m,
    r.fwd_1m,
    r.fwd_3m,
    r.fwd_6m,
    r.fwd_12m,
    -- 52W range position: 0.0(52W 저점) ~ 1.0(52W 고점)
    CASE
        WHEN r.high_52w = r.low_52w THEN 0.5
        ELSE (r.adj_close - r.low_52w) / (r.high_52w - r.low_52w)
    END                      AS range_pos_52w,
    -- RSI 14
    CASE
        WHEN r.avg_loss = 0 THEN 100.0
        ELSE 100.0 - 100.0 / (1.0 + r.avg_gain / r.avg_loss)
    END                      AS rsi_14
FROM rsi_calc r
JOIN month_ends me ON r.date = me.eom_date
WHERE r.perf_1m IS NOT NULL      -- 최소 1개월치 데이터 보증
ORDER BY r.date, r.ticker
"""


def compute_features(
    con: duckdb.DuckDBPyConnection,
    start: str = "2015-01-01",
    end: str = "2099-12-31",
) -> pd.DataFrame:
    """월말 기준 momentum features 추출.

    prices 테이블을 [start-400d, end] 범위로만 읽어 메모리 사용량 최소화.
    (52W range warmup: 252 거래일 ≈ 400 calendar days)

    Returns:
        DataFrame with columns:
            ticker, as_of_date,
            perf_1w, perf_1m, perf_3m,
            fwd_1m, fwd_3m, fwd_6m, fwd_12m,
            range_pos_52w (0~1), rsi_14
    """
    # 52W range + RSI 워밍업을 위해 start보다 400일 앞에서부터 읽기
    lookback = (pd.Timestamp(start) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    return con.execute(_FEATURES_SQL, [start, end, lookback, end]).df()
