# Checklist — config-cleanup (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-19 · 원 명세 (SMTP · 업로드 · SESSION_EXPIRE_SECONDS 삭제 · 만료 정본 · 사용처 계약)
- [x] 요청을 design-baseline §2 에 기록(REQ-001 사용자 결정, REQ-002~004)
- [x] `git grep` 참조 목록 작성(app·scripts·tests·migrations·docs·CI·compose) — run-log
- [x] (F-001) `SMTPSettings` 클래스·팩토리·전역, 배포 검사 `SMTP_PASSWORD`, `.env.example` SMTP 절, 관련 테스트
- [x] (F-002) `UploadSettings` 클래스·팩토리·전역, `.env.example` 업로드 절
- [x] (F-003) `SESSION_EXPIRE_SECONDS` 필드·`.env.example` 줄, docstring·주석을 "관리 세션 만료는 ADMIN_SESSION_* 가 정한다" 로
- [x] (F-004) `tests/core/test_settings_usage.py` — 사용처 계약·예외 목록 낡음 검사·수집기 확인·옛 키 무시
- [x] README(만료 표·업그레이드 노트·검사 표·체크리스트 4)·ARCHITECTURE(§6.1·§6.2·§11·§12·§16·부록)·DEVELOPMENT(§2.2)·HTML 안내서 2편
- [x] `scripts/review_gate.py` 요구 ID 출처에 이 그룹 추가
- [x] 공통 게이트 그린 · fail-on-revert · run-log 갱신

## Round 2 — 2026-10-19 · config-cleanup-2 (API_VERSION 삭제 · 로그 설정 연결 · 예외 목록 삭제)
- [x] 요청을 design-baseline §2 에 기록(REQ-005·006 사용자 결정)
- [x] 현재 로깅 흐름 조사(앱 dictConfig·uvicorn 두 실행 경로·Celery) — run-log
- [x] (F-005) `ApiSettings`·`API_VERSION` 삭제, `.env.example`·문서, `REMOVED_KEYS` 에 추가
- [x] (F-006) `LOG_CONSOLE_ENABLED` — `console_enabled()`·`apply_console_settings()`·경고 한 줄
- [x] (F-007) `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` — `console_formatter_kwargs()`, 기본값 = 기존 포맷, validator
- [x] `UNUSED_ALLOWED`·`test_unused_allowlist_is_not_stale` 삭제(ADR-007)
- [x] README 환경 변수 표·ARCHITECTURE(§2·§6.2·§9.2·§9.6·부록)·server-lifecycle·feature-development 안내서·`.env.example` 주석
- [x] 추가 확인: `python main.py` 경로의 uvicorn 접속 로그 — 결함 없음, 회귀 테스트 3건(`eae4a99`)
- [x] 공통 게이트 그린 · fail-on-revert · run-log 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
