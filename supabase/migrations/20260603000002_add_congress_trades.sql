-- 미 국회의원(상·하원) 주식 매매 트래킹
-- 출처: Quiver Quantitative /beta/live/congresstrading (무료 공개 피드)
-- 매일 1회 스냅샷 누적 → 수익률 리더보드 + 티커별 의회 순매수 신호

CREATE TABLE IF NOT EXISTS congress_trades (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  representative TEXT NOT NULL,
  bioguide_id TEXT,
  party TEXT,                  -- D / R / I
  house TEXT,                  -- House / Senate
  transaction TEXT,            -- 원문: Purchase / Sale (Full) / Sale (Partial) ...
  side TEXT,                   -- 파생: buy / sell / other
  transaction_date DATE,       -- 실제 거래일
  report_date DATE,            -- 공시일 (transaction_date + 지연)
  amount_min NUMERIC,          -- Range 하한 (Amount)
  range_text TEXT,             -- 예: "$100,001 - $250,000"
  ticker_type TEXT,            -- Stock / etc
  excess_return NUMERIC,       -- Quiver 계산: SPY 대비 초과수익%
  price_change NUMERIC,        -- 종목 수익률%
  spy_change NUMERIC,          -- SPY 수익률%
  last_modified DATE,
  snapshot_date DATE NOT NULL, -- 이 행을 적재한 배치 날짜
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(bioguide_id, ticker, transaction_date, transaction, amount_min)
);

CREATE INDEX IF NOT EXISTS idx_congress_trades_ticker
  ON congress_trades(ticker, transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_congress_trades_rep
  ON congress_trades(representative);
CREATE INDEX IF NOT EXISTS idx_congress_trades_report_date
  ON congress_trades(report_date DESC);

-- 의원별 수익률 리더보드 (SPY 대비 평균 초과수익, 최소 거래수 필터)
CREATE OR REPLACE FUNCTION congress_leaderboard(min_trades INT DEFAULT 8, since_days INT DEFAULT 365)
RETURNS TABLE(
  representative TEXT, party TEXT, house TEXT,
  avg_excess_return NUMERIC, avg_price_change NUMERIC, trade_count BIGINT
)
LANGUAGE sql STABLE AS $$
  SELECT representative,
         max(party)  AS party,
         max(house)  AS house,
         round(avg(excess_return)::numeric, 2) AS avg_excess_return,
         round(avg(price_change)::numeric, 2)  AS avg_price_change,
         count(*) AS trade_count
  FROM congress_trades
  WHERE excess_return IS NOT NULL
    AND transaction_date >= current_date - since_days
  GROUP BY representative
  HAVING count(*) >= min_trades
  ORDER BY avg(excess_return) DESC;
$$;

-- 티커별 최근 의회 순매수 신호
CREATE OR REPLACE FUNCTION congress_netbuy(since_days INT DEFAULT 90)
RETURNS TABLE(ticker TEXT, buys BIGINT, sells BIGINT, net BIGINT, reps BIGINT)
LANGUAGE sql STABLE AS $$
  SELECT ticker,
         count(*) FILTER (WHERE side = 'buy')  AS buys,
         count(*) FILTER (WHERE side = 'sell') AS sells,
         count(*) FILTER (WHERE side = 'buy')
           - count(*) FILTER (WHERE side = 'sell') AS net,
         count(DISTINCT bioguide_id) AS reps
  FROM congress_trades
  WHERE transaction_date >= current_date - since_days
  GROUP BY ticker
  ORDER BY net DESC, buys DESC;
$$;
