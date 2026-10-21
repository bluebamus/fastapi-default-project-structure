# Run Log — integration-e2e (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `292ba5b` (main, logging-overhaul 병합). 브랜치 `feat/integration-e2e`.
커밋 `0c7b3e1`(W0) · `7ab06a8`(L1 결함) · `4c2665f`(W1·W2·W5) · `ff88183`(W3·W4) · `abe5d55`(W6) · `9513a83`(F-006·README) · `d1bcaa8`(F-007), 문서는 그룹 개설 커밋.

## 계획 (writing-plans 요약)

계획서(작업 폴더 `integration-test-plan.md`)가 이미 작업·테스트 계획이라 별도 계획 문서는 만들지 않고 실행 순서만 정했다.

1. W0 — Redis 대상 명시(TDD: 실패 확인 → 구현 → fail-on-revert) → 별도 커밋.
2. 병합된 main 에서 인벤토리 재추출(아래), 계획서 §1 과 차이 기록.
3. W1·W2 — `compose.e2e.yaml` + 하네스(안전 검사 먼저: `check_targets` 테스트 → 스택 상태 테스트).
4. W4 — L2 → L3 → L4 → L5 → L6 순서로 층마다 작성·실행·결함 처리. W3 대조기·비밀값 grep 은 마지막.
5. W6 CI, W7 문서, W9 review 문서. 전체를 Windows(로컬)·Linux(WSL 네이티브 — CI 와 같은 prefork·SIGTERM)에서 실행.

## 인벤토리 재추출 (main `292ba5b`, 실제 앱 import)

