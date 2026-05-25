---
created: 2026-05-25
updated: 2026-05-25
tags: [Phase, 로드맵, 텐배거]
folder: 20_Projects/21_텐배거스코어링/PRD
status: draft
---

# 텐배거스코어링 -- Phase 분리 계획

> 한 번에 다 만들면 복잡해져서 품질이 떨어집니다.
> Phase별로 나눠서 각각 "진짜 동작하는 제품"을 만듭니다.

---

## Phase 1: MVP (2~3개월)

### 목표
무료 공개 웹 대시보드에서 미국주식 종목 검색 → Reddit·ETF·애널리스트·유튜브 4개 모듈 통합 스코어 + 근거 리포트 출력. 워치리스트 등록·이메일 알림·일별 랭킹보드까지 운영.

### 기능
- [ ] 프로젝트 셋업 + 인프라스트럭처 (Vercel + Supabase + Railway 셋업)
- [ ] **허브-스포크 아키텍처** (Analyzer 공통 인터페이스 정의: name/weight/analyze())
- [ ] **Reddit 분석 모듈** (PRAW로 r/wallstreetbets·r/stocks 멘션·감성 분석)
- [ ] **ETF 편입 분석 모듈** (ETF.com 또는 etfdb holdings 크롤링/API)
- [ ] **애널리스트·PER 분석 모듈** (Yahoo Finance API 또는 yfinance)
- [ ] **유튜브 분석 모듈** (YouTube Data API + LLM 영상 요약·종목 추출)
- [ ] **스코어링 엔진** (가중치 설정 + 룰 필터 + 통합 점수 산출)
- [ ] **Magic Link 인증** (Supabase Auth)
- [ ] **종목 검색 + 자동완성** (Stock 테이블 사전 적재 + 풀텍스트 검색)
- [ ] **On-demand 분석 페이지** (종목 입력 → 진행률 → 통합 리포트)
- [ ] **워치리스트 CRUD** (추가/삭제/임계치 설정)
- [ ] **일일 배치 스케줄러** (워치리스트 종목 매일 재분석 + 랭킹 스냅샷)
- [ ] **스코어 변화 이메일 알림** (Supabase Edge Function + Resend)
- [ ] **상위 100 랭킹 보드** (RankingSnapshot 조회 + 일별 변동 표시)
- [ ] **배포** (Vercel 프론트 + Railway 백엔드 + Supabase DB)

### 데이터
- User, Stock, AnalysisResult, ModuleScore (4개 모듈만), Watchlist, RankingSnapshot, AlertHistory

### 인증
- Magic Link (Supabase Auth)

### "진짜 제품" 체크리스트
- [ ] 실제 DB 연결 (Supabase Postgres, 목업 데이터 X)
- [ ] 실제 Magic Link 인증 (하드코딩된 비밀번호 X)
- [ ] 실제 서버에 배포 (Vercel + Railway, localhost X)
- [ ] 다른 사람이 URL로 접속해서 써볼 수 있음
- [ ] 4개 분석 모듈 모두 실제 외부 API 호출 (모킹 X)
- [ ] 일일 배치가 cron으로 자동 실행되어 워치리스트 종목 재분석
- [ ] 스코어 변화 시 실제 이메일 발송

### Phase 1 시작 프롬프트
```
이 PRD를 읽고 Phase 1을 구현해주세요.
@PRD/01_PRD.md
@PRD/02_DATA_MODEL.md
@PRD/04_PROJECT_SPEC.md

Phase 1 범위:
- 4개 분석 모듈 (Reddit / ETF / 애널리스트 / 유튜브)
- 허브-스포크 아키텍처 (Analyzer 공통 인터페이스)
- 스코어링 엔진 (가중치 + 룰 필터)
- Magic Link 인증
- 종목 검색 + 자동완성
- On-demand 분석 페이지
- 워치리스트 + 이메일 알림
- 일별 배치 + 상위 100 랭킹 보드
- Vercel + Supabase + Railway 배포

구현 순서 권장:
1. Stock 마스터 사전 적재 (S&P500 + 나스닥100)
2. Analyzer 인터페이스 + 4개 모듈 각각 구현 (병렬 가능)
3. 스코어링 엔진 + AnalysisResult 저장
4. Next.js 프론트 (검색 → 결과 페이지)
5. Supabase Auth + Watchlist
6. 배치 스케줄러 + 알림 + 랭킹보드

반드시 지켜야 할 것:
- 04_PROJECT_SPEC.md의 "절대 하지 마" 목록 준수
- 실제 DB 연결 (목업 X)
- 실제 인증 (하드코딩 X)
- "투자 자문 아님" 면책 푸터 표시
- API 키는 .env에만
```

