# Design Baseline — log-redaction-fixes (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `log-redaction ADR-0xx` 처럼 그룹 이름을 붙인다(코드 주석의 `log-redaction ADR-0xx` 는 이 그룹이다).

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-13 · 변경 이력: (없음)

## 1. 목적 / 배경

외부 검수 문서가 권장한 항목 중 로그·오류 응답의 비밀값, 예외 헤더, Redis 요구 버전 서술을 고친다. `logger.exception(...)` 이
남기는 traceback 본문에는 기존 마스킹 장치(쿼리스트링 키 마스킹·DSN `render_as_string(hide_password=True)`·`hide_parameters`)가
닿지 않았다. 접속 로그의 원문 저장은 사용자가 유지하기로 했다. 엔드포인트 보호 현황은 조사만 해 판단 자료로 낸다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "권장 하는 항목에 대해 수정해줘. 다른 두 저장소도 적용해줘. 접속 로그가 session_id 쿠키, Referer, XFF 헤더를 원문 그대로 저장하는 로그는 그대로 유지해줘. ... 405 응답에 allow 헤더를 넘겨주는 것으로 수정해줘. ... redis도 적절하게 다시 정의해줘." 원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합은 주입, 모든 단계 단위 테스트(fail-on-revert) | 아래 REQ-001-A~E | Active | ADR-001~004, C-1~C-4 |
| REQ-001-A | 2026-10-13 | (traceback 비밀값) | 재현 후 traceback·`stack_info`·메시지를 기존 규칙 하나로 가린다. 모든 핸들러 경로(uvicorn·Celery 포함), DEBUG 500 `detail` 도 | Active | ADR-001, ledger F-001~F-003 |
| REQ-001-B | 2026-10-13 | (접속 로그 원문 유지) | `session_id`·Referer·XFF 원문 저장 코드·테스트를 바꾸지 않고 결정으로 기록 | Active | ADR-004, residual R-001 |
| REQ-001-C | 2026-10-13 | (405 `Allow`) | 모든 전역 핸들러가 `exc.headers` 를 싣는지 확인, 회귀 테스트 | Active | ADR-002, residual R-002 |
| REQ-001-D | 2026-10-13 | (Redis 재정의) | 코드가 쓰는 명령으로 최소 버전을 정해 상수 하나로, 기동 시 확인, 문서 전부 같은 값 | Active | ADR-003, ledger F-004 |
| REQ-001-E | 2026-10-13 | (엔드포인트 보호 조사) | 읽기 전용 — 인증 방식·라우트 목록·누락 방지 장치·무인증 쓰기 라우트를 보고 | Active | residual R-004 |
| REQ-002 | 2026-10-13 | "0%로 정의해줘. 기본 설정은 0%이며 차후 사용자가 필요한 수준만큼 설정하는 것으로 정의하고 싶다. 최초는 다른 기능들이 제대로 동작하는지 여부 확인이 중요하다." | `fail_under = 0` 명시(정본 하나), 명령줄 하한 없음, CI 는 측정·출력, 계약 테스트, 하한 올리는 법 문서화 | Active | ADR-005, ledger F-005 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-13 | 마스킹 규칙의 정본을 `app/utils/logs/filters.py` 의 `_SECRET_PATTERNS`·`redact()` 하나로 두고, **필터 단계**의 `RedactingFilter` 가 적용한다 — 메시지는 가릴 것이 있을 때만 합친 문자열로 바꾸고, `exc_info` 는 미리 `exc_text` 로 포맷해 가린 뒤 남겨 두며, `stack_info` 도 가린다. 붙는 곳: ① root queue 핸들러의 필터 `redact`(`sql_noise` 다음, `context` 앞) ② `configure_logging()` 이 `uvicorn`·`uvicorn.error` **로거**에 ③ Celery `after_setup_logger`·`after_setup_task_logger` 수신자가 Celery 핸들러에. DEBUG 500 `detail` 은 `redact(str(exc))`. | 저장소에 로그 메시지용 마스킹 클래스가 없었다(쿼리스트링 키 마스킹은 파싱된 키 집합 기반이라 문자열 규칙과 목적이 다르다 — 그대로 둔다). **포매터가 아닌 필터를 고른 이유**: 출력 핸들러가 셋으로 갈린다 — 우리 queue(포매터 `TzFormatter`), `uvicorn main:app` CLI 의 uvicorn 자기 핸들러(`DefaultFormatter`), Celery worker 가 root 를 갈아끼운 핸들러(`ColorFormatter`). 포매터를 오버라이드하면 남의 포매터를 바꿔 끼워야 하지만 필터는 어느 핸들러·로거에나 덧붙일 수 있다. 또 queue 핸들러의 필터는 **적재 전**에 돌아 큐 포화 시 ERROR 의 stderr fallback(포매터를 거치지 않음)도 가려진 값을 쓴다. `QueueHandler.prepare()` 는 `format()` 이 `exc_text` 를 재사용하므로 가린 traceback 이 그대로 합쳐진다. 로거 필터는 dictConfig 가 지우지 않아(`common_logger_config` 는 더하기만 한다) uvicorn·우리 설정의 적용 순서와 무관하다 — ADR-020(orm-raw-repository)의 "순서 결합" 우려가 없다. `uvicorn.access` 는 traceback 을 내지 않고 포매터가 `args` 를 직접 읽어 제외했다. | Accepted | — |
| ADR-002 | 2026-10-13 | 405 `Allow`·예외 헤더는 **이미 정상**이다 — `StarletteHTTPException`·`AppException` 핸들러가 `headers=exc.headers` 를 싣고(`main.py`), `RequestValidationError`·일반 `Exception` 은 헤더가 없다. 코드는 바꾸지 않고 회귀 테스트만 더한다. | `DELETE /health` → 405 `allow: GET`, 401 `www-authenticate: Bearer` 를 실측했다. 헤더 전달을 지우는 변이에서 새 테스트 5건이 실패한다. `Allow` 값은 Starlette 가 처음 부분 일치한 라우트의 메서드로 채운다 — 같은 경로를 메서드별 함수로 나눈 곳(`GET`·`POST /api/v1/blog/posts`)은 `PUT` 에 `allow: POST` 만 실린다(실측). 고치려면 405 핸들러가 FastAPI 0.141 의 `_IncludedRouter` 내부까지 순회해 메서드를 합쳐야 해 범위 밖으로 둔다(R-002). | Accepted | — |
| ADR-003 | 2026-10-13 | Redis 서버 최소 버전은 **6.2.0** — `app/core/redis.py` 의 `REDIS_MIN_VERSION`. 근거(명령 → 버전)를 그 상수 주석에 적는다: `GETDEL` 6.2.0(`RefreshTokenStore.consume`), `SET … EX … NX` 2.6.12(`RateLimiter.hit`), 나머지(`MULTI`·`INCR`·`TTL`·`EXPIRE`(옵션 없음)·`SADD`·`SMEMBERS`·`EXISTS`·`DEL`·`PING`·`INFO`) 2.6 이하. lifespan `_redis` 가 `PING` 직후 `ensure_redis_version(client)` 를 부른다 — `INFO server` 의 `redis_version` 이 낮으면 `RedisVersionError` 로 기동을 멈추고, `RedisError`·키 없음·해석 불가면 WARNING 후 계속. | 코드에서 다시 확인했다(감독자 정리와 같다): `EXPIRE … NX`(7.0)·Lua 는 쓰지 않는다(service-hardening ADR-025 ④ 가 그것을 피했다). 문서의 "Redis 7"(compose 이미지·README)은 테스트 이미지일 뿐 요구 근거가 없었다. 확인 로직은 기존 Redis provider 모듈(주입 지점)에 두고 lifespan 이 호출한다 — 새 클래스를 만들지 않는다. fakeredis 는 `INFO` 를 모르므로(`unknown command 'info'`, 실측) 경고 경로를 탄다 — 테스트가 깨지지 않고 이 경로가 곧 관리형 Redis 경로의 시험이다. 계약 테스트는 `app/` 소스를 AST 로 훑어 `expire(..., nx/xx/gt/lt=)`→7.0, `getdel`·`getex`→6.2, `set(..., nx=, ex/px=)`→2.6.12 를 찾고 상수가 그 최댓값과 **같은지**(부풀림도 막는다) 본다. | Accepted | — |
| ADR-004 | 2026-10-13 | 접속 로그(`user_access_logs`)의 `session_id` 쿠키 값·`referer`·`forwarded_for`(X-Forwarded-For)·`real_ip` **원문 저장은 사용자 결정으로 유지**한다. 코드·테스트는 바꾸지 않는다. | 사용자 결정(REQ-001 원문). 조회 API 는 슈퍼유저 전용이다(service-hardening F-023). 남는 위험은 residual R-001 로 "결정으로 수용". | Accepted | — |
| ADR-005 | 2026-10-13 | 커버리지 하한은 `pyproject.toml` `[tool.coverage.report] fail_under = 0` **한 곳**(명시, 주석 아님)이다. CI 의 `pytest -m "not mysql"` 단계는 `--cov=app --cov-branch --cov-report=term-missing` 으로 측정·출력만 한다. CI·`review_gate` 명령줄에 `--cov-fail-under` 를 두지 않는다. `term-missing:skip-covered` 는 쓰지 않는다. `--cov-branch` 를 함께 준다. | 사용자 결정(REQ-002): 처음에는 기능이 동작하는지가 먼저이고 하한은 필요할 때 사용자가 올린다. 명령줄 하한은 pyproject 값을 덮어 정본이 둘이 된다. `skip-covered` 는 "N files skipped due to complete coverage" 를 찍어 CI 의 `[1-9][0-9]* (skipped|…)` SKIP 판정에 걸린다. 이 저장소에는 85% 를 고정하던 테스트·ADR 이 없었다(주석 처리된 `# fail_under = 80` 뿐) — Superseded 할 대상 없음. 게이트(`review_gate`)는 커버리지를 측정하지 않으므로 그대로 둔다. `--cov-branch` 는 실측으로 필요했다 — 없이 돌리면 subprocess 테스트(실제 uvicorn·설정 검사)의 자식이 `pyproject.toml` 을 못 찾는 작업 디렉터리에서 statement 데이터를 남겨, 결합 단계가 `Can't combine branch coverage data with statement data` 로 INTERNALERROR(종료 코드 3)를 냈다. 플래그를 주면 pytest-cov 가 자식에 `COV_CORE_BRANCH` 를 넘긴다. | Accepted | — |

## 4. 불가침 제약

- **C-1**: 마스킹 패턴은 `_SECRET_PATTERNS` 한 곳에만 둔다 — 다른 모듈에 정규식을 복제하지 않는다(ADR-001).
- **C-2**: 접속 로그 원문 저장(INV-6)은 사용자 결정이다 — 바꾸려면 새 요청으로 이 ADR-004 를 대체한다.
- **C-3**: `REDIS_MIN_VERSION` 을 바꾸면 README·ARCHITECTURE·`.env.example`·compose·CI 주석·`rate_limit`·`refresh_store` docstring 을 함께 바꾼다.
- **C-4**: 선행 그룹의 Active 불가침 제약(`service-hardening` C-1~C-8·C-10, `admin-login` C-1~C-5)을 계승한다.
- **C-5**: 커버리지 하한은 `fail_under` 한 곳이다(ADR-005).

## 5. 변경 이력

- v0.1 (2026-10-13): 최초 작성. REQ-001(A~E), ADR-001~004, C-1~C-4.
- v0.2 (2026-10-13): 추가 요청 REQ-002, ADR-005, C-5.
