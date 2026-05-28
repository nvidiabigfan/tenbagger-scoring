"""Revenue 가속도 모듈 백테스트.

quarterly_fundamentals + forward_returns → cross-sectional IC/Decile 분석.

Revenue 점수 로직 (revenue.py와 동일):
  sales_score  (0~50): 현재 분기 YoY 매출 성장률 절대값
  accel_score  (0~30): 현재 성장률 - 5Y CAGR (가속도)
  eps_score    (0~20): EPS YoY 가속도
  transition_bonus: 음→양 전환 보너스

PIT 보장:
  avail_date = period_end + 45일 기준
  as_of_date 시점에 avail_date <= as_of_date인 분기만 사용.

실행: python -m backtest.compute.revenue_scores [--start 2015-01-01]
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

import numpy as np
import pandas as pd

from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── 월말 기준일 조회 ──────────────────────────────────────────────────────

_MONTH_ENDS_SQL = """
SELECT MAX(date) AS eom_date
FROM prices
WHERE ticker = 'AAPL'
  AND date BETWEEN ?::DATE AND ?::DATE
GROUP BY YEAR(date), MONTH(date)
ORDER BY eom_date
"""

# ── PIT Revenue features 계산 ─────────────────────────────────────────────

_FEATURES_SQL = """
WITH
-- 각 as_of_date 기준 가장 최신 avail_date <= as_of_date 분기 선택
latest_q AS (
    SELECT
        qf.ticker,
        me.eom_date                           AS as_of_date,
        qf.period_end,
        qf.total_revenue,
        qf.gross_profit,
        qf.net_income,
        qf.eps_diluted,
        ROW_NUMBER() OVER (
            PARTITION BY qf.ticker, me.eom_date
            ORDER BY qf.period_end DESC
        )                                     AS rn
    FROM quarterly_fundamentals qf
    CROSS JOIN month_ends me
    WHERE qf.avail_date <= me.eom_date
),
current_q AS (
    SELECT * FROM latest_q WHERE rn = 1
),
-- 1년 전 동기 분기 (YoY 비교)
prior_year_q AS (
    SELECT
        qf.ticker,
        qf.period_end,
        qf.total_revenue   AS rev_prior,
        qf.eps_diluted     AS eps_prior
    FROM quarterly_fundamentals qf
),
-- 5년 전 ~ 1년 전 매출 (CAGR 계산용)
five_yr_ago AS (
    SELECT
        qf.ticker,
        me.eom_date        AS as_of_date,
        qf.total_revenue   AS rev_5y,
        qf.period_end      AS period_5y,
        ROW_NUMBER() OVER (
            PARTITION BY qf.ticker, me.eom_date
            ORDER BY ABS(DATEDIFF('day', qf.period_end,
                          me.eom_date - INTERVAL 5 YEARS))
        )                  AS rn
    FROM quarterly_fundamentals qf
    CROSS JOIN month_ends me
    WHERE qf.avail_date <= me.eom_date
      AND qf.period_end BETWEEN me.eom_date - INTERVAL 6 YEARS
                            AND me.eom_date - INTERVAL 4 YEARS
),
five_yr AS (SELECT * FROM five_yr_ago WHERE rn = 1),
-- 1년 전 같은 분기 (period_end - 365±45일)
py AS (
    SELECT
        cq.ticker,
        cq.as_of_date,
        py.rev_prior,
        py.eps_prior
    FROM current_q cq
    JOIN prior_year_q py
      ON py.ticker = cq.ticker
     AND ABS(DATEDIFF('day', py.period_end,
              cq.period_end - INTERVAL 1 YEAR)) <= 46
)
SELECT
    cq.ticker,
    cq.as_of_date,
    cq.total_revenue,
    cq.eps_diluted,
    py.rev_prior,
    py.eps_prior,
    fy.rev_5y,
    DATEDIFF('day', fy.period_5y, cq.period_end) / 365.25 AS years_5y
