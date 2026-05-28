"""Momentum 모듈 백테스트.

가격 데이터 → 월말 Momentum 점수 계산 → IC/Decile 분석.

로직: momentum.py와 동일 (perf 50% + RSI 30% + 52W 20%).
데이터: DuckDB prices 테이블 (Finviz 불필요 — PIT 완전 보장).

결과: module_scores + forward_returns 저장 후 IC/Decile 리포트 출력.

실행:
  python -m backtest.compute.momentum_scores [--start 2015-01-01]
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

import numpy as np
import pandas as pd

from backtest.compute.features import compute_features
from backtest.storage import duckdb_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── 스코어링 (momentum.py와 동일 로직, numpy 벡터화) ─────────────────────

def _perf_score_np(pct: pd.Series) -> pd.Series:
    """수익률 fraction(-0.3=0pt, 0=50pt, +0.3=100pt)."""
    return np.clip((pct * 100 + 30) / 60 * 100, 0, 100)


def _rsi_score_np(rsi: pd.Series) -> pd.Series:
    """RSI → 0~100점. 45~65 구간 = 100."""
    r = np.where(
        (rsi >= 45) & (rsi <= 65), 100.0,
        np.where(
            (rsi >= 30) & (rsi < 45),  50.0 + (rsi - 30) / 15 * 50,
            np.where(
                (rsi > 65) & (rsi <= 75), 100.0 - (rsi - 65) / 10 * 50,
                np.clip(30.0 - np.abs(rsi - 50) * 0.5, 0, None),
            ),
        ),
    )
    return pd.Series(r, index=rsi.index)


def compute_scores(df: pd.DataFrame) -> pd.Series:
    """features DataFrame → momentum score Series (0~100)."""
    ps1w = _perf_score_np(df["perf_1w"])
    ps1m = _perf_score_np(df["perf_1m"])
    ps3m = _perf_score_np(df["perf_3m"])

    # 가중평균 (NaN 종목은 해당 가중치 0 처리)
    mask1w = df["perf_1w"].notna().astype(float)
    mask1m = df["perf_1m"].notna().astype(float)
    mask3m = df["perf_3m"].notna().astype(float)

    numer = ps1w.fillna(0) * 0.30 * mask1w + ps1m.fillna(0) * 0.40 * mask1m + ps3m.fillna(0) * 0.30 * mask3m
    denom = mask1w * 0.30 + mask1m * 0.40 + mask3m * 0.30
    perf_composite = np.where(denom > 0, numer / denom, 50.0)

    rsi_s   = _rsi_score_np(df["rsi_14"].fillna(50.0))
    range_s = df["range_pos_52w"].fillna(0.5) * 100.0

    score = perf_composite * 0.50 + rsi_s * 0.30 + range_s * 0.20
    return pd.Series(np.round(score, 2), index=df.index)


# ── DuckDB upsert ─────────────────────────────────────────────────────────

def _upsert_module_scores(con, df: pd.DataFrame) -> int:
    rows = df[["ticker", "as_of_date", "score"]].copy()
    rows["module"] = "momentum"
    rows["confidence"] = 0.9
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


def _upsert_forward_returns(con, df: pd.DataFrame) -> int:
    cols = ["ticker", "as_of_date", "fwd_1m", "fwd_3m", "fwd_6m", "fwd_12m"]
    rows = df[cols].rename(columns={
        "fwd_1m": "ret_1m", "fwd_3m": "ret_3m",
        "fwd_6m": "ret_6m", "fwd_12m": "ret_12m",
    }).copy()
    con.register("_tmp_fr", rows)
    con.execute("""
        INSERT INTO forward_returns (ticker, as_of_date, ret_1m, ret_3m, ret_6m, ret_12m)
        SELECT ticker, as_of_date::DATE, ret_1m, ret_3m, ret_6m, ret_12m
        FROM _tmp_fr
        ON CONFLICT (ticker, as_of_date) DO UPDATE SET
            ret_1m = EXCLUDED.ret_1m, ret_3m = EXCLUDED.ret_3m,
            ret_6m = EXCLUDED.ret_6m, ret_12m = EXCLUDED.ret_12m
    """)
    con.unregister("_tmp_fr")
    return len(rows)


# ── IC 분석 ───────────────────────────────────────────────────────────────

def _cross_sectional_ic(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """월별 cross-sectional Spearman IC 계산."""
    valid = df[["as_of_date", score_col, ret_col]].dropna()
    if valid.empty:
        return pd.DataFrame(columns=["as_of_date", "ic", "n"])

    def _spearman(grp: pd.DataFrame) -> float:
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


def _decile_analysis(df: pd.DataFrame, score_col: str, ret_col: str) -> pd.DataFrame:
    """각 월 cross-sectional decile 분류 → 평균 forward return."""
    valid = df[["as_of_date", score_col, ret_col]].dropna()
    if valid.empty:
        return pd.DataFrame()
    valid = valid.copy()
    valid["decile"] = valid.groupby("as_of_date")[score_col].transform(
        lambda x: pd.qcut(x.rank(method="first"), 10, labels=False) + 1
    )
    return (
        valid.groupby("decile")[ret_col]
        .mean()
        .reset_index()
        .rename(columns={ret_col: "avg_ret"})
    )


# ── 리포트 출력 ───────────────────────────────────────────────────────────

def _print_report(df: pd.DataFrame) -> None:
    horizons = [
        ("fwd_1m", "1M"),
        ("fwd_3m", "3M"),
        ("fwd_6m", "6M"),
        ("fwd_12m", "12M"),
    ]

    print("\n" + "=" * 68)
    print("Momentum 모듈 IC 분석")
    print("=" * 68)
    print(f"{'Horizon':<10} {'IC_mean':>8} {'IC_std':>8} {'IC_IR':>8} {'HitRate':>9} {'N월':>6}")
    print("-" * 68)

    ic_3m_df = None
    for col, label in horizons:
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

    # 연도별 IC (3M 기준)
    if ic_3m_df is not None and not ic_3m_df.empty:
        print("\n3M Forward Return 기준 연도별 IC:")
        ic_3m_df["year"] = pd.to_datetime(ic_3m_df["as_of_date"]).dt.year
        yearly = ic_3m_df.groupby("year")["ic"].mean()
        for yr, ic in yearly.items():
            bar = ("▓" * int(abs(ic) * 300)) if not np.isnan(ic) else ""
            sign = "+" if ic >= 0 else ""
            print(f"  {yr}: {sign}{ic:.4f}  {bar}")

    # Decile 분석 (3M 기준)
    dec = _decile_analysis(df, "score", "fwd_3m")
    if not dec.empty:
        print("\nDecile 분석 (3M Forward Return 평균):")
        print(f"  {'Decile':<8} {'Avg Return':>12}")
        print(f"  {'-'*22}")
        for _, row in dec.iterrows():
            bar = "█" * int(abs(row["avg_ret"]) * 200)
            sign = "+" if row["avg_ret"] >= 0 else ""
            print(f"  D{int(row['decile']):<7} {sign}{row['avg_ret']:>+.2%}  {bar}")
        spread = dec.loc[dec["decile"] == 10, "avg_ret"].values[0] - \
                 dec.loc[dec["decile"] == 1,  "avg_ret"].values[0]
        print(f"  {'Spread(D10-D1)':<8} {spread:>+.2%}")


# ── main ──────────────────────────────────────────────────────────────────

def run(start: str = "2015-01-01", batch_years: bool = True) -> None:
    log.info("Momentum 백테스트 시작 (from %s, batch_years=%s)", start, batch_years)
    con = duckdb_store.connect()
    con.execute("SET memory_limit='800MB'")

    if batch_years:
        import datetime
        start_yr = int(start[:4])
        end_yr   = datetime.date.today().year
        all_feats = []
        for yr in range(start_yr, end_yr + 1):
            yr_start = f"{yr}-01-01"
            # window 함수에 충분한 선행 데이터 확보 위해 전년 10월부터 로드
            yr_start_with_buf = f"{yr - 1}-10-01"
            yr_end   = f"{yr}-12-31"
            log.info("  배치: %d년 처리 중...", yr)
            chunk = compute_features(con, start=yr_start_with_buf, end=yr_end)
            # 선행 버퍼(전년 데이터) 제거 — 실제 대상 연도만 유지
            chunk = chunk[chunk["as_of_date"].astype(str) >= yr_start]
            all_feats.append(chunk)
            log.info("    → %d rows", len(chunk))
        feats = pd.concat(all_feats, ignore_index=True)
    else:
        log.info("월말 features 추출 중 (단일 쿼리)...")
        feats = compute_features(con, start=start)

    log.info(
        "features 합계: %d rows | tickers=%d | dates=%d",
        len(feats), feats["ticker"].nunique(), feats["as_of_date"].nunique(),
    )

    feats["score"] = compute_scores(feats)

    n_ms = _upsert_module_scores(con, feats)
    n_fr = _upsert_forward_returns(con, feats)
    log.info("저장: module_scores=%d, forward_returns=%d", n_ms, n_fr)

    _print_report(feats)

    log.info("완료")
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Momentum IC backtest")
    p.add_argument("--start", default="2015-01-01", help="백테스트 시작일 (default: 2015-01-01)")
    p.add_argument("--no-batch", action="store_true", help="연도별 배치 분할 비활성화 (단일 쿼리)")
    args = p.parse_args()
    run(start=args.start, batch_years=not args.no_batch)
