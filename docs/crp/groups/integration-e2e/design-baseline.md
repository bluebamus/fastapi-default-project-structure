# Design Baseline — integration-e2e (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `integration-e2e ADR-0xx` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 갈림길(산출물·복제·CI·장애 주입·포트·keepalive·Playwright)은 사용자가 계획서 §0·§5 로 확정했다(2026-10-19). 나머지는 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-20 · 변경 이력: (없음)

## 1. 목적 / 배경

사용자 지시 "통합 테스트 진행해줘"(2026-10-20). 계획서(작업 폴더 `integration-test-plan.md`, 사용자 확정)의 W1~W9·L1~L6 을
이 저장소에서 수행한다 — 실제 MySQL 복제·Redis·uvicorn·Celery·브라우저 위에서 API·관리 화면·백그라운드·장애·운영 도구를
전수로 돌리고, 실제 앱에서 뽑은 인벤토리의 모든 칸이 실행됐는지 대조한다. 그 전에 W0: 기존 통합 테스트가 접속 대상을
명시하지 않아 남의 로컬 Redis 에 붙은 사고의 구조를 없앤다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-20 | W0 "테스트가 남의 Redis 에 붙는 구조 제거" | Redis 가 필요한 fixture 는 `REDIS_HOST`·`REDIS_PORT` 가 명시되지 않으면 `pytest.fail`(이유·방법). 명시됐는데 닿지 않으면 기존 skip. 자식 서버 env 에 확인한 대상(+부모가 준 `REDIS_PASSWORD`, 없으면 빈 값)을 넘겨 `.env` 가 바꾸지 못하게. CI 에 변수 명시 | Active | ADR-005, F-001 |
| REQ-002 | 2026-10-19 | 계획서 §0 D1~D4·포트·keepalive·Playwright | 영구 스위트 `tests/e2e/`(마커 `e2e`), GTID replica 위 검증, 매 push CI job `e2e`(skip·xfail 금지), 장애 주입 포함. 포트 MySQL 13321·13322, Redis 16391, 앱 18091(127.0.0.1). 실행 직전 점유 검사, 접속 대상 검사 | Active | ADR-001~004 |
| REQ-003 | 2026-10-19 | 계획서 §3 공통 통과 기준 | 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 실행 로그 비밀값 grep 0 | Active | ADR-006, ADR-007 |
| REQ-004 | 2026-10-19 | 계획서 §3 L2~L6 | L2 operation × 7칸, L3 시나리오 8종, L4 관리 화면 6항목, L5 장애 5종, L6 운영 4항목 | Active | ADR-006 |
| REQ-005 | 2026-10-20 | 명세 "로깅 쪽 새 검사 대상" | 실행 경로별 같은 형식·헤더, 앱별 레벨, 프로세스별 파일·회전·보관, DSN·설정 비밀값 원문 0건 | Active | F-003 |
| REQ-006 | 2026-10-19 | 계획서 §5-1 | 통합 테스트가 찾은 결함은 테스트를 먼저 고정하고 별도 커밋으로 고친다. 정책을 바꾸는 수정은 멈추고 보고 | Active | F-001~F-005 |
| REQ-007 | 2026-10-20 | 사용자 결정 "e2e 정책 결정 반영"(F-004·R-004·F-003) | ① Redis 를 필수로 쓰는 API(아래 ADR-009 목록)의 Redis 연결 오류 → 503 `SERVICE_UNAVAILABLE`, 내부 정보 0, fail-closed, traceback 한 번, keep-alive 유지 ② 읽기 전용 세션의 replica 연결 오류 → primary 로 한 번 재시도 + WARNING(비밀값 없음), `/ready` 불변, 단일 DB 동작 변화 0 ③ 설정 로드 직후 프로세스 파일을 붙여 import 중 줄도 `app.log`·`celery.log` 에 남김(웹·`python main.py`·`uvicorn main:app`·Celery worker·beat), 중복 0 | Active | ADR-009~011, F-003, F-004, R-004 |
| REQ-008 | 2026-10-21 | 사용자 결정 "e2e 정책 결정 2차"(결정 1~7) | 결정마다 이 저장소 해당 여부를 먼저 확인 — 있으면 TDD·fail-on-revert 로 고치고, 이미 결정대로면 계약 테스트만. ① OpenAPI 422 = 실제 본문(`ErrorResponse`) ② 처리되지 않은 예외 500 의 traceback 한 번·keep-alive — 한때 보류(상세 설명 요청) 뒤 같은 날 ①안(미들웨어로 직접 받기)으로 확정 ③ 모든 401 에 `WWW-Authenticate: Bearer` ④ CLI 비밀번호 변경 시 세션 폐기 — 해당 없음(그런 명령 없음) ⑤ 인증 사용자 조회는 primary ⑥ 관리 화면 Redis 장애는 모두 503(쿠키 없는 첫 요청 포함) — 이미 충족 ⑦ CSRF 폼 버퍼링: 본문 10 MiB 초과 413(`Content-Length` 먼저, 없거나 거짓이면 누적), 필드 1 MiB 초과 400 | Active | ADR-012~017 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-20 | 스택은 **별도 파일** `compose.e2e.yaml`(프로젝트 `itest-default`)이다. `compose.test.yaml` 은 그대로 둔다 | 기존 파일은 고정 `container_name`·고정 계정·포트를 쓰고 `gate`·`mysql` job 이 그대로 의존한다. E2E 는 실행마다 무작위 비밀번호, 복제 2대, 컨테이너 정지·재기동을 하므로 섞으면 서로를 깨뜨린다 | Active | — |
| ADR-002 | 2026-10-20 | **하네스가 스택을 소유한다**(`tests/e2e/stack.py`): 점유 검사 → 비밀값 생성 → `up --wait` → 127.0.0.1 도달 확인 → GTID 복제 부착(`RESET BINARY LOGS AND GTIDS` 후 `SOURCE_AUTO_POSITION=1`) → Alembic → `create_superuser` → uvicorn·Celery worker → 끝나면 프로세스 정지 + `down`(tmpfs 라 `-v` 불필요). Docker 가 PATH 에 없고 Windows 면 `wsl -e` + 실행 중 keepalive | 장애 주입(L5)이 컨테이너를 멈췄다 켜야 하고, 실행마다 무작위 비밀값을 compose 와 앱이 함께 알아야 한다. CI 와 로컬이 같은 코드 경로를 쓴다. 데이터는 tmpfs — 명세 "down -v 금지" 와 정리 요구를 함께 만족 | Active | — |
| ADR-003 | 2026-10-20 | 자식 프로세스는 **빈 작업 디렉터리**에서 OS 필수 변수만 물려받아 띄우고, 설정은 전부 환경 변수로 준다(`ENV=development`, `DEBUG=false`). 시작 전에 모든 DSN·Redis 대상이 127.0.0.1 + 표의 포트인지 검사한다(`check_targets`) | `.env` 는 작업 디렉터리 기준으로 읽힌다 — 저장소에서 띄우면 개발자 `.env` 가 접속 대상을 바꾼다(W0 와 같은 사고). `ENV=development` 라 배포 설정 검사(예시 값·짧은 키)가 실제로 돈다. `TRUSTED_PROXY_HOPS=1` + 클라이언트마다 다른 `X-Forwarded-For` 로 레이트 리밋 카운터를 테스트끼리 나눈다 | Active | — |
| ADR-004 | 2026-10-20 | `tests/e2e/` 는 마커식에 `e2e` 가 없으면 **deselect**(skip 아님). 마커 `e2e` 등록, CI job `e2e` 만 `-m e2e` 로 돈다. Playwright(Chromium)를 dev 의존성으로 추가 | 기본 실행·`-m "not mysql"`·`review_gate` 는 Docker 없이 돌아야 한다. deselect 는 "안 돌았다" 가 요약에 드러나고 skip 판정과 섞이지 않는다. Playwright 는 계획서 §0 에서 허용(관리 화면의 JS CSRF 주입은 실제 브라우저로만 검증된다 — default R-005) | Active | — |
| ADR-005 | 2026-10-20 | W0: `require_redis` 가 `(host, port)` 를 돌려주고 `ServerProcess(argv, port, redis_target)` 가 그 값을 자식 env 로 넘긴다. 미지정이면 `pytest.fail` | fixture 가 확인한 대상과 자식이 붙는 대상이 같아야 한다. 기본값을 남기면 다시 남의 Redis 에 붙는다 | Active | — |
| ADR-006 | 2026-10-20 | **인벤토리 대조**: 테스트가 `cover(kind, item, cell, na=None)` 로 장부에 적고, 마지막 파일 `test_zz_inventory.py` 가 실제 앱에서 operation(`AccessPolicyGuard().routes`)·관리 뷰(`ADMIN_VIEWS`)·Celery 태스크·beat 일정·Redis 접두어(소스 스캔)를 뽑아 칸 목록을 만들고, 빈 칸·모르는 칸이 있으면 실패. 행위 목록(관리 화면 요청 종류·장애·운영·로깅)은 계획서에서 옮긴 고정 표. 결과는 `inventory.md` | 새 API·뷰·태스크·키가 생기면 테스트가 없어도 초록인 상태를 막는다. N/A 는 사유 문자열로 적어 "빈 칸 금지" 를 지킨다 | Active | — |
| ADR-007 | 2026-10-20 | **비밀값 grep** 은 마지막 테스트(`test_zz_secrets.py`)에서 앱·worker 를 멈춰 큐를 비운 뒤, 실행 디렉터리의 모든 `*.log*`(앱·worker·beat·도구 출력, 프로세스 파일·회전 파일)에서 실행마다 만든 비밀값과 발급 토큰 원문을 찾는다 | 정지 전에는 큐에 남은 줄을 못 본다. 값은 실패 메시지에도 싣지 않는다 | Active | — |
| ADR-008 | 2026-10-20 | 메서드 분할 경로의 405 `Allow` 는 **값만 기록**한다(`Allow` 가 있고 그 경로 메서드의 부분집합인지 판정, 실제 값은 `NOTES`) | 사용자 결정(계획서 §3 L2 "현행 유지 — 값만 기록") | Active | — |
| ADR-009 | 2026-10-20 | **Redis 연결 오류 → 503.** `main.py` 에 redis `ConnectionError`·`TimeoutError` 전용 예외 핸들러를 둔다 — ERROR `[RedisUnavailable]` + traceback 한 번, 응답은 `ServiceUnavailableException`(503 `SERVICE_UNAVAILABLE`, 기존 `ErrorResponse` 형식, 내부 정보 없음). 명령 오류(`ResponseError` 등)는 500 그대로. 대상 API(Redis 필수 경로, 코드에서 추출): `POST /api/v1/auth/register`(레이트 리밋)·`/login`(레이트 리밋·refresh 등록)·`/refresh`·`/logout`(refresh 회전·폐기), `PATCH`·`DELETE /api/v1/users/{user_id}`(refresh·관리 세션 폐기 — `get_user_service` 가 Redis 저장소를 조립). 관리 화면은 기존대로 `RedisSessionMiddleware` 가 503 | 중복 traceback·연결 종료의 원인: 처리되지 않은 예외는 `Exception` 핸들러로 가는데, Starlette 는 그 핸들러를 `ServerErrorMiddleware` 에 두고 응답을 보낸 **뒤 예외를 다시 던진다**(`starlette/middleware/errors.py` `raise exc`) — uvicorn 이 `Exception in ASGI application` traceback 을 한 번 더 남기고 연결을 닫는다. 예외 클래스별 핸들러는 `ExceptionMiddleware` 에 있어 다시 던지지 않는다. 한 곳(전역 핸들러)이라 라우트·의존성마다 감싸지 않는다. 관리 화면 503 과 같은 의미(일시 불가, fail-closed) | Active | — |
| ADR-010 | 2026-10-20 | **replica 연결 오류 → primary 로 한 번 재시도.** `make_routing_session_class()` 가 `RoutingSession` 에 `do_orm_execute` 리스너를 단다: `state.invoke_statement()` 가 `DBAPIError` 로 실패하고 ① 세션이 읽기 전용(`mark_read_only`) ② 이 세션이 고른 엔진이 replica(writer 아님) ③ 연결 계열(`connection_invalidated` 또는 MySQL 2002·2003·2006·2013)이면 WARNING `[database] replica 연결 실패(<타입>(code=…))` 를 남기고 세션을 primary 에 고정한 뒤 같은 구문을 한 번 다시 실행한다. **재시도 범위:** 읽기 전용 세션(`get_read_only_db_session`)의 ORM·Core·`text()` 읽기만. writer 세션·투명 라우팅 세션(`get_routed_db_session`)·background 세션은 재시도하지 않는다. 쿼리 문법·제약 오류(1xxx)·풀 대기 초과는 재시도하지 않는다. replica 가 없거나 라우터가 꺼지면(단일 DB) 리스너가 없거나 조건 ②가 거짓이라 동작 변화 0. `/ready` 는 바꾸지 않는다 | 읽기 전용 세션은 쓰기를 실행할 수 없으므로(`_block_read_only_*`) 재시도가 쓰기와 한 트랜잭션에 섞이지 않는다 — 다른 서버에서 다시 읽어도 결과의 의미가 같다(primary 가 더 최신일 뿐). 재시도 뒤 primary 고정은 같은 세션이 죽은 replica 로 매 구문 접속 시간(최대 `connect_timeout` 10초)을 다시 쓰지 않게 한다. 실행 지점이 `Session.execute` 하나라 repository 마다 감싸지 않는다. 로그에는 예외 타입·드라이버 코드만(DSN·호스트 없음) | Active | — |
| ADR-011 | 2026-10-20 | **프로세스 파일은 설정 로드 직후 붙인다.** `configure_logging()`(첫 `get_logger()`)이 `setup.entry_process(sys.argv[0])` 로 `python main.py`·`uvicorn`(`-m uvicorn` 포함) → `app`, `celery`(`-m celery`, worker·beat) → `celery` 를 정해 `attach_log_files()` 를 부른다. 그 밖의 프로그램(pytest·alembic·스크립트)은 파일을 열지 않는다. 진입점 호출(`main.py`·Celery `after_setup_logger`)은 멱등 대비로 남는다(`python -c`·테스트) | 파일 핸들러가 진입점에서 붙으면 그 전 import 중 줄(`[database] 라우팅 구성`)이 파일에 없다(F-003). 설정 로드 직후가 가장 이른 시점이고, 그때 프로세스 종류를 알 수 있는 것은 실행 프로그램뿐이다. `attach_log_files` 는 listener 에 `DailySizeRotatingFileHandler` 가 있으면 아무것도 하지 않아 두 번 불러도 한 번만 붙는다(줄 중복 0). logging-overhaul ADR-002 의 "진입점이 정한다"(판정 시점)를 대체한다 — 파일 구성·listener 부착은 그대로 | Active | logging-overhaul ADR-002(판정 시점 부분) |
| ADR-012 | 2026-10-21 | **422 문서는 앱 생성 시 OpenAPI 후처리 한 곳에서.** `main._openapi_with_actual_422` 가 `app.openapi` 를 대신해 모든 operation 의 422 응답을 `#/components/schemas/ErrorResponse` 로 바꾸고 `HTTPValidationError`·`ValidationError` 를 components 에서 뺀다. 실제 응답은 그대로 | 422 는 FastAPI 가 매개변수 있는 operation 마다 자동으로 붙여 라우터별 `responses=` 로는 빠짐없이 덮을 수 없다. 후처리 한 곳이면 새 라우터도 자동으로 맞는다. 계약 테스트는 실제 422 본문을 각 operation 의 422 스키마(필수·허용 키)에 대어 본다 | Active | — |
| ADR-013 | 2026-10-21 | **401 challenge 는 전역 핸들러에서.** `main._with_bearer_challenge` 를 `AppException`·`HTTPException` 두 핸들러가 함께 쓴다 — 상태가 401 이면 `WWW-Authenticate: Bearer` 를 보태고, 예외가 이미 실은 값은 그대로 둔다 | 401 의 출처가 `InvalidCredentialsException`(로그인)·`InvalidTokenException`(refresh·logout·틀린 토큰)·`OAuth2PasswordBearer`(토큰 없음)로 갈라져 있어 예외 클래스마다 헤더를 실으면 새 401 이 빠진다. RFC 9110 §15.5.2 | Active | — |
| ADR-014 | 2026-10-21 | **인증 사용자 조회는 primary.** `get_current_user` 는 읽기 전용 세션(쓰기 차단 유지)에 `using_writer()` 를 더해 primary 에서 읽는다. 다른 읽기 라우팅은 그대로 | 복제 지연 동안 막 가입한 사용자의 유효한 토큰이 401 이 되고 비활성화·삭제가 늦게 반영된다. 요청마다 1건이라 primary 부하는 작다. `get_current_principal`(DB 미조회)을 쓰는 라우트는 해당 없음 | Active | — |
| ADR-015 | 2026-10-21 | **CSRF 폼 버퍼링 상한.** `AdminCsrfMiddleware` 가 `Content-Length` 가 `MAX_FORM_BODY_BYTES`(10 MiB)를 넘으면 읽지 않고 413, 없거나 거짓이면 읽는 도중 누적으로 413. 폼 파서에 `max_part_size=MAX_FORM_FIELD_BYTES`(1 MiB, Starlette 기본값과 같지만 명시)를 넘겨 필드 하나가 넘으면(깨진 폼 포함) 400 — 전에는 CSRF 거부(403·로그인 화면)로 둔갑했다. 상한은 기존 관례대로 모듈 상수(설정 아님) | 413 판정을 헤더로 먼저 하면 정직한 큰 요청이 본문을 한 바이트도 버퍼링시키지 못한다. 400 은 본문을 다 읽은 뒤라 keep-alive 가 유지된다(e2e 확인) | Active | — |
| ADR-016 | 2026-10-21 | **처리기 없는 예외는 가장 바깥 사용자 미들웨어에서.** `_register_exception_handlers` 끝에서 `@app.middleware("http")` `unhandled_exception_middleware` 를 등록한다(미들웨어 등록의 마지막 → `user_middleware[0]`, 테스트로 고정): `call_next` 의 예외를 기존 `Exception` 처리기(`general_exception_handler` — 로그 형식·마스킹·본문 그대로)로 응답한다. `DEBUG=true` 는 다시 던진다(기존 동작). 응답 본문 전송 중의 예외는 `call_next` 가 돌아온 뒤라 오지 않는다(기존대로) | Starlette 는 `Exception` 처리기를 `ServerErrorMiddleware`(가장 바깥, `starlette/applications.py` `build_middleware_stack`)에 두고 응답 뒤 `raise exc`(`starlette/middleware/errors.py`) — uvicorn 이 `Exception in ASGI application` 을 남기고 응답이 시작된 연결을 닫는다(`uvicorn/protocols/http/httptools_impl.py` `run_asgi`). 그 바로 안쪽에서 끝내면 로그 1번·연결 유지·응답 불변. 가장 바깥이어야 CORS·UserInfo 안의 예외도 받는다. 처음엔 보류(사용자 상세 설명 요청)였다가 같은 날 사용자가 ①안으로 확정 | Active | — |
| ADR-017 | 2026-10-21 | **MySQL RSA 는 `aiomysql[rsa]` 로 선언.** `cryptography>=…` 직접 선언을 지우고 `aiomysql[rsa] (>=0.3.2,<0.4.0)` 로 바꾼다. `pymysql` 은 Alembic 이 직접 써서 옵션 없이 유지. lock 은 표기만 바뀌고 `cryptography` 는 그대로 남는다 | `cryptography` 의 유일한 사용처가 MySQL 8.4 `caching_sha2_password` 전체 인증(TLS 아닌 연결)의 RSA 암호화다(`aiomysql[rsa]` = `PyMySQL[rsa]` = `cryptography`). 드라이버의 공식 추가 옵션이면 버전 하한도 드라이버가 정한다. 계약 테스트 `tests/test_mysql_rsa_dependency.py` | Active | — |

