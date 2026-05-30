"""Momentum + Revenue 복합 스코어 IC 백테스트.

module_scores 테이블(momentum + revenue 기적재)을 읽어 두 가지 질문에 답한다.
  Q1. 복합 점수 수준이 높으면 향후 수익률이 높은가?  (수준 IC)
  Q2. 복합 점수가 개선되면 향후 수익률이 높은가?    (변화량 IC — 사용자 핵심 질문)

가중치:
  production  : Revenue 71.4% (25/35) + Momentum 28.6% (10/35)
  equal       : Revenue 50%  + Momentum 50%

실행: python -m backtest.compute.composite_scores [--start 2015-01-01]
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

W_PROD  = {"revenue": 25 / 35, "momentum": 10 / 35}   # 운영 가중치 (25+10=35 합산 정규화)
W_EQUAL = {"revenue": 0.5, "momentum": 0.5}


# ── 데이터 로드 ───────────────────────────────────────────────────────────

def _load_pivot(con, start: str) -> pd.DataFrame:
    """module_scores pivot → (ticker, as_of_date, revenue, momentum)."""
    df = con.execute("""
        SELECT ticker, as_of_date, module, score
        FROM module_scores
        WHERE module IN ('momentum', 'revenue')
          AND as_of_date >= ?::DATE
        ORDER BY ticker, as_of_date
    """, [start]).df()

    if df.empty:
        return pd.DataFrame()

    pivot = df.pivot_table(
        index=["ticker", "as_of_date"],
        columns="module",
        values="score",
        aggfunc="last",
    ).reset_index()
    pivot.columns.name = None
    return pivot


def _load_forward_returns(con) -> pd.DataFrame:
    return con.execute("""
        SELECT ticker, as_of_date,
               ret_1m AS fwd_1m, ret_3m AS fwd_3m,
               ret_6m AS fwd_6m, ret_12m AS fwd_12m
        FROM forward_returns
    """).df()


# ── 복합 점수 + 변화량 계산 ───────────────────────────────────────────────

def _compute_composite(pivot: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """두 모듈 중 하나만 있어도 단독 점수 사용."""
    df = pivot.copy()
    has_rev = "revenue" in df.columns
    has_mom = "momentum" in df.columns

    if has_rev and has_mom:
        w_r, w_m = weights["revenue"], weights["momentum"]
        # NaN 처리: 한쪽 없으면 있는 쪽 100% 사용
        both = df["revenue"].notna() & df["momentum"].notna()
        rev_only = df["revenue"].notna() & df["momentum"].isna()
        mom_only = df["revenue"].isna() & df["momentum"].notna()

        score = np.where(both,
            df["revenue"].fillna(0) * w_r + df["momentum"].fillna(0) * w_m,
            np.where(rev_only, df["revenue"],
            np.where(mom_only, df["momentum"], np.nan)))
    elif has_rev:
        score = df["revenue"].values
    elif has_mom:
        score = df["momentum"].values
    else:
        raise ValueError("module_scores에 momentum/revenue 없음")

    df["composite"] = np.round(score, 2)
    return df


def _compute_delta(df: pd.DataFrame) -> pd.DataFrame:
    """ticker별 직전 월 대비 composite 변화량."""
    df = df.sort_values(["ticker", "as_of_date"])
    df["composite_prev"] = df.groupby("ticker")["composite"].shift(1)
    df["delta"] = df["composite"] - df["composite_prev"]
    return df


# ── IC / Decile 공통 유틸 ─────────────────────────────────────────────────

def _cross_sectional_ic(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    valid = df[["as_of_date", score_col, ret_col]].dropna()
    if valid.empty:
        return pd.DataFrame(columns=["as_of_date", "ic", "n"])

    def _spearman(grp):
        if len(grp) < 20:
            return float("nan")
        return grp[score_col].rank().corr(grp[ret_col].rank())

    ic_s = valid.groupby("as_of_date").apply(_spearman, include_groups=False)
    n_s  = valid.groupby("as_of_date")[score_col].count()
    return pd.DataFrame({"ic": ic_s, "n": n_s}).reset_index()


def _ic_summary(ic_df: pd.DataFrame) -> dict:
    vals = ic_df["ic"].dropna().values
    if len(vals) == 0:
        return {}
    std = float(np.std(vals))
    return {
        "mean_ic":  round(float(np.mean(vals)), 4),
        "std_ic":   round(std, 4),
        "ic_ir":    round(float(np.mean(vals)) / std if std > 0 else 0, 3),
        "hit_rate": round(float(np.mean(vals > 0)), 4),
        "n_months": int(len(vals)),
    }


def _decile_analysis(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    valid = df[["as_of_date", score_col, ret_col]].dropna()
    if valid.empty:
        return pd.DataFrame()
    valid = valid.copy()
    valid["decile"] = valid.groupby("as_of_date")[score_col].transform(
        lambda x: pd.qcut(x.rank(method="first"), 10, labels=False) + 1
    )
    return valid.groupby("decile")[ret_col].mean().reset_index().rename(
        columns={ret_col: "avg_ret"}
    )


def _yearly_ic(ic_df: pd.DataFrame) -> pd.Series:
    if ic_df.empty:
        return pd.Series(dtype=float)
    ic_df = ic_df.copy()
    ic_df["year"] = pd.to_datetime(ic_df["as_of_date"]).dt.year
    return ic_df.groupby("year")["ic"].mean()


# ── 리포트 출력 ───────────────────────────────────────────────────────────

def _print_ic_table(df: pd.DataFrame, score_col: str, title: str) -> dict[str, pd.DataFrame]:
    horizons = [("fwd_1m","1M"),("fwd_3m","3M"),("fwd_6m","6M"),("fwd_12m","12M")]
    print(f"\n{'─'*68}")
    print(f"  {title}")
    print(f"{'─'*68}")
    print(f"  {'Horizon':<8} {'IC_mean':>8} {'IC_std':>8} {'IC_IR':>8} {'HitRate':>9} {'N월':>6}")
    print(f"  {'-'*60}")

    ic_dfs = {}
    for col, label in horizons:
        if col not in df.columns:
            continue
        ic_df = _cross_sectional_ic(df, score_col, col)
        ic_dfs[col] = ic_df
        s = _ic_summary(ic_df)
        if not s:
            print(f"  {label:<8} {'(데이터 없음)':>40}")
            continue
        print(
            f"  {label:<8} {s['mean_ic']:>8.4f} {s['std_ic']:>8.4f} "
            f"{s['ic_ir']:>8.3f} {s['hit_rate']:>8.1%} {s['n_months']:>6}"
        )
    return ic_dfs


def _print_decile(df: pd.DataFrame, score_col: str, ret_col: str = "fwd_3m") -> None:
    dec = _decile_analysis(df, score_col, ret_col)
    if dec.empty:
        return
    print(f"\n  Decile 분석 ({ret_col.replace('fwd_','').upper()} 기준):")
    for _, row in dec.iterrows():
        bar = "█" * int(abs(row["avg_ret"]) * 200)
        print(f"    D{int(row['decile']):<2} {row['avg_ret']:>+.2%}  {bar}")
    d10 = dec.loc[dec["decile"]==10, "avg_ret"].values
    d1  = dec.loc[dec["decile"]==1,  "avg_ret"].values
    if len(d10) and len(d1):
        print(f"    Spread(D10-D1): {d10[0]-d1[0]:>+.2%}")


def _print_yearly(ic_df: pd.DataFrame) -> None:
    yearly = _yearly_ic(ic_df)
    if yearly.empty:
        return
    print("\n  연도별 3M IC:")
    for yr, ic in yearly.items():
        if np.isnan(ic):
            continue
        bar = ("▓" * int(abs(ic) * 300))
        sign = "+" if ic >= 0 else ""
        print(f"    {yr}: {sign}{ic:.4f}  {bar}")


def _print_report(df: pd.DataFrame, tag: str = "Production weights") -> None:
    print(f"\n{'='*68}")
    print(f"복합 스코어 IC 백테스트  [{tag}]")
    n_tickers = df["ticker"].nunique()
    n_dates   = df["as_of_date"].nunique()
    print(f"  데이터: {len(df):,} rows | {n_tickers} tickers | {n_dates} 월말 기준일")
    print(f"={'*'*66}=")

    # Q1 — 수준 IC
    ic_dfs = _print_ic_table(df, "composite", "Q1  복합 점수 수준 → 향후 수익률")
    if "fwd_3m" in ic_dfs:
        _print_decile(df, "composite", "fwd_3m")
        _print_yearly(ic_dfs["fwd_3m"])

    # Q2 — 변화량 IC
    if "delta" in df.columns:
        delta_dfs = _print_ic_table(df, "delta", "Q2  점수 변화량(delta) → 향후 수익률  ← 핵심 질문")
        if "fwd_3m" in delta_dfs:
            _print_decile(df, "delta", "fwd_3m")
            _print_yearly(delta_dfs["fwd_3m"])

    print(f"{'='*68}")


# ── main ──────────────────────────────────────────────────────────────────

def run(start: str = "2015-01-01") -> None:
    log.info("복합 IC 백테스트 시작 (from %s)", start)
    con = duckdb_store.connect()
    con.execute("SET memory_limit='800MB'")

    # 데이터 가용성 확인
    for tbl in ["module_scores", "forward_returns"]:
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        log.info("%s: %d rows", tbl, n)
        if n == 0:
            log.error("%s 비어있음. 선행 스크립트 먼저 실행:", tbl)
            if tbl == "module_scores":
                log.error("  python -m backtest.compute.momentum_scores")
                log.error("  python -m backtest.compute.revenue_scores")
            con.close()
            return

    pivot = _load_pivot(con, start)
    fret  = _load_forward_returns(con)
    con.close()

    if pivot.empty:
        log.error("module_scores에 %s 이후 데이터 없음", start)
        return

    log.info(
        "pivot: %d rows | tickers=%d | modules=%s",
        len(pivot), pivot["ticker"].nunique(),
        [c for c in pivot.columns if c not in ("ticker","as_of_date")],
    )

    # ── Production 가중치 ──
    df_prod = _compute_composite(pivot, W_PROD)
    df_prod = _compute_delta(df_prod)
    df_prod = df_prod.merge(fret, on=["ticker","as_of_date"], how="left")
    _print_report(df_prod, tag=f"Production  Revenue×{W_PROD['revenue']:.1%} + Momentum×{W_PROD['momentum']:.1%}")

    # ── Equal 가중치 ──
    df_eq = _compute_composite(pivot, W_EQUAL)
    df_eq = _compute_delta(df_eq)
    df_eq = df_eq.merge(fret, on=["ticker","as_of_date"], how="left")
    _print_report(df_eq, tag="Equal  Revenue×50% + Momentum×50%")

    log.info("완료")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Momentum+Revenue 복합 IC backtest")
    p.add_argument("--start", default="2015-01-01")
    args = p.parse_args()
    run(start=args.start)
