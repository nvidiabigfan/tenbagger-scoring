-- ============================================================
-- 텐배거스코어링 초기 스키마
-- ============================================================

-- 1. stocks (종목 마스터)
CREATE TABLE IF NOT EXISTS public.stocks (
    ticker       TEXT PRIMARY KEY,
    company_name TEXT        NOT NULL,
    sector       TEXT        NOT NULL,
    industry     TEXT,
    market_cap   BIGINT,
    exchange     TEXT        NOT NULL,
    logo_url     TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT true,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. analysis_results (통합 분석 결과)
CREATE TABLE IF NOT EXISTS public.analysis_results (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker               TEXT        NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    total_score          NUMERIC(5,2) NOT NULL CHECK (total_score >= 0 AND total_score <= 100),
    signal               TEXT        NOT NULL CHECK (signal IN ('strong_buy','buy','hold','sell')),
    confidence           NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    analyzed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trigger_source       TEXT        NOT NULL CHECK (trigger_source IN ('on_demand','scheduled')),
    report_md            TEXT        NOT NULL DEFAULT '',
    analysis_duration_ms INTEGER
);

-- 3. module_scores (모듈별 점수·근거)
CREATE TABLE IF NOT EXISTS public.module_scores (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id       UUID        NOT NULL REFERENCES public.analysis_results(id) ON DELETE CASCADE,
    module_name       TEXT        NOT NULL,
    score             NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
    signal            TEXT        NOT NULL CHECK (signal IN ('strong_buy','buy','hold','sell')),
    confidence        NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence          JSONB       NOT NULL DEFAULT '{}',
    data_collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version    TEXT        NOT NULL DEFAULT '1.0'
);

-- 4. watchlist (사용자 관심 종목, 복합 PK)
CREATE TABLE IF NOT EXISTS public.watchlist (
    user_id         UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker          TEXT        NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_threshold NUMERIC(5,2),
    alert_enabled   BOOLEAN     NOT NULL DEFAULT true,
    note            TEXT,
    PRIMARY KEY (user_id, ticker)
);

-- 5. ranking_snapshots (일별 상위 100 스냅샷)
CREATE TABLE IF NOT EXISTS public.ranking_snapshots (
    date        DATE         NOT NULL,
    rank        INTEGER      NOT NULL CHECK (rank >= 1 AND rank <= 100),
    ticker      TEXT         NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    score       NUMERIC(5,2) NOT NULL,
    rank_change INTEGER,
    PRIMARY KEY (date, rank)
);

-- 6. alert_history (알림 이력)
CREATE TABLE IF NOT EXISTS public.alert_history (
    id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   UUID         NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker    TEXT         NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    old_score NUMERIC(5,2) NOT NULL,
    new_score NUMERIC(5,2) NOT NULL,
    delta     NUMERIC(5,2) NOT NULL,
    sent_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    channel   TEXT         NOT NULL DEFAULT 'email',
    opened    BOOLEAN      NOT NULL DEFAULT false
);

-- ============================================================
-- 인덱스
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_ar_ticker        ON public.analysis_results(ticker);
CREATE INDEX IF NOT EXISTS idx_ar_analyzed_at   ON public.analysis_results(analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_ms_analysis_id   ON public.module_scores(analysis_id);
CREATE INDEX IF NOT EXISTS idx_rs_date          ON public.ranking_snapshots(date DESC);
CREATE INDEX IF NOT EXISTS idx_ah_user_id       ON public.alert_history(user_id);
CREATE INDEX IF NOT EXISTS idx_wl_ticker        ON public.watchlist(ticker);

-- ============================================================
-- RLS (Row Level Security)
-- ============================================================
ALTER TABLE public.stocks            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_results  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.module_scores     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlist         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ranking_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert_history     ENABLE ROW LEVEL SECURITY;

-- 공개 읽기
CREATE POLICY "stocks_read_all"            ON public.stocks            FOR SELECT USING (true);
CREATE POLICY "analysis_results_read_all"  ON public.analysis_results  FOR SELECT USING (true);
CREATE POLICY "module_scores_read_all"     ON public.module_scores     FOR SELECT USING (true);
CREATE POLICY "ranking_snapshots_read_all" ON public.ranking_snapshots FOR SELECT USING (true);

-- watchlist: 본인만 CRUD
CREATE POLICY "watchlist_select_own" ON public.watchlist FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "watchlist_insert_own" ON public.watchlist FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "watchlist_update_own" ON public.watchlist FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "watchlist_delete_own" ON public.watchlist FOR DELETE USING (auth.uid() = user_id);

-- alert_history: 본인만 읽기
CREATE POLICY "alert_history_read_own" ON public.alert_history FOR SELECT USING (auth.uid() = user_id);