## 4. 불가침 제약

- C-1: 접속은 127.0.0.1 의 이 스택(13321·13322·16391·18091)뿐. 외부 DB(115.68.199.140)·`*-testdb`·남의 컨테이너(6379 등)에 붙지 않는다.
- C-2: 이 작업이 만든 compose 프로젝트(`itest-default`)에만 up·stop·start·down·logs·exec. `down -v` 금지.
- C-3: `.env` 를 읽지 않는다(하네스는 빈 작업 디렉터리에서 자식을 띄운다).
- C-4: 정책을 바꾸는 수정(권한·폐기 규칙·응답 형식·설정 의미)은 하지 않고 보고한다.

## 5. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-10-20 | 그룹 개설(REQ-001~006, ADR-001~008) |
| 2026-10-21 | e2e 정책 결정 2차(REQ-008, ADR-012~017). 결정 2 는 보류됐다가 같은 날 ①안으로 확정(ADR-016), 의존성 `aiomysql[rsa]` 통일(ADR-017) |
| 2026-10-20 | 사용자 결정 반영(REQ-007, ADR-009~011). C-4 의 "보고만" 대상이던 F-003·F-004·R-004 를 사용자가 결정해 고쳤다. logging-overhaul ADR-002 의 판정 시점 부분을 Superseded 로 표시 |
