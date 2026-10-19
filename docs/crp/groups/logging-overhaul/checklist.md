# Checklist — logging-overhaul (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-19 · 원 명세 (L1~L9)
- [x] 요청을 design-baseline §2 에 기록(REQ-001~007, 사용자 결정 2026-10-19)
- [x] 현재 로깅 흐름 조사(앱 dictConfig·`python main.py`·`uvicorn main:app`·Celery 수신자·`LogSettings`) — run-log
- [x] (F-001·F-002) L7 — DSN 사용자명, `LOG_SECRET_SETTINGS`·`log_secret_values()`·원문 치환·짧은 값 규칙·계약 테스트
- [x] L2 — `_app_from_path(pathname, logger_name)` 외부 로거 표, `TzFormatter` 대체 헤더, `StaticAppFilter` 삭제
- [x] (F-006) L3 — 필수 필드 검사, `LOG_FILE_FORMAT`
- [x] (F-004) L4 — `LOG_APP_LEVELS`·`parse_app_levels`·`AppLevelFilter`·`lowest_level()`·모르는 헤더 경고
- [x] (F-003·F-007) L1 — `adopt_foreign_handlers`(uvicorn CLI·Celery), "기본값이면 도구 형식" 분기 삭제, 옛 테스트를 "모든 경로 같은 형식" 으로 교체
- [x] (F-005) L6 — `DailySizeRotatingFileHandler`(자정·크기·덮지 않음·보관 일수)
- [x] (F-005·F-008) L5 — `attach_log_files`(웹 `main.py`·Celery 수신자), 프로세스별 + 에러 파일, 옛 키 무시 목록, 경고 조건
- [x] L8 — README 로깅 절·ARCHITECTURE §9·부록·변경 이력·DEVELOPMENT §11·server-lifecycle §5·§6·부록·`.env.example`, 이전 그룹 residual-risk 해소 표시, `docs/review` 두 문서(커밋하지 않음)
- [x] `scripts/review_gate.py` 요구 ID 출처에 이 그룹 추가
- [x] L9 — 공통 게이트·`.env` 없는 저장소 밖 클론·fail-on-revert·실기동 스모크 — run-log
