---
created: 2026-05-25
updated: 2026-05-25
tags: [스펙, AI규칙, 텐배거]
folder: 20_Projects/21_텐배거스코어링/PRD
status: draft
---

# 텐배거스코어링 -- 프로젝트 스펙

> AI가 코드를 짤 때 지켜야 할 규칙과 절대 하면 안 되는 것.
> 이 문서를 AI에게 항상 함께 공유하세요.

---

## 기술 스택

| 영역 | 선택 | 이유 |
|------|------|------|
| 프론트엔드 프레임워크 | Next.js 16 (App Router) | 서버 컴포넌트로 대용량 데이터 처리 효율적, AI 코딩 생태계 최상위, SEO 강함(랭킹보드·종목 페이지) |
| 스타일링 | Tailwind CSS v4 + shadcn/ui | 2026년 표준 조합, AI가 가장 잘 생성하는 UI 스택 |
| 차트 | Recharts (P1) + Tremor (P2 대시보드) | 무료, React 친화, 학습 곡선 낮음 |
| 인증 | Supabase Auth (Magic Link) | 비밀번호 관리 불필요, 무료 티어, Supabase DB와 통합 |
| DB | Supabase Postgres | 무료 500MB, RLS로 행 단위 보안, Edge Function 결합 가능 |
| 분석 백엔드 | Python 3.12 + FastAPI | 데이터 사이언스 라이브러리 풍부 (yfinance/PRAW/google-api-python-client), 분석 모듈 작성에 최적 |
| 배치 스케줄러 | GitHub Actions (P1) → Supabase Cron (P2) | GitHub Actions 무료, 일일 배치에 충분 |
| 이메일 발송 | Resend | Magic Link + 알림 통합 가능, 월 3,000건 무료 |
| 프론트 배포 | Vercel | Next.js 1순위, 무료 티어 충분, OG 이미지 동적 생성(@vercel/og) |
| 백엔드 배포 | Railway 또는 Fly.io | Python FastAPI 컨테이너 배포 쉬움, Vercel과 도메인 분리 |
| LLM (유튜브 요약·어닝스콜) | Claude Haiku 4.5 또는 Gemini Flash 2.5 | 가성비 최강, 한국어 출력 품질 우수 |

---

## 프로젝트 구조

```
21_텐배거스코어링/
├── frontend/                  # Next.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/        # 로그인·매직링크 콜백
│   │   │   ├── stocks/[ticker]/  # 종목 상세 (SEO 랜딩)
│   │   │   ├── watchlist/
│   │   │   ├── ranking/
│   │   │   └── api/           # Next.js API (proxy 또는 가벼운 BFF)
│   │   ├── components/        # shadcn/ui 기반 컴포넌트
│   │   ├── lib/               # supabase client, fetcher, utils
│   │   └── types/             # 공유 타입 정의 (zod 권장)
│   ├── .env.local             # NEXT_PUBLIC_SUPABASE_URL 등
│   └── package.json
│
├── backend/                   # Python FastAPI
│   ├── app/
│   │   ├── analyzers/         # 분석 모듈 (허브-스포크 스포크)
│   │   │   ├── base.py        # Analyzer 추상 클래스 (인터페이스)
│   │   │   ├── reddit.py
│   │   │   ├── etf.py
│   │   │   ├── analyst.py
│   │   │   └── youtube.py
│   │   ├── scoring/           # 스코어링 엔진 (허브)
│   │   │   ├── engine.py      # 가중치·룰필터·통합 점수
│   │   │   └── weights.yaml   # 모듈별 가중치 설정 (코드 분리)
│   │   ├── routes/            # FastAPI 라우터
│   │   ├── jobs/              # 일일 배치 (랭킹 스냅샷·워치리스트 재분석)
│   │   ├── db/                # Supabase Python client
│   │   └── core/              # 설정·로깅
│   ├── tests/                 # pytest
│   ├── .env                   # API 키
│   ├── requirements.txt
│   └── Dockerfile
│
├── .github/workflows/         # GitHub Actions (일일 배치)
├── supabase/                  # 마이그레이션·RLS 정책
└── PRD/                       # 본 디자인 문서
```

