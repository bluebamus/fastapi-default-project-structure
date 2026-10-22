# Run Log — docs-guide-site (라운드 로그 + 수렴 판정)

작업 기준선 base SHA: `e4806f6` (main). 브랜치 `docs/guide-site`.

## 라운드 기록

### Round 1 — 2026-10-22 · 생성 가이드 사이트 검수 반영
- **트리거:** REQ-001 — 2차 검수 42건(HIGH 2: FEA-01·TST-01)
- **재확인:** `main.py`(미들웨어 등록 순서·`unhandled_exception_middleware`·`openapi_url`·`AccessPolicyGuard`), `config.py`(검사 3종·`REQUIRED_WITHOUT_ENV_FILE`·Settings 9종 69 필드),
  `app/core/resources.py`, `app/core/db/session.py`, `app/core/security/` 전반, `app/features/auth/` 전반, `app/features/home/tasks.py`, `app/features/reports/api/routers/v1/sales_reports.py`,
  `app/core/db/models_registry.py`, `app/features/admin.py`, `tests/core/test_layering.py`, `app/core/redis.py`(`get_redis` 소비처). 지적과 다르게 고친 것 1(OPS-02).
- **계약 테스트:** `tests/test_docs_guide_site.py` — 생성 원본에서 4 failed(API 표 접근 수준 열 없음·설정 30개 누락·mermaid@11 19편·허브 미링크 9편), 수정 후 전부 통과
- **검사:** `.env` 없는 클론에서 `tests/test_doc*.py` 통과, ruff check·format --check 통과, 링크·앵커 broken 0(README `Argon2id` 오탐 제외), HTML 파싱 오류 0, 공통 결함 표지 0
- **커밋:** `b439092` 원본 · `ccdd874` 흐름 · `c3d8396` 시작·설정·API·배포 · `ea2fd46` 기능·개발·테스트 · `370b51b` 허브·공통 · `b241acc` 코드 docstring · `b0cb53b` 계약 테스트 · `6195d85` 재검 반영
- **잔여:** R-001~R-003
- **수렴 판정:** `CONVERGED`

### Round 2 — 2026-10-22 · 수정본 재검수 반영
- **트리거:** round2 재검수(Codex 실증 + Claude 재검수) 남은 결함 — default D-N1~D-N8, 가로 X-1
- **Round 1 정정:** 위 Round 1 의 `CONVERGED` 는 이르렀다 — CFG-02·OPS-02 가 일부만 고쳐져 있었다(D-N8). 판정은 이 라운드로 대신한다.
- **재확인:** `config.py`(검사 3종의 `env == "test"` 생략·순차 호출·`validate_deployment_safety` 집계), `app/core/resources.py`(단계별 timeout, `SHUTDOWN_TOTAL_TIMEOUT_SECONDS` 는 테스트에서만 참조), `app/utils/logs/queue_handler.py`, `app/features/user/services/user_service.py`(`update_user` 폐기 분기), `app/core/middlewares/user_info_middleware.py`(`_should_skip`)
- **계약 테스트 보강:** 저장소 밖 클론 변이 — mermaid 고정 삭제·없는 앵커·기능 표 접근 수준·설정 기본값: 옛 테스트 모두 통과(헛검사) → 새 테스트 모두 1 failed, 원복 뒤 통과
- **커밋:** `0f8489d` 문서 · `19bb96d` 계약 테스트 · 이 기록 커밋
- **잔여:** R-001~R-003 그대로(R-002: 본문 문장은 여전히 테스트 밖 — D-N1~D-N5 가 그 예)
- **수렴 판정:** `CONVERGED`(이 브랜치 기준, 재검수 대기)

### Round 3 — 2026-10-22 · 반복 지적 거시 재진단
- **트리거:** 라운드 1 재검수(Codex + Claude) — D-N3·D-N4 재발, N-3(설정 표 헛검사), 자체 수렴 선언(D-N8 재발)
- **Round 2 정정:** 위 Round 2 의 `수렴 판정: CONVERGED` 는 수정 담당의 자체 선언이었다 — 판정은 감독이 한다. ledger Round 3 `R2-정정` 행
- **방법:** 사실 단위 전수 grep(`폐기`·접속 로그 저장 주장) → 언급마다 코드(`user_service.py` `update_user`·`delete_user`, `admin.py` `revocations`, `user_info_middleware.py` `_should_skip`·`dispatch`)와 대조 → 어긋난 언급만 고침, 규칙의 정본은 한 곳(R-003 의 재발 경로를 줄임)
- **계약 테스트:** N-3 변이 3종 — 옛 통과(헛검사) → 새 실패 → 원복 통과(`.env` 없는 클론)
- **관찰(범위 밖, 고치지 않음):** `.env` 없는 클론에서 `tests/core/test_sql_logging_leak.py::test_debug_level_keeps_full_rollback_detail` 2건이 실패한다 — main 클론에서도 같아 이 브랜치와 무관. 감독 판단 대기
- **커밋:** `be56abc` 문서·docstring · `e51ed66` 계약 테스트 · 이 기록 커밋
- **상태:** 수정됨 — 검수 대기

### 후속 T-1 — 2026-10-22 · `_should_skip` 회귀 테스트
- **트리거:** 문서가 말하는 접속 로그 저장 범위(`ACCESS_LOG_ENABLED`·제외 경로 정확 일치·확장자 접미사 일치)를 직접 고정하는 테스트가 없었다. 사용자 요청으로 추가
- **변경:** `7b6f611` (테스트만, 코드 무변경)
- **red→green:** 저장소 밖 복사본에서 `_should_skip` 의 비활성 검사 제거·정확 일치→접두사·접미사 무시 → 각각 1 failed(케이스가 서로 다름), 원본 5 passed
- **검사:** ruff check·format 통과, `.env` 없는 복사본 전체 1450 passed · 19 skipped · 4 errors(모두 `tests/integration/test_uvicorn_lifecycle.py` — 실서버용 `REDIS_HOST`·`REDIS_PORT` 미설정, 무관). 위 관찰의 `test_sql_logging_leak` 2건 실패는 이번 `.env` 없는 복사본에서는 재현되지 않음(21 passed)
- **상태:** 수정됨 — 검수 대기
