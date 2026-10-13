# Ledger — log-redaction-fixes (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-2 — 로그 출력에 비밀값이 없다 | Fix | Fixed | Round 1 · `RedactingFilter` + queue 필터 `redact` · `tests/utils/test_log_redaction.py`(`test_project_logging_pipeline_masks_stdout_and_stderr` · `test_queue_overflow_fallback_is_masked` · `test_filter_masks_traceback_and_keeps_exc_info` · `test_filter_masks_stack_info` · `test_filter_masks_message_arguments` · `test_redact_masks_known_secret_shapes`) | 출처: 외부 검수 권장 항목(traceback redaction). 재현: production 구성에서 `logger.exception` 의 원인 예외 `mysql+asyncmy://u:secret42@h/db password=secret42` 와 `Authorization: Bearer …` 가 stdout·stderr 에 각 4줄 그대로 나왔다 |
| F-002 | MED | INV-2 — 외부 로거 경로 | Fix | Fixed | Round 1 · `configure_logging()` 의 uvicorn 로거 부착 · Celery `after_setup_logger`·`after_setup_task_logger` 수신자 · `test_uvicorn_cli_loggers_are_masked` · `test_celery_worker_handlers_are_masked` | `uvicorn main:app` CLI 는 uvicorn 자기 핸들러로 "Exception in ASGI application" traceback 을 낸다. Celery worker 는 기본값(`worker_hijack_root_logger`)으로 root 핸들러를 지우고 자기 핸들러를 단다 — 둘 다 queue 필터를 거치지 않는다 |
| F-003 | LOW | INV-1 — DEBUG 500 응답 `detail` | Fix | Fixed | Round 1 · `main.py` `redact(str(exc))` · `test_debug_500_detail_is_masked` | 응답은 클라이언트로 나간다. DEBUG 에서만 열리는 경로 |
| F-004 | LOW | INV-4 — Redis 최소 버전 | Fix | Fixed | Round 1 · `REDIS_MIN_VERSION`·`ensure_redis_version` · `tests/core/test_redis_version.py`(14건) · 문서 9곳 | 최소 버전이 정의돼 있지 않았고 문서는 근거 없이 "Redis 7"(테스트 이미지)만 적었다. 6.2 미만 서버는 refresh 회전(`GETDEL`)에서야 실패했다 |
| F-005 | LOW | INV-5 — 커버리지 하한의 정본 | Fix | Fixed | Round 2 · `pyproject.toml` `fail_under = 0` · CI `--cov=app --cov-branch --cov-report=term-missing` · `tests/test_coverage_contract.py`(3건) | 하한이 주석(`# fail_under = 80`)으로만 있었고 CI 는 커버리지를 재지 않았다 |

<!--
405 Allow·예외 헤더는 결함이 아니었다(ADR-002) — 회귀 테스트만 더했다(run-log Round 1).
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
