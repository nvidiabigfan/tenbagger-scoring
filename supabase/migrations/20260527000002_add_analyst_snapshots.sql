-- analyst_snapshots: 종목별 애널리스트 커버리지 이력 스냅샷
-- coverage expansion (0→N 커버리지 증가)을 시그널로 활용하기 위한 테이블
CREATE TABLE IF NOT EXISTS analyst_snapshots (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker text NOT NULL,
  snapshot_date date NOT NULL DEFAULT CURRENT_DATE,
  ratings_count_1y integer NOT NULL DEFAULT 0,  -- 최근 12개월 총 ratings 수
  created_at timestamptz DEFAULT now(),
  UNIQUE(ticker, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_analyst_snapshots_ticker_date
  ON analyst_snapshots(ticker, snapshot_date DESC);
