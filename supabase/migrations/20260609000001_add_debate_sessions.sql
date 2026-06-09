-- 멀티에이전트 토론 세션/라운드/판정 테이블
-- debate.py v2: Groq(강세) vs Gemini(약세) 2라운드 + 심판

create table if not exists debate_sessions (
  id            uuid primary key default gen_random_uuid(),
  ticker        text not null,
  total_rounds  int not null default 2,
  status        text not null default 'running',  -- running | completed | failed
  score_at_gen  numeric not null,
  signal_at_gen text,
  created_at    timestamptz default now(),
  completed_at  timestamptz
);

create table if not exists debate_rounds (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references debate_sessions(id) on delete cascade,
  round_no    int not null,
  bull_agent  text not null,
  bear_agent  text not null,
  bull_text   text not null,
  bear_text   text not null,
  created_at  timestamptz default now()
);

create table if not exists debate_verdicts (
  id              uuid primary key default gen_random_uuid(),
  session_id      uuid not null unique references debate_sessions(id) on delete cascade,
  judge_agent     text not null,
  verdict_text    text not null,
  bull_score      int not null check (bull_score between 0 and 100),
  bear_score      int not null check (bear_score between 0 and 100),
  recommendation  text not null,
  created_at      timestamptz default now()
);

-- RLS: 기존 debates와 동일 정책 (익명 읽기, 쓰기는 service key만)
alter table debate_sessions enable row level security;
alter table debate_rounds enable row level security;
alter table debate_verdicts enable row level security;

create policy "debate_sessions_public_read" on debate_sessions for select using (true);
create policy "debate_rounds_public_read"   on debate_rounds   for select using (true);
create policy "debate_verdicts_public_read" on debate_verdicts for select using (true);

-- ticker + created_at 인덱스 (히스토리 조회용)
create index if not exists debate_sessions_ticker_idx on debate_sessions(ticker, created_at desc);