| 대상 | 결과 | 계획서 §1 대비 |
|---|---|---|
| API operation | 39 (+ `GET /docs` — `DEBUG=true` 에서만) | 같음. `/docs` 는 E2E(배포 구성 `DEBUG=false`)에서 404 로 확인 |
| 접근 수준 | Public 10 · PublicWrite 4 · LoginRequired 12 · SuperuserRequired 13 (`/docs` 제외) | — |
| 관리 뷰 | 7: `post`·`product`·`user-access-log`(생성·수정 불가)·`reply`·`sales-order`(생성·수정·삭제 불가)·`sns-post`·`user`(생성 불가) | 같음. 뷰별 가능 동작을 인벤토리 칸에 반영(불가 칸은 403 확인 후 N/A) |
| Celery | 태스크 2(`home.aggregate_access_stats`·`home.purge_expired_access_logs`), beat 1(`<crontab: 30 3 * * *>`) | 같음 |
| Redis 접두어 | `admin:sess:`·`admin:user_sessions:`·`admin:rl:login:`·`auth:rt:`·`auth:fam:`·`auth:user:`·`auth:rl:login:`·`auth:rl:register:` + Celery broker·backend | **정정:** 계획서의 `admin:login` 은 Redis 키가 아니라 sqladmin 라우트 이름(`url_for("admin:login")`). 관리 로그인 제한 키는 `admin:rl:login:{ip}:{user}`·`admin:rl:login:{ip}` |
| 설정 | 9 클래스 · 69 필드 | **변경:** config-cleanup 1·2차로 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS`·`API_VERSION` 삭제. logging-overhaul 로 `LogSettings` 13 필드(`LOG_APP_LEVELS`·`LOG_FILE_*`·`LOG_DIR`·`LOG_MAX_SIZE_MB`·`LOG_RETENTION_DAYS`·`LOG_*_FORMAT` 등) |
| 로깅(새 검사 대상) | 모든 실행 경로 같은 형식·헤더(`[app=…]`), `LOG_APP_LEVELS`, 프로세스별 파일(`app.log`·`error.log`·`celery.log`·`celery-error.log`), 자정+크기 회전·`LOG_RETENTION_DAYS`, DSN 계정·설정 비밀값 원문 마스킹, uvicorn CLI 접속 줄 마스킹(config-cleanup F-008) | 계획서 작성 뒤 병합 — L6 에 로깅 항목 추가 |

## 라운드 기록

### Round 1 — 2026-10-20 · W0~W9 · L1~L6
- **트리거:** REQ-001~006(사용자 지시·확정 계획서)
- **결정:** ADR-001~008
- **신규 finding:** MED 1(F-001, Fixed) · LOW 6(F-002·F-006·F-007 Fixed, F-003·F-004 Report, F-005 Accepted)

#### W0 — TDD·fail-on-revert

| 테스트 | 수정 전 코드 |
|---|---|
| `test_missing_redis_port_fails_instead_of_defaulting_to_6379` | 실패(3 skipped — 그리고 **6379 에 실제로 접속했다**: 로컬 6379 는 다른 프로젝트 Redis 라 RED 확인 1회가 그 Redis 에 ping·INFO 를 보냈다. 이후 fail-on-revert 에서는 이 테스트를 빼고 돌렸다) |
| `test_missing_redis_host_fails_too` | 실패(skip 으로 끝남) |
| `test_explicit_but_unreachable_target_keeps_the_skip_policy` | 통과(유지해야 할 정책 — 의도) |
| `test_child_server_gets_the_checked_target_not_the_inherited_one` | 실패(`ServerProcess` 가 대상을 받지 않음) |

복원 방법: 대상 파일을 작업 폴더 밖 tmp 에 복사 → `git show HEAD:…` 로 수정 전 내용 → 테스트 → 복사본으로 복원(diff 동일 확인).

#### 층별 결과 (Windows 로컬 · Linux WSL 네이티브)

| 층 | 테스트 | Windows | Linux |
|---|---|---|---|
| 하네스 | `test_a_stack.py` 8 | 통과 | 통과 |
| L1 회귀 | `test_a_regression.py` 2 — 스택 위 `-m "not mysql"` 1322 passed · `-m mysql --mysql-required` 19 passed | 통과(F-002 수정 뒤) | 통과 |
| L2 | `test_b_api_matrix.py` 275 | 통과 | 통과 |
| L3 | `test_c_flows.py` 13 | 통과 | 통과 |
| L4 | `test_d_admin.py` 57 | 통과 | 통과 |
| L5 | `test_e_faults.py` 4 | 통과 | 통과 |
| L6 | `test_f_ops.py` 12 + `test_zz_secrets.py` 1 | 통과 | 통과 |
| W3 | `test_zz_inventory.py` 2 — 400칸(API 280 · 관리 77 · 관리 요청 17 · Celery 3 · Redis 9 · 장애·운영·로깅 14), 빈 칸 0, N/A 84 | 통과 | 통과 |

전체: Windows **374 passed, 0 skipped** · Linux(WSL 네이티브 클론, `.env` 없음) **374 passed, 0 skipped, 9분 19초**.
`/mnt/c` 위의 Linux 실행은 파일시스템이 느려 import 만 수십 초~수 분 걸려 하네스 시간 제한(90초·300초)에 걸렸다 — 결함이 아니라
환경 문제로 판정하고 WSL 네이티브 경로(`/tmp`, 끝나고 삭제)에서 다시 돌렸다.

#### 측정·관측

- **CSRF 본문 버퍼링 상한(passive R-004 대응 항목의 default 측):** 10 MiB + 1 바이트 폼 본문 → 413(`test_admin_csrf_form_body_over_10_mib_is_413`).
- **Redis 정지:** 관리 화면 503 · 변경 미저장, API 로그인·refresh 500 `INTERNAL_SERVER_ERROR`(내부 정보 없음) + 응답 뒤 연결 종료(F-004), Redis 를 안 쓰는 조회 200, `/ready` 503, 재기동 후 자동 회복.
- **replica 정지:** replica 경로 조회 500 `DATABASE_ERROR`, 쓰기·수정 200, `/ready` 200(R-004). 재기동 후 primary binlog 로 처음부터 따라옴.
- **primary 정지:** `/ready` 503 · `/health` 200 · 쓰기 500(내부 정보 없음). tmpfs 라 스택 재구성.
- **worker 정지:** API 영향 없음, 태스크는 PENDING → 재기동 후 처리.
- **405 `Allow`:** 메서드 분할 경로는 마지막 라우트 메서드만(R-001, 값은 `inventory.md`).
- **Celery 종료:** Linux(prefork·SIGTERM)는 `Warm shutdown` → `worker 자원 해제 완료` → `stop 완료`. Windows(solo·CTRL_BREAK)는 listener 정지 시간 초과(F-005).

#### 검사

최종 코드(`d1bcaa8`) 기준:

| 검사 | 결과 |
|---|---|
| `pytest -m e2e -rsxX` (Windows) | **374 passed**, 1341 deselected, skipped·xfailed 0 — 18분 23초. 인벤토리 빈 칸 0(`inventory.md`), 비밀값 grep 0 |
| `pytest -m e2e -rsxX` (Linux, WSL 네이티브 클론 `9513a83` + 회귀 수정) | **374 passed**, skipped 0 — 9분 19초. Celery prefork warm shutdown·`worker 자원 해제 완료` 확인 |
| L1 `-m "not mysql"`(스택 Redis) | 1322 passed, 393 deselected, skipped 0 |
| L1 `-m mysql --mysql-required`(스택 primary) | 19 passed, skipped 0 |
| `ruff check` · `ruff format --check` | 통과 |
| mypy(격리 실행, 1.20.2) | 205 파일 이상 없음 |
| `review_gate --fast` | 전건 통과(pip-audit 포함) |

관리 화면 모듈은 F-007 수정 뒤 따로 2회(56 passed ×2) 더 돌렸다.

### Round 2 — 2026-10-20 · 사용자 결정 반영(F-004·R-004·F-003) · 브랜치 `fix/e2e-policy`(main `a803b55` 에서)

명세가 곧 계획이라 writing-plans 는 생략했다. 결정마다 TDD(실패 확인 → 구현) · fail-on-revert(수정 전 파일을 넣고 실패 확인 → 복원) · 별도 커밋.

| 결정 | 커밋 | 단위 테스트(수정 전 → 후) | e2e(수정 전 → 후) |
|---|---|---|---|
| F-004 Redis 연결 오류 → 503 (ADR-009) | `9cff14c` | `test_redis_connection_error_is_503_logged_once` — 수정 전 TestClient 가 `redis.ConnectionError` 를 올린다(`ServerErrorMiddleware` 재전파) → 503·traceback 1건 | `test_redis_down_admin_fails_closed_and_api_follows_policy` — 수정 전 같은 연결로 보낸 refresh 가 연결 종료로 실패 → 503·503, keep-alive 유지, `Exception in ASGI application` 0 |
| R-004 replica 연결 오류 → primary 재시도 (ADR-010) | `a8be33a` | `test_read_only_session_retries_on_writer_when_replica_is_unreachable` — 수정 전 `OperationalError(2003)` → `["writer"]`·WARNING 1건. 가드: `test_routed_session_does_not_retry_replica_failure`·`test_read_only_session_does_not_retry_query_errors`(전후 모두 통과 — 재시도 범위 고정) | `test_replica_down_and_back` — 수정 전 500 `DATABASE_ERROR` → 200 + WARNING `replica 연결 실패(OperationalError(code=2003))` |
| F-003 import 중 줄 → 프로세스 파일 (ADR-011) | `3d30859` | `test_import_time_lines_reach_the_process_file`(`main.py`·`uvicorn/__main__.py`·`uvicorn.exe`·`celery/__main__.py`·`bin/celery` 5종) — 수정 전 `app.log` 에 라우팅 줄 0 → 각 1줄(중복 0), 다른 프로세스 파일 없음. `test_other_programs_get_no_early_files` | `test_process_files_are_separate`·`test_no_secret_appears_in_any_run_log` — `app.log` 14줄·`celery.log` 5줄(재기동 횟수만큼, 연속 중복 0), 가려진 DSN 이 `app.log` 에 있음 |

e2e 의 "수정 전" 은 `main.py`·`router.py` 를 `a803b55` 판으로 바꿔 `-k "redis_down or replica_down"` 로 돌렸다(2 failed) — 끝나고 복원했다.
Redis 대상은 `REDIS_HOST=127.0.0.1 REDIS_PORT=16391` 로 명시했다. RED 실행 동안 1초 간격 `netstat` 표본에서 6379 ESTABLISHED 0건.
(전체 실행 중 표본에 `[::1]:6379` TIME_WAIT 가 보였으나 실행이 끝난 뒤에도 새로 생겼다 — 이 저장소의 프로세스가 남아 있지 않은 상태에서다. 같은 머신의 다른 작업이 남의 로컬 Redis(`wslrelay`)에 붙은 것이다.)

| 검사 | 결과 |
|---|---|
| `pytest -m e2e -rsxX` (Windows) | **374 passed**, 1347 deselected, skipped·xfailed 0 — 16분 56초. 인벤토리 빈 칸 0, 비밀값 grep 0 |
| L1 `-m "not mysql"`(스택 Redis 16391, e2e 안의 회귀) | 1328 passed, 393 deselected, skipped 0 |
| L1 `-m mysql --mysql-required`(스택 primary) | 19 passed, skipped 0 |
| `ruff check` · `ruff format --check` | 통과 |
| mypy(격리 실행, 1.20.2) | 205 파일 이상 없음 |
| `review_gate --fast` | 전건 통과(pip-audit 포함) |

### Round 3 — 2026-10-21 · e2e 정책 결정 2차(결정 1~7 + 의존성) · 브랜치 `fix/e2e-policy-2`(main `d5a51f1` 에서)

명세가 곧 계획이라 writing-plans 는 생략했다. 결정마다 해당 여부를 먼저 확인하고, 있으면 TDD(실패 확인 → 구현) ·
fail-on-revert(수정 전 파일을 넣고 실패 확인 → 복원) · 별도 커밋. 결정 2 는 한때 보류(사용자가 상세 설명 요청)였다가 같은 날
①안(미들웨어로 직접 받기)으로 확정됐다. 그 사이 감독자가 `docs/guides` 구조 개편 커밋 2개(`8e40676`·`a874a1a`)를 이 브랜치에 더했다.

| 결정 | 판정 | 커밋 | 테스트(수정 전 → 후) |
|---|---|---|---|
| 1 OpenAPI 422 = 실제 본문 | 고침(35 operation 이 `HTTPValidationError`) | `01f1d6a`·`6f479c4`(mypy) | `test_422_documents_the_body_the_app_actually_sends` — 수정 전 35건 불일치 → 통과 |
| 2 처리기 없는 예외 | 고침 | `0fef02e`·`9f41f4b`(W0 가드 수 3→4) | 단위 `test_unhandled_exception_is_answered_once_without_reraising`(엔드포인트·다른 미들웨어 안) — 수정 전 `RuntimeError` 가 TestClient 로 올라옴, `test_catcher_is_the_outermost_user_middleware` — 수정 전 바깥이 `UserInfoMiddleware`, `test_debug_keeps_reraising`(전후 통과 — 유지할 동작). 실제 uvicorn `test_unhandled_exception_keeps_the_connection_and_logs_once` — 수정 전 같은 연결의 두 번째 요청이 `ConnectionAbortedError` |
| 3 모든 401 Bearer | 고침(로그인 실패·refresh·logout·틀린 토큰에 헤더 없음) | `98c390d` | `test_every_401_carries_www_authenticate_bearer`(5종)·`test_rejected_bearer_token_carries_the_challenge` — 수정 전 6 failed. e2e `test_token_lifecycle_rotation_reuse_and_logout`·`test_login_and_register_rate_limits_recover_after_the_window` — 수정 전 `KeyError: 'www-authenticate'` |
| 4 CLI 비밀번호 변경 세션 폐기 | 해당 없음 — `create_superuser` 는 기존 사용자를 승격만 하고 비밀번호를 바꾸지 않는다(`test_promotes_existing_user_without_touching_password`) | — | — |
| 5 인증 사용자 조회 primary | 고침(`get_current_user` 가 replica) | `db1d3fe` | `test_current_user_is_read_from_primary_not_a_lagging_replica` — 수정 전 `InvalidTokenException`. e2e `test_replication_lag_does_not_401_a_valid_token`(replica SQL 스레드 정지) — 수정 전 `/me` 401 |
| 6 관리 화면 Redis 장애 모두 503 | 이미 충족 — 계약 고정 | `cce4fdd` | `test_first_request_without_cookie_is_503_when_the_session_cannot_be_saved`(2종) — 변이(`started=True` 를 저장 전에) 시 2 failed. e2e `test_redis_down_…` 에 쿠키 없는 첫 요청 503 추가(수정 전 코드에서도 통과 — 이미 충족). 문서에 500 으로 적힌 곳 없음 |
| 7 CSRF 상한 | 고침(`Content-Length` 미판정, 1 MiB 초과 필드가 CSRF 거부로 둔갑) | `8f3d269` | `test_declared_body_over_10_mib_is_413_before_reading`·`test_single_field_over_1_mib_is_400_not_a_csrf_rejection`(2종) — 수정 전 3 failed(200·403). e2e `test_admin_csrf_body_and_field_caps` — 수정 전 `Content-Length` 413 대기 중 시간 초과 |
| 의존성 `aiomysql[rsa]` | 고침 | `9774d68` | `test_rsa_comes_from_the_driver_extra_not_a_direct_dependency` — 수정 전 실패, `test_pymysql_can_do_the_rsa_exchange`(전후 통과). lock 은 표기만(`aiomysql[rsa]`·`pymysql[rsa]` optional), `cryptography` 그대로 |

e2e 의 "수정 전" 은 `main.py`·`auth_dependencies.py`·`admin_session.py` 를 main 판으로 바꿔
`-k "token_lifecycle or rate_limits_recover or replication_lag or body_and_field_caps or redis_down"` 로 돌렸다 — 4 failed, 1 passed(`redis_down` — 결정 6 이미 충족), 끝나고 복원했다.

**결정 2 재현(수정 전, 실제 uvicorn 0.54):** `main._register_exception_handlers` 를 단 앱의 `RuntimeError` 엔드포인트 → 500 본문은 정상,
그 뒤 `Exception in ASGI application` 1건(traceback 합계 2), 같은 연결의 다음 요청 `ConnectionAbortedError`. 경로: `Exception` 처리기는
`starlette/applications.py` `build_middleware_stack`(키 `500`·`Exception` → `ServerErrorMiddleware` 의 handler)로 가장 바깥에 놓이고,
`starlette/middleware/errors.py` 가 응답 뒤 `raise exc` → `uvicorn/protocols/http/httptools_impl.py` `run_asgi` 가 로그를 남기고
응답이 시작됐으므로 `transport.close()`. 미들웨어 순서(바깥 → 안): `ServerErrorMiddleware` → (이번 수정) `unhandled_exception_middleware` →
`UserInfoMiddleware` → CORS → `ExceptionMiddleware`(클래스별 처리기 — 다시 던지지 않음) → 라우터.

**측정(L5, 결정 7):** 앱 RSS(기준 대비 현재/최대) — `Content-Length` 10 MiB+1 → 413 +0.1/+0.1 MiB(본문을 읽지 않음),
chunked 10 MiB+1 KiB → 413 +0.6/+10.9 MiB(누적 판정까지 버퍼링), 필드 1 MiB+1 → 400 +2.0/+10.9 MiB(최대는 앞 단계 값), 400 뒤 같은 연결 200.

Redis 대상은 `REDIS_HOST=127.0.0.1 REDIS_PORT=16391` 로 명시했다. 전체 실행 동안 1초 간격 `netstat` 표본에서 6379 연결 0건.

| 검사 | 결과 |
|---|---|
| `pytest -m e2e -rsxX` (Windows, 최종 `9f41f4b`) | **375 passed**, 1369 deselected, skipped·xfailed 0 — 14분 39초. 인벤토리 빈 칸 0, 비밀값 grep 0 |
| L1 `-m "not mysql"`(스택 Redis 16391, e2e 안의 회귀) | 1350 passed, 394 deselected, skipped 0 |
| L1 `-m mysql --mysql-required`(스택 primary) | 19 passed, skipped 0 |
| `ruff check` · `ruff format --check` | 통과 |
| mypy(격리 실행, 1.20.2) | 205 파일 이상 없음 |
| `review_gate --fast` | 전건 통과(pip-audit 포함) |

## 수렴 판정

- Round 1: 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 비밀값 grep 0. 열린 항목은 결정 필요 3건(F-003·F-004·R-004) — 정책·설계 변경이라 보고만 했다.
  **CONVERGED (결정 대기 3건 제외)**
- Round 2: 사용자 결정으로 3건 해결(F-003·F-004 Fixed, R-004 해소). 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 비밀값 grep 0. 열린 항목 0.
  **CONVERGED**
- Round 3: 결정 1~7 + 의존성 — 고침 1·2·3·5·7·의존성, 이미 충족 6, 해당 없음 4. 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 비밀값 grep 0. 열린 항목 0.
  **CONVERGED**
