CREATE TABLE IF NOT EXISTS supply_snapshots (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  snapshot_date DATE NOT NULL,
  close_price NUMERIC,
  short_interest_pct NUMERIC,
  volume_vs_avg NUMERIC,
  pc_ratio NUMERIC,
  institutional_net NUMERIC,
  insider_net NUMERIC,
  source_flags JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(ticker, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_supply_snapshots_ticker_date
  ON supply_snapshots(ticker, snapshot_date DESC);
