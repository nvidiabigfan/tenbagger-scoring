---
created: 2026-05-25
updated: 2026-05-25
tags: [CLAUDE, 작업규칙, 텐배거]
folder: 20_Projects/21_텐배거스코어링
status: active
---

# 21_텐배거스코어링 -- Claude 작업 규칙

## 프로젝트 한 줄
미국주식 종목 → Reddit·ETF·애널리스트·유튜브 4개 모듈 통합 스코어링 → 텐배거 후보 가능성 0~100점 + 근거 리포트 (무료 공개 웹 대시보드).

## 세션 시작 시 필독
1. [SESSION_LOG.md](./SESSION_LOG.md) RESUME_POINT 확인
2. [PRD/01_PRD.md](./PRD/01_PRD.md) 핵심 기능 표 확인
3. [PRD/04_PROJECT_SPEC.md](./PRD/04_PROJECT_SPEC.md) 의 "절대 하지 마 / 항상 해" 목록 적용

## 아키텍처 핵심 원칙 (불변)
- **허브-스포크**: 분석 모듈(스포크)은 `analyzers/base.py` Analyzer 인터페이스 준수 의무
- **모듈 인터페이스 시그니처**: `analyze(ticker) -> {score, signal, evidence, confidence, timestamp, schema_version}`
- **모듈 간 직접 참조 금지**: 스코어링 엔진(허브)을 통해서만 결과 결합
- **신규 모듈 추가**: `analyzers/` 폴더에 파일 떨굼 + `weights.yaml`에 가중치 등록 → 자동 인식

## 작업 우선순위
- **Phase 1 (현재)**: MVP 4개 모듈 + 검색 + 워치리스트 + 알림 + 랭킹보드
- **Phase 2 이후 기능 요청 시**: 일단 거절하고 Phase 1 안정화 우선

## 도메인 규칙 (필수 준수)
- **표현 완곡화**: signal=buy 라도 UI에는 "긍정 시그널" / "주목 가치 있음" 등으로 표시. **"매수하세요" 같은 직접 권유 금지**
- **모든 페이지 푸터**: "본 서비스는 투자 자문이 아니며 참고용입니다"
- **분석 결과 신뢰도 항상 노출**: score만 보여주지 말고 confidence(0~1) 병기
- **티커 검증**: A-Z + 점 1개 이내, 5자 이하만 허용 (인젝션 방지)
- **외부 API 호출**: 항상 timeout + retry + circuit breaker 패턴

## 비용 관리
- **분석 결과 24시간 캐시 기본** (같은 종목 재요청 시 캐시 반환)
- **무료 사용자 일일 분석 한도 설정 필수** (LLM 비용 폭주 방지)
- **YouTube Data API 쿼터 10,000 unit/일** 한도 관리 (모듈에서 명시적 체크)

## 의사결정 보고
- 신규 분석 모듈 추가 결정은 PRD 03_PHASES Phase별 범위 안에서만
- 스키마 변경은 사용자 확인 후 `supabase/migrations/` 통해서만
- 외부 신규 API 도입 시 비용 시뮬레이션 함께 제시

## 관련 Vault 노트
- [[09_텔레그램신호감지]] -- Reddit 모듈 설계 참고
- [[14_미국주식투자어시스턴트]] -- 미국주식 데이터 패턴
- [[20_ETF패시브플로우트래커]] -- ETF 모듈 데이터 소스