---

## Phase 2: 확장 (1.5~2개월)

### 전제 조건
- Phase 1이 안정적으로 배포되어 1개월 이상 운영
- MAU 50명 이상, 워치리스트 등록 종목 200개 이상

### 목표
재방문 유도 기능 + 바이럴 요소 + 분석 모듈 추가로 "다른 스크리너와 명확히 차별화".

### 기능
- [ ] **SEC 공시 분석 모듈** (EDGAR API 기반 10-K/8-K 빈도·키워드 분석)
- [ ] **인사이더 거래 모듈** (Form 4 공시 → CEO/CFO 매수·매도 시그널)
- [ ] **종목 비교 기능** (2~3개 종목 통합 스코어·모듈별 점수 나란히 표시)
- [ ] **스코어 히스토리 차트** (Recharts로 종목별 시계열 그래프)
- [ ] **소셜 공유 (X 공유 + OG 이미지 동적 생성)** (`@vercel/og` 활용)
- [ ] **PWA 최적화** (모바일 홈화면 추가 + 푸시 알림 옵션)
- [ ] **SEO 랜딩 페이지 자동 생성** (분석 종목별 `/stocks/AAPL` 정적 라우트 + 메타태그)

### 추가 데이터
- ModuleScore에 sec / insider 추가 (테이블 변경 없이 module_name만 추가)
- AnalysisResult 보관 정책 명문화 (히스토리 차트용)

### 통합 테스트
- Phase 1 기능이 여전히 정상 동작하는지 확인
- 신규 모듈 추가로 스코어 변동성 검증 (가중치 재조정 필요할 수 있음)

---

## Phase 3: 고도화 (2~3개월)

### 전제 조건
- Phase 1 + 2가 안정적으로 운영 중
- MAU 500명 이상, 한국어 투자 커뮤니티 자발적 언급 다수
- 본인의 인지도 효과(블로그·유튜브 구독자) 검증 완료

### 목표
**차별화 + 수익화 옵션 검증**. 무료 사용자는 유지하되 Pro 구독으로 운영비 회수 + 본인 브랜드 확장.

### 기능
- [ ] **어닝스콜 감정분석 모듈** (Earnings Call Transcript → LLM 톤 분석)
- [ ] **공매도 비율 모듈** (Short interest 추이 + 스퀴즈 가능성 지표)
- [ ] **백테스트 시스템** (과거 스코어 vs 실제 주가 수익률 → 모듈별 가중치 검증)
- [ ] **모듈별 가중치 사용자 커스터마이징** (Pro 사용자 슬라이더)
- [ ] **공개 REST API + 문서화** (Swagger)
- [ ] **Pro 구독 (Stripe)** (무제한 워치리스트·실시간 알림·종목별 알림 채널·API 액세스)
- [ ] **관리자 대시보드** (모듈 상태·API 비용·사용자 활동 모니터링)

### 주의사항
- **비용 발생 가능성 ↑**: LLM 호출(어닝스콜·유튜브) + 백테스트 컴퓨팅 → 무료 사용자 한도 강제 필요
- **법적 리스크**: Pro 구독 시작하면 "투자 자문" 경계 모호. 약관·면책 조항 변호사 검토 권장
- **외부 서비스 의존성**: Stripe(결제) / Resend(이메일) / 각종 API 요금제 모니터링

---

## Phase 로드맵 요약

| Phase | 핵심 기능 | 예상 기간 | 상태 |
|-------|----------|----------|------|
| Phase 1 (MVP) | 4개 분석 모듈 + 검색 + 워치리스트 + 알림 + 랭킹보드 | 2~3개월 | 시작 전 |
| Phase 2 (확장) | SEC + 인사이더 + 비교 + 히스토리 + 소셜 공유 + PWA + SEO | +1.5~2개월 | Phase 1 완료 후 |
| Phase 3 (고도화) | 어닝스콜 + 공매도 + 백테스트 + 가중치 커스텀 + API + Pro 구독 | +2~3개월 | Phase 2 완료 후 |

총 예상 기간: **약 6~8개월** (혼자 사이드 프로젝트 기준)
