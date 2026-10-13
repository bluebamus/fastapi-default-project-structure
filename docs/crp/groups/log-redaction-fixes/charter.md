# Charter — log-redaction-fixes  (Charter v0.2 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `app/utils/logs/filters.py` | 소스 | `redact()`·`_SECRET_PATTERNS`(정본)·`RedactingFilter`·`add_redacting_filter` |
| 1 | `app/utils/logs/config.py`, `app/utils/logs/setup.py` | 소스 | queue 핸들러 필터 `redact`, uvicorn CLI 로거 부착 |
| 1 | `app/celery/lifecycle.py` | 소스 | `after_setup_logger`·`after_setup_task_logger` 수신자 |
| 1 | `main.py` | 소스 | DEBUG 500 `detail` 마스킹 |
| 1 | `app/core/redis.py`, `app/core/resources.py` | 소스 | `REDIS_MIN_VERSION`·`ensure_redis_version`, lifespan 호출 |
| 1 | `app/core/security/rate_limit.py`·`refresh_store.py` | 소스(docstring) | 버전 서술 |
| 1 | `pyproject.toml`, `.github/workflows/ci.yml` | 설정 | `fail_under = 0`, CI 커버리지 측정, compose·CI Redis 주석 |
| 1 | `compose.test.yaml`, `.env.example`, `scripts/review_gate.py` | 설정·스크립트 | 주석, 요구 ID 출처에 이 그룹 추가 |
| 1 | `tests/utils/test_log_redaction.py`·`tests/core/test_redis_version.py`·`tests/test_exception_headers.py`·`tests/test_coverage_contract.py`(신규), `tests/utils/test_logs.py`·`tests/core/test_resources.py` | 테스트 | |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`server-lifecycle-guide.html` | 문서 | |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `service-hardening` charter §2-1 과 같다. Redis 는 필수이고 서버 **6.2 이상**이다(ADR-003).

### 2-2. 위협 모델

- 방어한다: traceback·체인 예외·`stack_info`·로그 메시지에 실린 DSN 비밀번호·`password=` 류·`Authorization` 값의 로그 출력
  (앱 queue 경로·stdout·stderr·큐 포화 fallback·`uvicorn main:app` CLI·Celery worker), DEBUG 500 응답 `detail` 의 같은 값,
  예외 헤더 유실(405 `Allow`·401 `WWW-Authenticate`·429 `Retry-After`), 쓰는 명령이 없는 Redis 로의 조용한 기동.
- 방어하지 않는다: 형태로 알아볼 수 없는 비밀값(R-003), 접속 로그 원문 저장(사용자 결정 — R-001), 같은 경로를 메서드별로 나눈
  라우트의 `Allow` 누락 메서드(R-002), 새 라우터의 인증 누락(R-004 — 조사만).

### 2-3. 불변식

- **INV-1**: 마스킹 규칙의 정본은 `app/utils/logs/filters.py` 의 `redact()` 하나다. 로그·DEBUG 500 응답이 모두 그것을 쓴다.
- **INV-2**: 로그 출력 경로마다 비밀값이 없고 마스킹 표식(`***`)이 있으며, 예외 타입·체인·파일·줄은 남는다.
- **INV-3**: 전역 예외 핸들러는 예외의 `headers` 를 응답에 싣고 본문 형식(`ErrorResponse`)은 그대로다.
- **INV-4**: `REDIS_MIN_VERSION` 은 코드가 보내는 명령의 요구 버전 중 최댓값과 같고, 미만 서버로는 기동하지 않는다.
- **INV-5**: 커버리지 하한은 `pyproject.toml` 의 `fail_under` 하나이고 기본값은 0 이다. 명령줄 `--cov-fail-under` 가 없다.
- **INV-6**: 접속 로그의 `session_id`·`referer`·`forwarded_for`·`real_ip` 원문 저장 코드·테스트는 바꾸지 않는다.

## 3. 인수 기준 — 전부 그린

- [x] **재현** — 실제 dictConfig(production: stdout + stderr)로 `logger.exception` 을 남겨 DSN·`password=`·Bearer 값이 두 출력에 모두 남는 것을 확인(run-log Round 1)
- [x] **마스킹** — 경로별 테스트(queue stdout·stderr, fallback, uvicorn CLI, Celery 2 시그널, DEBUG 500) + 체인·`stack_info` + 진단 정보 유지 — `tests/utils/test_log_redaction.py`
- [x] **헤더** — 405 `Allow` = 라우트 메서드, `HTTPException(headers=)`·`AppException(headers=)`·401 `WWW-Authenticate`, 본문 형식 — `tests/test_exception_headers.py`
- [x] **Redis 버전** — 미만 거부·이상 통과·INFO 실패/키 없음/해석 불가 경고 후 계속·fakeredis 통과·상수↔소스 계약(상·하 양방향) — `tests/core/test_redis_version.py`
- [x] **커버리지** — `fail_under = 0`, 명령줄 하한 없음, CI 측정 — `tests/test_coverage_contract.py`
- [x] **§5 조사** — 라우트 전량을 `app.routes`(`_IncludedRouter.effective_route_contexts`) 순회로 뽑아 보고(코드 변경 없음)
- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"`(작업 트리 + `.env` 없는 사본), `review_gate --fast`(pip-audit 제외), `-m mysql` 수집, alembic 변경 없음 — run-log
- [x] **fail-on-revert** — 변경 파일마다 수정 전 내용으로 되돌려 해당 테스트가 실패(run-log)

## 4. 변경 이력

- v0.1 (2026-10-13): 최초 작성(명세 §1~§7).
- v0.2 (2026-10-13): 추가 요청 §8(커버리지 하한 0%) — INV-5·인수 기준 추가.
