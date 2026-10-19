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

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
