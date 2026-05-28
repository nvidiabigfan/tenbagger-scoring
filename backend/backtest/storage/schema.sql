-- 백테스트용 DuckDB 스키마.
-- 위치: backend/backtest/data/warehouse.duckdb (gitignore)
-- 운영 Supabase와 완전 분리. 분석/백테스트 전용 OLAP 저장소.

-- ─────────────────────────────────────────────────────────────
-- 가격 시계열 (yfinance daily OHLCV)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prices (
    ticker      VARCHAR     NOT NULL,
    date        DATE        NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE      NOT NULL,
    adj_close   DOUBLE      NOT NULL,   -- 배당·분할 조정 종가
    volume      BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);

-- ─────────────────────────────────────────────────────────────
-- Finviz raw snapshot (매일 1회 저장 → PIT 재구성용)
-- key-value 전체를 JSON으로 보존하여 사후 어떤 필드도 추출 가능
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS finviz_snapshots (
    ticker          VARCHAR     NOT NULL,
    snapshot_date   DATE        NOT NULL,
    metrics_json    JSON        NOT NULL,   -- get_metrics() 전체 dict
    fetched_at      TIMESTAMP   NOT NULL,
    PRIMARY KEY (ticker, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_finviz_date ON finviz_snapshots(snapshot_date);

-- ─────────────────────────────────────────────────────────────
-- 분기 재무제표 (yfinance quarterly_income_stmt)
-- Revenue 모듈 PIT 백테스트용
-- period_end: 분기 마지막일 (2024-03-31 등)
-- avail_date:  실제 사용 가능 일자 = period_end + 45일 (보수적 어닝 래그)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quarterly_fundamentals (
    ticker          VARCHAR     NOT NULL,
    period_end      DATE        NOT NULL,    -- 분기 말일 (e.g. 2024-03-31)
    avail_date      DATE        NOT NULL,    -- period_end + 45일 (look-ahead 방지)
    total_revenue   DOUBLE,                  -- 분기 총매출 (USD)
    gross_profit    DOUBLE,
    net_income      DOUBLE,
    eps_diluted     DOUBLE,
    PRIMARY KEY (ticker, period_end)
);
CREATE INDEX IF NOT EXISTS idx_qfund_avail ON quarterly_fundamentals(ticker, avail_date);

-- ─────────────────────────────────────────────────────────────
-- SEC EDGAR Form 4 (내부자 거래) 원시 데이터
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS form4_transactions (
    accession_no    VARCHAR     NOT NULL,    -- SEC accession (unique)
    ticker          VARCHAR     NOT NULL,
    cik             VARCHAR     NOT NULL,
    filing_date     DATE        NOT NULL,
    transaction_date DATE,
    insider_name    VARCHAR,
    insider_title   VARCHAR,
    transaction_code VARCHAR,                 -- P=Purchase, S=Sale, A=Award, etc
    shares          BIGINT,
    price_per_share DOUBLE,
    total_value     DOUBLE,
    PRIMARY KEY (accession_no, insider_name, transaction_date)
);
CREATE INDEX IF NOT EXISTS idx_form4_ticker_date ON form4_transactions(ticker, filing_date);

-- ─────────────────────────────────────────────────────────────
-- Wikipedia pageviews (buzz 모듈 PIT 입력)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wiki_pageviews (
    article         VARCHAR     NOT NULL,
    date            DATE        NOT NULL,
    views           BIGINT      NOT NULL,
    PRIMARY KEY (article, date)
);

-- ─────────────────────────────────────────────────────────────
-- 모듈 스코어 시계열 (백테스트 결과)
-- 매월 말일 시점으로 전 종목 각 모듈 점수 계산해서 저장
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS module_scores (
    ticker          VARCHAR     NOT NULL,
    as_of_date      DATE        NOT NULL,    -- 평가 기준일 (월말)
    module          VARCHAR     NOT NULL,    -- revenue/etf/analyst/...
    score           DOUBLE      NOT NULL,    -- 0~100
    confidence      DOUBLE      NOT NULL,    -- 0~1
    evidence_json   JSON,
    PRIMARY KEY (ticker, as_of_date, module)
);
CREATE INDEX IF NOT EXISTS idx_scores_date ON module_scores(as_of_date);

-- ─────────────────────────────────────────────────────────────
-- 통합 스코어 (가중평균 후)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS composite_scores (
    ticker          VARCHAR     NOT NULL,
    as_of_date      DATE        NOT NULL,
    total_score     DOUBLE      NOT NULL,
    signal          VARCHAR     NOT NULL,
    confidence      DOUBLE      NOT NULL,
    active_modules  VARCHAR[],
    PRIMARY KEY (ticker, as_of_date)
);

-- ─────────────────────────────────────────────────────────────
-- Forward returns (백테스트 검증 타겟)
-- 각 as_of_date에서 N개월 후 수익률 사전 계산해두면 IC 계산 빠름
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forward_returns (
    ticker          VARCHAR     NOT NULL,
    as_of_date      DATE        NOT NULL,
    ret_1m          DOUBLE,
    ret_3m          DOUBLE,
    ret_6m          DOUBLE,
    ret_12m         DOUBLE,
    ret_24m         DOUBLE,
    ret_36m         DOUBLE,
    PRIMARY KEY (ticker, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_fret_date ON forward_returns(as_of_date);
