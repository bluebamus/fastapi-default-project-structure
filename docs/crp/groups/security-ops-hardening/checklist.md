# Checklist — security-ops-hardening (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-19 · 원 명세 (바인드 값 · 접속 로그 보존 · 로그인 CSRF · 날짜 필터)
- [x] 요청을 design-baseline §2 에 기록(REQ-001 A~D, REQ-002 사용자 결정), 선행 그룹 제약 확인(C-4)
- [x] (F-001) 엔진 생성 지점 `grep` — `session.py` 3곳 모두 `hide_parameters=True`, 회귀 테스트 4건
- [x] (F-002) `ACCESS_LOG_RETENTION_DAYS` + `.env.example`, `AccessLogRetentionService`·`delete_created_before`, beat 등록, 테스트 10건 + MySQL 마커 1건
- [x] (F-003) 로그인 CSRF(백엔드·템플릿·조립), 기존 로그인 테스트 갱신(공용 `tests/admin_csrf.py`), 새 테스트 9건
- [x] (F-004) `LocalDateFilter` + 템플릿, 7개 뷰 적용, 단위 11건 + 화면 테스트 37건
- [x] README(환경 표·체크리스트 11·관리 화면)·ARCHITECTURE(§4.1·§10·§12·§13·§16)·DEVELOPMENT(§2.1·§10.3)·관리 인증 안내서(시퀀스·분기·실패 표·위협 모델·문제 해결)
- [x] 이전 그룹 상태 덧붙임: admin-login R-002·ADR-009, log-redaction R-001, service-hardening R-002·R-014
- [x] 공통 게이트 그린 · fail-on-revert · 실기동 스모크 · run-log 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
