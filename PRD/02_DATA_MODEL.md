---
created: 2026-05-25
updated: 2026-05-25
tags: [데이터모델, ERD, 텐배거]
folder: 20_Projects/21_텐배거스코어링/PRD
status: draft
---

# 텐배거스코어링 -- 데이터 모델

> 이 문서는 앱에서 다루는 핵심 데이터의 구조를 정의합니다.
> 개발자가 아니어도 이해할 수 있는 "개념적 ERD"입니다.

---

## 전체 구조

```
  ┌────────────────┐
  │     User       │
  │ (Magic Link)   │
  └─┬──────┬───────┘
    │      │
    │1:N   │1:N
    ▼      ▼
  ┌───────┐ ┌──────────┐
  │Watch  │ │ Alert    │
  │list   │ │ History  │
  └──┬────┘ └────┬─────┘
     │N:1        │N:1
     ▼           ▼
  ┌─────────────────────┐
  │        Stock        │
  │   (종목 마스터)       │
  └──┬──────┬──────┬────┘
     │      │      │
     │ 1:N  │ 1:N  │1:N
     ▼      ▼      ▼
  Analysis  Module  Ranking
   Result   Score   Snapshot
     │
     │ 1:N
     ▼
  ModuleScore
  (Reddit / ETF / Analyst / YouTube)
```

---

## 엔티티 상세

### User
서비스에 가입한 사람 (Magic Link 이메일 인증).

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| id | 고유 식별자 (자동 생성, UUID) | abc-123-def | O |
| email | 이메일 (Magic Link 발송 대상) | user@example.com | O |
| display_name | 닉네임 (이메일 앞자리 자동 생성) | user | X |
| created_at | 가입 일시 | 2026-05-25 14:30 | O |
| last_login_at | 마지막 로그인 | 2026-05-25 14:30 | O |
| timezone | 알림 발송 기준 시간대 | Asia/Seoul | X |

### Stock
분석 대상 종목 마스터 (S&P500 + 나스닥100 기준 사전 적재).

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| ticker | 종목 코드 (PK) | AAPL | O |
| company_name | 회사명 | Apple Inc. | O |
| sector | 섹터 | Technology | O |
| industry | 세부 산업 | Consumer Electronics | X |
| market_cap | 시가총액 (USD) | 3000000000000 | O |
| exchange | 거래소 | NASDAQ | O |
| logo_url | 회사 로고 (자동 수집) | https://... | X |
| is_active | 분석 대상 여부 (상폐·합병 시 false) | true | O |
| updated_at | 마스터 데이터 갱신일 | 2026-05-25 | O |

### AnalysisResult
한 종목에 대한 한 시점의 통합 분석 결과.

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| id | 고유 식별자 | xyz-789 | O |
| ticker | 종목 (FK → Stock) | AAPL | O |
| total_score | 통합 점수 (0~100) | 72.5 | O |
| signal | 시그널 (강매수/매수/보유/매도) | buy | O |
| confidence | 종합 신뢰도 (0~1) | 0.85 | O |
| analyzed_at | 분석 시점 | 2026-05-25 22:00 | O |
| trigger_source | 분석 트리거 (on_demand/scheduled) | on_demand | O |
| report_md | 통합 리포트 본문 (Markdown) | "## AAPL 분석..." | O |
| analysis_duration_ms | 분석 소요시간 (모니터링용) | 245000 | X |

### ModuleScore
AnalysisResult에 속한 모듈별 세부 점수·근거.

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| id | 고유 식별자 | mod-456 | O |
| analysis_id | 속한 분석 (FK → AnalysisResult) | xyz-789 | O |
| module_name | 모듈명 (reddit/etf/analyst/youtube/sec/insider…) | reddit | O |
| score | 모듈 점수 (0~100) | 68.0 | O |
| signal | 모듈 시그널 (buy/hold/sell) | buy | O |
| confidence | 모듈 신뢰도 (0~1) | 0.7 | O |
| evidence | 근거 데이터 (JSON: 핫 게시물 URL, 멘션 수, ETF 리스트 등) | `{...}` | O |
| data_collected_at | 데이터 수집 시각 (신선도 판단용) | 2026-05-25 21:55 | O |
| schema_version | 모듈 스키마 버전 (확장성) | "1.0" | O |

