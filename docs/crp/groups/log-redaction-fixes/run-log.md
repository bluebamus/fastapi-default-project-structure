# Run Log — log-redaction-fixes (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `0a52fb6` (main, 그룹 개설 직전). 브랜치 `fix/log-redaction`.

## 라운드 기록

### Round 1 — 2026-10-13 · 원 명세 (traceback 마스킹 · 접속 로그 유지 · 405 Allow · Redis 버전 · 보호 현황 조사)
- **트리거:** REQ-001
- **재현(수정 전):** 저장소 밖 스크립트가 `app_settings.ENV="production"` 으로 `configure_logging(force=True)` 를 적용하고(실제
  dictConfig — queue → listener → `console`(stdout)·`error_console`(stderr)), `raise RuntimeError("Authorization: Bearer …") from
  ValueError("connect failed mysql+asyncmy://u:secret42@h/db password=secret42")` 를 `logger.exception(..., stack_info=True)` 로 남겼다.
  stdout·stderr **각각 4줄**에 비밀값이 그대로 나왔다(원인 예외의 소스 줄·메시지, 바깥 예외의 소스 줄·메시지). 수정 후 0줄,
  `***` 표식·체인 문구·파일·줄·Stack 은 남는다.
- **핸들러 경로 확인:** 앱·SQLAlchemy·`python main.py` 의 uvicorn 3종은 root(또는 공유) queue 핸들러 하나 → 필터가 덮는다.
  `uvicorn main:app` CLI 는 uvicorn 자기 핸들러(`uvicorn.error` 가 "Exception in ASGI application"·startup 실패 traceback 을 낸다,
  `httptools_impl.py:427`·`lifespan/on.py:97`). Celery worker 는 `setup_logging_subsystem` 이 `worker_hijack_root_logger` 로 root
  핸들러를 비우고 자기 핸들러를 단다 — 둘 다 queue 를 거치지 않아 별도로 덮었다(ADR-001). 큐 포화 fallback 은 필터 뒤라 덮인다.
- **405 확인:** `DELETE /health` → 405 `allow: GET`, `POST /api/v1/blog/posts`(토큰 없음) → 401 `www-authenticate: Bearer` — 이미 정상(ADR-002).
  `PUT /api/v1/blog/posts` → `allow: POST`(GET 누락) — Starlette 동작, R-002.
- **Redis 명령 조사:** `app/` 전체에서 Redis 호출은 `rate_limit.py`(`SET … EX NX`·`INCR`·`TTL`·`DEL`), `refresh_store.py`
  (`SET EX`·`SADD`·`EXPIRE`·`GETDEL`·`EXISTS`·`SMEMBERS`·`DEL`), `resources.py`·`main.py`(`PING`)뿐. `EXPIRE NX`·Lua 없음 → 6.2(ADR-003).
  fakeredis 2.x 의 `INFO` 는 `unknown command 'info'` — 경고 경로.
- **결정:** ADR-001~004
- **신규 finding:** HIGH 1(F-001) · MED 1(F-002) · LOW 2(F-003·F-004) — 전부 Fixed
- **§5 조사:** 코드 변경 없음, 감독자 보고에 전량. 누락 방지 장치 부재는 R-004
- **수렴 판정:** `CONVERGED`

### Round 2 — 2026-10-13 · 추가 명세 §8 (커버리지 하한 0%)
- **트리거:** REQ-002
- **확인:** 하한은 `pyproject.toml` 의 주석(`# fail_under = 80`)뿐, CI·게이트에 `--cov` 없음, 85% 를 고정하는 테스트·ADR 없음.
- **실측:** CI 와 같은 명령을 `--cov=app --cov-report=term-missing` 로 돌리자 1043 passed 뒤 결합 단계에서
  `INTERNALERROR … Can't combine branch coverage data with statement data`(종료 코드 3 — CI 의 `pipefail` 이면 실패). subprocess
  테스트의 자식이 statement 데이터를 남긴 것이다. `--cov-branch` 를 더하자 통과(TOTAL 72%) → ADR-005 에 반영.
- **결정:** ADR-005
- **신규 finding:** LOW 1(F-005) — Fixed
- **수렴 판정:** `CONVERGED`

## 검사 (최종 트리)

- `uv run ruff check .` 통과 · `uv run ruff format --check .` 313 files already formatted
- mypy(규칙 파일 방법 — 순수 파이썬 빌드 1.20.2) `Success: no issues found in 200 source files`
- `pytest -m "not mysql" --cov=app --cov-branch --cov-report=term-missing`(작업 트리, Redis 는 저장소 밖 fakeredis TCP
  127.0.0.1:6391 — `REDIS_HOST`·`REDIS_PORT` 함께 지정): **1043 passed · 0 skipped · 18 deselected**, TOTAL 72%
- 같은 명령을 `.env` 없는 사본(추적·신규 파일만 복사, `uv sync --locked`)에서: **1043 passed · 0 skipped · 18 deselected**, TOTAL 72%
- `pytest -m mysql --collect-only`: 18 selected(로컬 미실행 — CI 의 mysql job)
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크가 열려 있어 돌았다)
- `migrations/` 변경 0

## fail-on-revert

대상 파일을 저장소 밖(`tmp/default/log-redaction/revert`)에 복사해 두고 수정 전 내용(`git show main:<file>`, CRLF 유지)을
넣어 테스트한 뒤 복사본으로 복원했다(복원 후 `cmp` 바이트 일치).

| 되돌린 것 | 실패한 테스트 |
|---|---|
| `app/utils/logs/config.py`(queue 필터 `redact` 없음) | `test_project_logging_pipeline_masks_stdout_and_stderr` |
| `app/utils/logs/setup.py`(uvicorn 로거 부착 없음) | `test_uvicorn_cli_loggers_are_masked` |
| `app/celery/lifecycle.py`(시그널 수신자 없음) | `test_celery_worker_handlers_are_masked` |
| `main.py`(DEBUG 500 `str(exc)`) | `test_debug_500_detail_is_masked` |
| `app/core/resources.py`(버전 확인 호출 없음) | `test_startup_refuses_redis_below_the_minimum` 3건 · `test_unverifiable_version_warns_and_continues` 3건 |
| 변이: `REDIS_MIN_VERSION=(6,0,0)` / `(7,0,0)` | `test_min_version_covers_every_command_the_code_sends`·`test_min_version_is_not_inflated` / `test_min_version_is_not_inflated` |
| 변이: 두 핸들러의 `headers=exc.headers` 제거 | `tests/test_exception_headers.py` 5건 전부 |
| `pyproject.toml`·`ci.yml` 수정 전 | `test_fail_under_is_declared_once_with_default_zero`·`test_ci_measures_and_prints_coverage` |
| 변이: CI 에 `--cov-fail-under=85` | `test_no_command_line_threshold_overrides_pyproject` |

`app/utils/logs/filters.py` 를 되돌리면 `RedactingFilter`·`redact` 가 없어 새 테스트 파일이 수집 단계부터 실패한다.

## 심각도 추세
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 1 | 0 | 1 | 1 | 2 | 4 (F-001~F-004) | CONVERGED |
| 2 | 0 | 0 | 0 | 1 | 1 (F-005) | CONVERGED — **그룹 종료** |
