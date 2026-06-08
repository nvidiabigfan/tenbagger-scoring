-- 강세 vs 약세 토론 리포트 테이블
-- 종목당 최신 1건만 유지 (upsert on ticker PK)
create table if not exists debates (
  ticker         text primary key,
  bull_text      text not null,
  bear_text      text not null,
  score_at_gen   numeric not null,
  signal_at_gen  text,
  model          text default 'llama-3.3-70b-versatile',
  generated_at   timestamptz default now()
);

-- RLS: 익명 읽기 허용, 쓰기는 service key (batch)만
alter table debates enable row level security;
create policy "debates_public_read" on debates for select using (true);