---

## 절대 하지 마 (DO NOT)

> AI에게 코드를 시킬 때 이 목록을 반드시 함께 공유하세요.

- [ ] API 키나 비밀번호를 코드에 직접 쓰지 마 (.env 파일 사용, .gitignore 등록 필수)
- [ ] 기존 DB 스키마를 임의로 변경하지 마 (supabase/migrations 통해서만)
- [ ] 테스트 없이 새 분석 모듈을 메인에 머지하지 마 (analyzers/*.py 마다 pytest 필수)
- [ ] 목업/하드코딩 데이터로 "완성"이라고 하지 마 (실제 API 호출 → 캐싱은 별도)
- [ ] package.json/requirements.txt의 기존 의존성 버전을 임의로 변경하지 마
- [ ] **"매수 추천", "이 종목 사세요" 같은 단정적 표현을 UI에 절대 노출 금지** (signal은 buy/hold/sell이지만 화면 표시는 "긍정/중립/부정 시그널" 등 완곡한 표현)
- [ ] **사용자 입력을 그대로 SQL/API에 전달 금지** (티커 화이트리스트 검증 필수, 인젝션 방지)
- [ ] **분석 결과 캐시 없이 매번 외부 API 호출 금지** (24시간 캐시 기본)
- [ ] Reddit/YouTube API 쿼터 한도 초과 시 자동 재시도 금지 (조용히 실패 처리)
- [ ] **무료 사용자 분석 한도 없는 채로 배포 금지** (LLM 비용 폭주 방지)
- [ ] 분석 모듈끼리 직접 참조 금지 (반드시 base.py 인터페이스 통해서만 호출)

---

## 항상 해 (ALWAYS DO)

- [ ] 변경하기 전에 계획을 먼저 보여줘 (특히 스키마·인터페이스 변경)
- [ ] 환경변수는 .env.local(프론트)·.env(백) 또는 Vercel/Railway Secrets에 저장
- [ ] 에러가 발생하면 사용자에게 친절한 메시지 표시 (단, 내부 에러 디테일은 노출 금지)
- [ ] 모바일에서도 사용 가능한 반응형 디자인 (모바일 우선 설계)
- [ ] **"본 서비스는 투자 자문이 아니며 참고용입니다" 푸터 모든 페이지 표시**
- [ ] **새 분석 모듈 추가 시 base.Analyzer 인터페이스 준수** (analyze(ticker) → {score, signal, evidence, confidence, timestamp})
- [ ] **외부 API 호출은 항상 timeout + retry + circuit breaker** (외부 장애로 전체 분석 멈춤 방지)
- [ ] **모든 분석 결과에 confidence 점수 표시** (사용자가 데이터 한계 이해)
- [ ] **분석 소요시간 측정·로깅** (성능 회귀 감지)
- [ ] **Supabase RLS(Row Level Security) 활성화** (Watchlist는 본인 것만 조회·수정)
- [ ] **테스트는 실제 API 모킹 사용** (pytest-vcr 또는 responses)

---

## 테스트 방법

```bash
# 프론트엔드
cd frontend
npm install
npm run dev              # 로컬 실행 (http://localhost:3000)
npx tsc --noEmit         # 타입 체크
npm run build            # 빌드 확인
npm run lint             # 린트

# 백엔드
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload  # 로컬 실행 (http://localhost:8000)
pytest                   # 테스트 실행
pytest --cov=app         # 커버리지 (목표 70% 이상)
ruff check .             # 린트
mypy app/                # 타입 체크

# 통합 테스트
# 1. Supabase 로컬 시작: supabase start
# 2. 환경변수 설정 (.env.local + .env)
# 3. 프론트 + 백 동시 실행 후 종목 검색 시나리오 수동 검증
```

---

## 배포 방법

### Phase 1 배포 구성
1. **Supabase**: 프로젝트 생성 → DB 마이그레이션 → RLS 정책 적용 → Magic Link 설정
2. **Vercel** (프론트): GitHub 연동 → 환경변수 등록 → 자동 배포
3. **Railway** (백엔드): Dockerfile 기반 배포 → 환경변수 등록 → 도메인 발급
4. **GitHub Actions** (배치): `.github/workflows/daily-batch.yml` 매일 21:00 KST 실행
5. **Resend**: API 키 발급 → Supabase Edge Function에서 호출
6. **도메인**: 추후 결정 (현재는 Vercel 서브도메인 사용)

### 환경 분리
- **Local**: docker-compose로 Supabase 로컬 + Python 백 + Next.js
- **Production**: Vercel + Railway + Supabase 클라우드

---

## 환경변수

### 프론트엔드 (.env.local)
| 변수명 | 설명 | 어디서 발급 |
|--------|------|------------|
| NEXT_PUBLIC_SUPABASE_URL | Supabase 프로젝트 URL | Supabase 대시보드 |
| NEXT_PUBLIC_SUPABASE_ANON_KEY | Supabase 익명 키 | Supabase 대시보드 |
| NEXT_PUBLIC_BACKEND_URL | Python 백엔드 URL | Railway 대시보드 |

### 백엔드 (.env)
| 변수명 | 설명 | 어디서 발급 |
|--------|------|------------|
| SUPABASE_URL | Supabase 프로젝트 URL | Supabase 대시보드 |
| SUPABASE_SERVICE_KEY | Supabase 서비스 키 (서버 전용) | Supabase 대시보드 |
| REDDIT_CLIENT_ID | Reddit API ID | reddit.com/prefs/apps |
| REDDIT_CLIENT_SECRET | Reddit API Secret | reddit.com/prefs/apps |
| YOUTUBE_API_KEY | YouTube Data API v3 | Google Cloud Console |
| ANTHROPIC_API_KEY | Claude API (유튜브 요약) | console.anthropic.com |
| RESEND_API_KEY | 이메일 발송 | resend.com |
| ETFDB_API_KEY | ETF holdings (선택) | etfdb.com |

> .env / .env.local 파일에 저장. 절대 GitHub에 올리지 마세요.
> .gitignore에 `.env*` 반드시 포함.

---

## 도메인 규칙 (텐배거스코어링 특화)

- **티커 검증**: A-Z + 점 1개 이내, 5자 이하 (예: AAPL, BRK.B)
- **종목명 검색**: 유사도 매칭 (fuzzy search) 허용
- **스코어 표시**: 항상 정수 + "/100" 형식 (예: "72/100")
- **시그널 컬러**: 강매수=짙은 녹색 / 매수=연녹색 / 보유=회색 / 매도=빨강 (다만 텍스트는 완곡 표현)
- **타임존**: 모든 timestamp UTC 저장, 표시는 사용자 timezone 변환
- **숫자 포맷**: 시총은 한국식 (조/억) + 영문식 (B/M) 병기

---

## [NEEDS CLARIFICATION]

### 결정 완료 (2026-05-25)
- [x] **Reddit API 정책**: Phase 1.5 보류 결정 → analyzers/reddit.py 미구현
- [x] **YouTube Data API 쿼터 산정**: 종목당 ~102 units → 일 80종목 한도. 단 LLM 비용 검증 후 활성화 결정 → Phase 1은 비활성 (`weights.yaml` enabled: false)

### 남은 미결
- [ ] **LLM 비용 모델 결정**: 유튜브/어닝스콜 요약용 (Claude Haiku 4.5 vs Gemini Flash 2.5) -- 유튜브 모듈 활성화 직전 결정
- [ ] **Vercel @vercel/og 함수 비용**: P2 소셜 공유 시 OG 이미지 호출 폭증 가능성
- [ ] **Supabase 무료 티어 한계**: DB 500MB·MAU 50K. Phase 2 이후 Pro 플랜($25/월) 필요 시점 산정
- [ ] **Railway vs Fly.io 비교**: 백엔드 배포 플랫폼 최종 선택 (월 사용량 시뮬레이션 필요)
- [ ] **Magic Link 발송 한도**: Resend 무료 3,000건/월 → 사용자 증가 시 부족 가능