FROM current_q cq
LEFT JOIN py ON py.ticker = cq.ticker AND py.as_of_date = cq.as_of_date
LEFT JOIN five_yr fy ON fy.ticker = cq.ticker AND fy.as_of_date = cq.as_of_date
WHERE cq.total_revenue IS NOT NULL
"""


def _compute_revenue_features(con, start: str, end: str) -> pd.DataFrame:
    month_ends = con.execute(_MONTH_ENDS_SQL, [start, end]).df()
    if month_ends.empty:
        return pd.DataFrame()

    con.register("month_ends", month_ends)
    df = con.execute(_FEATURES_SQL).df()
    con.unregister("month_ends")
    return df


# ── 스코어링 (revenue.py 동일 로직) ──────────────────────────────────────

def compute_scores(df: pd.DataFrame) -> pd.Series:
    """PIT features → revenue score (0~100)."""
    rev      = df["total_revenue"]
    rev_py   = df["rev_prior"]
    eps      = df["eps_diluted"]
    eps_py   = df["eps_prior"]
    rev_5y   = df["rev_5y"]
    yrs_5y   = df["years_5y"]

    # YoY 성장률 (%)
    sales_yoy = np.where(
        (rev_py.notna()) & (rev_py != 0),
        (rev / rev_py - 1) * 100,
        np.nan,
    )
    eps_yoy = np.where(
        (eps_py.notna()) & (eps_py != 0),
        (eps / eps_py - 1) * 100,
        np.nan,
    )

    # 5Y CAGR (%)
    cagr_5y = np.where(
        (rev_5y.notna()) & (rev_5y > 0) & (yrs_5y > 0),
        (np.power(rev / rev_5y, 1 / yrs_5y) - 1) * 100,
        np.nan,
    )

    # sales_score (0~50)
    sales_score = np.clip(25.0 + np.where(np.isnan(sales_yoy), 0, sales_yoy) * 0.25, 0, 50)

    # accel_score (0~30)
    accel_score = np.where(
        ~np.isnan(cagr_5y),
        np.clip(15.0 + (np.where(np.isnan(sales_yoy), 0, sales_yoy) - cagr_5y) * 0.3, 0, 30),
        np.where(
            ~np.isnan(sales_yoy),
            np.clip(7.5 + np.where(np.isnan(sales_yoy), 0, sales_yoy) * 0.075, 0, 15),
            15.0,
        ),
    )

    # eps_score (0~20)
    eps_score = np.where(
        ~np.isnan(eps_yoy),
        np.where(
            ~np.isnan(cagr_5y),
            np.clip(10.0 + (np.where(np.isnan(eps_yoy), 0, eps_yoy) - cagr_5y) * 0.1, 0, 20),
            np.clip(10.0 + np.where(np.isnan(eps_yoy), 0, eps_yoy) * 0.1, 0, 20),
        ),
        10.0,
    )

    # transition bonus
    transition_bonus = np.where(
        (~np.isnan(cagr_5y)) & (cagr_5y <= 0) & (~np.isnan(sales_yoy)) & (sales_yoy > 0),
        10.0,
        np.where(
            (~np.isnan(sales_yoy)) & (~np.isnan(cagr_5y)) & ((sales_yoy - cagr_5y) > 50),
            5.0, 0.0,
        ),
    )

    score = np.clip(sales_score + accel_score + eps_score + transition_bonus, 0, 100)
    return pd.Series(np.round(score, 2), index=df.index)


# ── DuckDB upsert ─────────────────────────────────────────────────────────

def _upsert_module_scores(con, df: pd.DataFrame) -> int:
    rows = df[["ticker", "as_of_date", "score"]].copy()
    rows["module"] = "revenue"
    rows["confidence"] = 0.85
    rows["evidence_json"] = None
    con.register("_tmp_ms", rows)
    con.execute("""
        INSERT INTO module_scores (ticker, as_of_date, module, score, confidence, evidence_json)
        SELECT ticker, as_of_date::DATE, module, score, confidence, evidence_json
        FROM _tmp_ms
        ON CONFLICT (ticker, as_of_date, module) DO UPDATE SET
            score = EXCLUDED.score, confidence = EXCLUDED.confidence
    """)
    con.unregister("_tmp_ms")
    return len(rows)


# ── IC 분석 (momentum_scores.py에서 재사용) ───────────────────────────────

def _cross_sectional_ic(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    valid = df[["as_of_date", score_col, ret_col]].dropna()
    if valid.empty:
        return pd.DataFrame(columns=["as_of_date", "ic", "n"])

    def _spearman(grp):
        if len(grp) < 30:
            return float("nan")
        return grp[score_col].rank().corr(grp[ret_col].rank())

    ic_s = valid.groupby("as_of_date").apply(_spearman, include_groups=False)
    n_s  = valid.groupby("as_of_date")[score_col].count()
    return pd.DataFrame({"ic": ic_s, "n": n_s}).reset_index()


def _ic_summary(ic_df: pd.DataFrame) -> dict:
    vals = ic_df["ic"].dropna().values
    if len(vals) == 0:
        return {}
    return {
        "mean_ic":  round(float(np.mean(vals)), 4),
        "std_ic":   round(float(np.std(vals)), 4),
        "ic_ir":    round(float(np.mean(vals) / np.std(vals)) if np.std(vals) > 0 else 0, 3),
        "hit_rate": round(float(np.mean(vals > 0)), 4),
        "n_months": int(len(vals)),
    }


def _print_report(df: pd.DataFrame, module: str = "Revenue") -> None:
    horizons = [("fwd_1m", "1M"), ("fwd_3m", "3M"), ("fwd_6m", "6M"), ("fwd_12m", "12M")]

    print(f"\n{'=' * 68}")
    print(f"{module} 모듈 IC 분석")
    print("=" * 68)
    print(f"{'Horizon':<10} {'IC_mean':>8} {'IC_std':>8} {'IC_IR':>8} {'HitRate':>9} {'N월':>6}")
    print("-" * 68)

    ic_3m_df = None
    for col, label in horizons:
        if col not in df.columns:
            continue
        ic_df = _cross_sectional_ic(df, "score", col)
        s = _ic_summary(ic_df)
        if not s:
            print(f"{label:<10} {'데이터 없음':>30}")
            continue
        print(
            f"{label:<10} {s['mean_ic']:>8.4f} {s['std_ic']:>8.4f} "
            f"{s['ic_ir']:>8.3f} {s['hit_rate']:>8.1%} {s['n_months']:>6}"
        )
        if col == "fwd_3m":
            ic_3m_df = ic_df

    print("=" * 68)

    if ic_3m_df is not None and not ic_3m_df.empty:
        print("\n3M Forward Return 기준 연도별 IC:")
        ic_3m_df["year"] = pd.to_datetime(ic_3m_df["as_of_date"]).dt.year
        yearly = ic_3m_df.groupby("year")["ic"].mean()
        for yr, ic in yearly.items():
            bar = ("▓" * int(abs(ic) * 300)) if not np.isnan(ic) else ""
            sign = "+" if ic >= 0 else ""
            print(f"  {yr}: {sign}{ic:.4f}  {bar}")


# ── main ──────────────────────────────────────────────────────────────────

def run(start: str = "2015-01-01") -> None:
    log.info("Revenue 백테스트 시작 (from %s)", start)
    con = duckdb_store.connect()
    con.execute("SET memory_limit='800MB'")

    # quarterly_fundamentals 있는지 확인
    n_fund = con.execute("SELECT COUNT(*) FROM quarterly_fundamentals").fetchone()[0]
    if n_fund == 0:
        log.error("quarterly_fundamentals 비어있음. 먼저 python -m backtest.data.fundamentals 실행")
        con.close()
        return

    log.info("quarterly_fundamentals: %d rows", n_fund)

    # forward_returns 조회 (momentum backtest에서 이미 계산됨)
    n_fret = con.execute("SELECT COUNT(*) FROM forward_returns").fetchone()[0]
    if n_fret == 0:
        log.warning("forward_returns 없음. momentum_scores 먼저 실행 권장")

    end = date.today().isoformat()
    log.info("Revenue features 계산 중...")
    df = _compute_revenue_features(con, start=start, end=end)
    log.info("  features: %d rows (tickers=%d)", len(df), df["ticker"].nunique() if not df.empty else 0)

    if df.empty:
        log.error("features 없음")
        con.close()
        return

    # py 서브쿼리에서 동일 (ticker, as_of_date)에 다중 prior year 매칭 가능 → dedup
    df = df.drop_duplicates(subset=["ticker", "as_of_date"])
    log.info("  dedup 후: %d rows", len(df))

    df["score"] = compute_scores(df)

    # forward_returns JOIN
    fret = con.execute("""
        SELECT ticker, as_of_date, ret_1m AS fwd_1m, ret_3m AS fwd_3m,
               ret_6m AS fwd_6m, ret_12m AS fwd_12m
        FROM forward_returns
    """).df()

    df = df.merge(fret, on=["ticker", "as_of_date"], how="left")

    n_ms = _upsert_module_scores(con, df)
    log.info("  저장: module_scores=%d", n_ms)

    _print_report(df)

    log.info("완료")
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Revenue IC backtest")
    p.add_argument("--start", default="2015-01-01")
    args = p.parse_args()
    run(start=args.start)
