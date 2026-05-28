-- score_history: 주간 성장 점수 스냅샷
-- week_date = 해당 주 월요일 기준 (UNIQUE: ticker + week_date)
-- modules JSONB = {revenue: 80, etf: 65, analyst: 72, ...}

CREATE TABLE IF NOT EXISTS public.score_history (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      TEXT         NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    week_date   DATE         NOT NULL,
    total_score NUMERIC(5,2) NOT NULL,
    signal      TEXT,
    confidence  NUMERIC(4,3),
    modules     JSONB        NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_score_history_ticker_week UNIQUE (ticker, week_date)
);

CREATE INDEX IF NOT EXISTS idx_sh_ticker_week ON public.score_history(ticker, week_date DESC);
CREATE INDEX IF NOT EXISTS idx_sh_week_date   ON public.score_history(week_date DESC);

ALTER TABLE public.score_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read score_history"
    ON public.score_history FOR SELECT USING (true);
