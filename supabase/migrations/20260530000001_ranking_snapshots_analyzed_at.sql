-- ranking_snapshots에 analyzed_at 컬럼 추가
-- 스냅샷 생성 시점의 분석 일시를 저장해 stale 여부를 UI에 노출하기 위함
ALTER TABLE ranking_snapshots
  ADD COLUMN IF NOT EXISTS analyzed_at timestamptz;
