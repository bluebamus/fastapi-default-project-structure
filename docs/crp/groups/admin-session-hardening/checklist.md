# Checklist — admin-session-hardening (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-19 · 원 명세 (Redis 서버 세션 · 로그인 이후 CSRF · 기간 필터 · 405 사용자 결정)
- [x] 요청을 design-baseline §2 에 기록(REQ-001 A~C, REQ-002 사용자 결정), 선행 그룹 제약 확인(C-5)
- [x] (F-001) `AdminSessionStore`·`RedisSessionMiddleware`, 설정 `ADMIN_SESSION_*` + `.env.example`, 백엔드 미들웨어 교체·`rotate_session`, `itsdangerous` 제거, 기존 로그인·세션 범위·끄기 테스트 갱신
- [x] (F-002) 즉시 폐기 — `UserService`(provider `get_admin_session_store`)·`UserAdmin` 훅, `SET XX` 되살리기 방지
- [x] (F-003) `AdminCsrfMiddleware`(로그인 검사 통합)·`csrf_rejected`·`base.html` meta·스크립트·로그아웃 POST 전용, sqladmin 상태 변경 요청 목록(run-log), 드리프트 테스트
- [x] (F-004) `LocalDateFilter.between`·`date_range`, 필터 템플릿 두 번째 폼, 단위·화면 테스트
- [x] (F-005) 추가 범위 REQ-003 — `UserAdmin.on_model_change`·`on_model_delete`(커밋 전) + `revokes_admin_sessions` 변경 전후 비교, 테스트 7건(비활성화·강등·일반 수정·삭제·비밀번호·자기 강등·폐기 실패), 변이 6건
- [x] ADR-006 — log-redaction-fixes R-002 에 사용자 결정 덧붙임
- [x] README(환경 표·운영 체크리스트·관리 화면·문제 해결)·ARCHITECTURE(§1·§6·§11·§12·변경 이력)·DEVELOPMENT(§1.3·§2.1)·관리 인증 안내서(세션 구조·시퀀스·CSRF·폐기·쿠키·Redis 키·만료·위협 모델·문제 해결)
- [x] 이전 그룹 상태 덧붙임: admin-login R-001, security-ops-hardening R-001·R-004, log-redaction-fixes R-002
- [x] 공통 게이트 그린 · fail-on-revert · 실기동 스모크 · run-log 갱신

## Round 2 — 2026-10-19 · 후속 (R-004 해소 — 관리 화면 경로의 refresh 폐기)
- [x] 요청 기록(REQ-004), ADR-008
- [x] (F-006) `UserAdmin` `_revoke_credentials` — refresh `revoke_user` + 관리 세션 `revoke_user`, `AdminSessionStore.redis`
- [x] 테스트 갱신(관리 화면 8건 — 네 조건 refresh 폐기·일반 수정 유지·두 저장소 각각 실패 시 미저장), 변이 2건
- [x] 안내서 폐기 표·수명주기 표, README, residual-risk R-004 상태, docs/review 상태
- [x] 공통 게이트 그린(작업 트리·`.env` 없는 클론)

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
