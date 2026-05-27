-- reddit_snapshots: GitHub Actions에서 수집한 Reddit 데이터 저장
-- (백엔드 서버 IP 차단 우회 목적 — 수집은 Actions에서, 조회는 백엔드에서)

CREATE TABLE IF NOT EXISTS public.reddit_snapshots (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker        TEXT         NOT NULL REFERENCES public.stocks(ticker) ON DELETE CASCADE,
    post_count    INTEGER      NOT NULL DEFAULT 0,
    total_upvotes INTEGER      NOT NULL DEFAULT 0,
    collected_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reddit_snapshots_ticker_collected
    ON public.reddit_snapshots(ticker, collected_at DESC);
