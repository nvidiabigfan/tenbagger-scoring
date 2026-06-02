-- 수급 스냅샷에 가격 변동률 컬럼 추가 (전월대비/전주대비)
-- 수집 시점 30일 yfinance 윈도우에서 계산 (별도 히스토리 누적 불필요)
ALTER TABLE supply_snapshots
  ADD COLUMN IF NOT EXISTS price_change_1m_pct NUMERIC,  -- 전월대비 % (30일 윈도우 첫날 종가 대비)
  ADD COLUMN IF NOT EXISTS price_change_1w_pct NUMERIC;  -- 전주대비 % (5거래일 전 종가 대비)