### Watchlist
사용자가 등록한 관심 종목.

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| user_id | 사용자 (FK) | abc-123 | O |
| ticker | 종목 (FK) | AAPL | O |
| added_at | 등록 일시 | 2026-05-25 | O |
| alert_threshold | 알림 임계치 (스코어 변동폭) | 10.0 | X |
| alert_enabled | 알림 ON/OFF | true | O |
| note | 사용자 메모 | "다음 어닝 주목" | X |

### RankingSnapshot
랭킹보드용 일별 상위 100 종목 스냅샷.

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| date | 스냅샷 날짜 (PK) | 2026-05-25 | O |
| rank | 순위 (1~100) | 1 | O |
| ticker | 종목 (FK) | NVDA | O |
| score | 그날 스코어 | 92.5 | O |
| rank_change | 전일 대비 순위 변동 | +3 | X |

### AlertHistory
워치리스트 스코어 변화 알림 이력.

| 필드 | 설명 | 예시 | 필수 |
|------|------|------|------|
| id | 고유 식별자 | alt-001 | O |
| user_id | 수신자 (FK) | abc-123 | O |
| ticker | 종목 (FK) | AAPL | O |
| old_score | 직전 스코어 | 60.0 | O |
| new_score | 신규 스코어 | 72.5 | O |
| delta | 변화량 | +12.5 | O |
| sent_at | 발송 시각 | 2026-05-26 09:00 | O |
| channel | 발송 채널 (email/web_push) | email | O |
| opened | 사용자 열람 여부 | false | X |

### 관계
- **User 1:N Watchlist**: 한 사용자는 여러 종목 관심등록
- **User 1:N AlertHistory**: 한 사용자에게 여러 알림 이력 누적
- **Stock 1:N AnalysisResult**: 한 종목은 시점별 여러 분석 결과 보유 (히스토리)
- **AnalysisResult 1:N ModuleScore**: 한 분석은 4~N개 모듈 점수 묶음
- **Stock 1:N RankingSnapshot**: 한 종목은 여러 날짜의 랭킹 스냅샷 가짐
- **Watchlist N:1 Stock**: 여러 사용자가 같은 종목 등록 가능
- **AlertHistory N:1 Stock**: 알림은 특정 종목에 대해 발생

---

## 왜 이 구조인가

### 확장성
- **ModuleScore.module_name + schema_version**: 신규 분석 모듈(SEC·인사이더·어닝스콜) 추가 시 테이블 변경 없이 row만 추가하면 됨 → 허브-스포크 아키텍처와 일치
- **AnalysisResult.report_md**: Markdown 본문을 그대로 저장해 리포트 포맷 변경 시 재생성 불필요
- **ModuleScore.evidence (JSONB)**: 모듈마다 근거 데이터 구조가 달라도 유연하게 저장

### 단순성
- **Watchlist는 join table만**: 별도 ID 없이 (user_id, ticker) 복합키 → 중복 등록 자동 방지
- **RankingSnapshot은 일별 누적**: 매일 1회 배치로 100 row 생성 → 1년치 36,500 row로 부담 없음
- **AnalysisResult 캐싱**: 같은 종목 24시간 내 재분석 요청 시 캐시 결과 반환 → API 비용 절감

### 텐배거 도메인 특화
- **score + signal + confidence 3종 세트**: 단순 점수만으로 판단하지 않고 "신뢰도"까지 함께 노출 → 사용자가 데이터 한계를 이해
- **trigger_source 구분**: on_demand vs scheduled 분석을 분리해 사용 패턴 분석 가능

---

## [NEEDS CLARIFICATION]

- [ ] **ModuleScore.evidence 스키마 표준화**: 모듈별 evidence JSON 구조 사전 정의 필요 (Reddit: 핫 게시물 URL 배열 / ETF: ETF 리스트 + 보유 비중 / 애널리스트: 평가 분포 + 목표가 / 유튜브: 채널·영상 리스트)
- [ ] **AnalysisResult 보관 정책**: 영구 보관 vs 6개월 후 archive? (스코어 히스토리 차트 P2 기능과 연관)
- [ ] **Stock 마스터 갱신 주기**: 매월 1회 시총·섹터 업데이트? 자동 vs 수동?
- [ ] **신규 상장 종목 자동 편입 로직**: IPO 종목을 어떻게 마스터에 추가할지
- [ ] **RankingSnapshot 분석 대상 모집단**: 전 종목 매일 분석은 비용 폭탄. 시총 상위 500개 한정?
