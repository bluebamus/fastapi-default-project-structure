# 아키텍처

이 문서는 현재 코드가 어떻게 연결돼 있는지를 설명합니다. 실행·설정은 [README](../README.md),
기능 추가·테스트·마이그레이션은 [DEVELOPMENT](./DEVELOPMENT.md) 를 봅니다.

## 1. 디렉터리 구조

```
main.py                     앱 조립 — 미들웨어, 예외 처리기, include_router, /health·/ready·/docs, 관리 화면, 접근 정책 검사
config.py                   설정(Pydantic Settings) 과 import 시점 설정 검사
app/
  core/                     기능이 공유하는 부품 (기능을 import 하지 않는다)
    db/                     session.py(엔진·세션 의존성), router.py(읽기/쓰기 라우팅), models_registry.py(모델·태스크 탐색)
    models/                 models_base.py(Base·Mixin), types.py(UTCDateTime)
    repositories/           ORM: crud_base → repository_base / Raw: raw_crud_base → raw_repository_base, db_errors.py
    services/               services_base.py(BaseService)
    security/               토큰·비밀번호·레이트 리밋·refresh 저장소·인가·접근 수준·관리 세션
    middlewares/            CORS, 접속 정보 수집, 백그라운드 태스크 상한, 클라이언트 IP
    resources.py            lifespan 자원(로그 큐·DB·Redis·백그라운드 태스크)
    redis.py, exception.py, schemas.py, admin_filters.py, tags_metadata.py
  features/
    <name>/                 auth, blog, catalog, home, reply, reports, sns, user
      __init__.py           router 공개 (+ 모델 import 로 Base.metadata 등록)
      api/routers/router.py v1 서브라우터 취합
      api/routers/v1/*.py   path operation (View)
      dependencies/         세션 선택 + Service 조립(provider)
      services/             비즈니스 규칙
      repositories/         데이터 접근
      models/models.py      ORM 모델
      schemas/              요청·응답 DTO (Pydantic v2)
      exceptions.py         도메인 예외
      admin.py              SQLAdmin ModelView 와 admin_views
      tasks.py              (선택) Celery 태스크
      tests/                기능 테스트
    admin.py                관리 화면 조립 — 기능별 admin_views 를 명시 import 해 등록
  celery/                   app.py(Celery 앱), task.py(run_async), lifecycle.py(worker 자원)
  utils/logs/               로깅 서브시스템
  utils/pagination/         Pagination 데이터클래스
  templates/admin/sqladmin/ 관리 화면 템플릿(로그인 화면, 날짜 필터)
migrations/                 Alembic (env.py, versions/ 의 baseline 리비전)
scripts/                    create_superuser.py, review_gate.py
tests/                      core·utils·scripts 테스트와 기능을 가로지르는 테스트
```

`auth` 는 자체 모델이 없고 `user` 의 `User` 에 대해 인증합니다. 그래서 `models/`·`admin.py` 가 없습니다.

## 2. 요청 경로와 계층

```
View(api/routers/v1) → Dependency(dependencies/) → Service(services/) → Repository(repositories/) → AsyncSession
```

| 계층 | 책임 | 하지 않는 것 |
|---|---|---|
| View | HTTP 계약(파라미터·상태 코드·응답 모델), Service 호출, 응답 DTO 변환, **쓰기 성공 시 커밋** | SQL, 도메인 분기, 세션 직접 주입 |
| Dependency | 세션 선택(읽기/쓰기)과 협력 객체 조립 | 유스케이스 실행, 커밋 |
| Service | 비즈니스 규칙, 인가(소유권), Repository 조합 | 커밋, HTTP 예외 직접 생성 |
| Repository | 쿼리 실행, DB 오류 → 프로젝트 예외 변환 | 커밋, HTTP |

- 기능끼리 import 하지 않습니다. 여러 기능이 쓰는 협력 객체(비밀번호 해시기·토큰 서비스·refresh 저장소·
  소유권 정책)의 provider 는 `app/core/security/dependencies.py` 에 있습니다. 예외: `auth` 는 `user` 의 모델과
  Repository 에 기대어 인증합니다.
- 커밋 위치: 쓰기 핸들러가 응답 DTO 를 먼저 검증하고 `await service.commit()` 을 한 번 부릅니다. 의존성의 `yield`
  뒤(teardown)는 **응답을 보낸 뒤** 실행되므로, 거기서 커밋하면 실패해도 클라이언트는 이미 2xx 를 받습니다.
  예외가 나면 세션 의존성이 rollback 합니다.
- 요청 밖(Celery·접속 로그 적재)은 `background_db_session()` 컨텍스트를 연 쪽이 커밋합니다.
- 공통 Repository API:
  - ORM `BaseRepository`: `create`·`get_by_id`·`get_by_id_or_raise`·`list`·`count`·`exists`·`update_by_id`·
    `delete_by_id`. 이 밖의 쿼리는 기능 Repository 가 명시적 메서드로 소유하고 `self.execute(...)` 로 실행합니다.
  - Raw `RawRepositoryBase`: 미리 만든 `TextClause` 와 바인드 파라미터, `query_name` 을 받아 `RowMapping`·
    scalar·영향 행 수를 돌려줍니다. 문자열 SQL 을 받는 진입점은 없습니다.
  - 두 계층은 서로 상속하지 않고(게이트가 검사), DB 오류 변환은 `db_errors.py` 한 표를 씁니다
    (중복 409, NOT NULL·외래 키 422, 참조 중 삭제 409, 나머지 500 — 응답에 드라이버 원문을 싣지 않음).
- 오류 응답 형식은 모두 `{"error_code", "message", "detail"}` 입니다(`app/core/exception.py` 의 `ErrorResponse`).
  OpenAPI 의 422 문서도 이 형식으로 바꿔 냅니다.
- 시각은 `UTCDateTime` 으로 UTC 저장합니다. naive 값을 넣으면 `ValueError`, MySQL 에서는 `DATETIME(6)` 입니다.

## 3. DB 세션과 읽기/쓰기 라우팅

`app/core/db/session.py`:

| 이름 | 용도 |
|---|---|
| `get_read_only_db_session` | 조회 핸들러. 세션을 읽기 전용으로 표시 — flush·DML 을 시도하면 `ReadOnlyRoutingError` |
| `get_writer_db_session` | 쓰기 핸들러. 첫 쿼리부터 primary 고정 |
| `get_routed_db_session` | 구문 성격으로 동적 라우팅(승인된 특수 경로 전용) |
| `background_db_session()` | 요청 밖 작업. 별도 엔진·풀(`background_engine`) |

엔진은 모두 `hide_parameters=True` 라 예외 문자열과 로그에 바인딩 값이 실리지 않습니다. SQL 본문 로그는
`LOG_SQL_ECHO_ENABLED=true` 일 때만 나옵니다.

라우팅(`app/core/db/router.py`, `DB_ROUTER_ENABLED`·`DB_REPLICATION_ENABLED`·`MYSQL_REPLICA_HOSTS`):

1. ORM flush 또는 Core/`text()` DML → writer
2. 그 밖의 SELECT → replica(라운드로빈, 세션 동안 같은 replica 고정)
3. 쓰기가 한 번이라도 일어난 세션의 이후 SELECT → writer(`DB_READ_STICKY_AFTER_WRITE`, 복제 지연 대비)
4. 잠금 읽기(`FOR UPDATE`·`FOR SHARE`, ORM `with_for_update`) → writer

`text()` 구문은 최상위 키워드를 스캔해 쓰기 여부를 판정하고, 판정이 무너지면(따옴표·괄호 불일치) 쓰기로 봅니다.
읽기 전용 세션의 replica **연결** 오류는 같은 읽기를 primary 로 한 번 재시도합니다.

## 4. 인증과 권한

- **토큰**(`app/core/security/tokens.py`): access·refresh JWT, 서명 키가 서로 다름. 검증은 알고리즘 고정,
  `iss`·`aud`·필수 claim·`type` 확인. 실패 사유는 응답에 싣지 않고 401 하나로 모읍니다. 401 응답에는
  `WWW-Authenticate: Bearer` 를 붙입니다.
- **refresh 회전**(`refresh_store.py`, Redis): `GETDEL` 로 jti 를 소비 — 이미 쓰인 토큰을 다시 내밀면 재사용으로
  보고 그 family 를 폐기합니다. 사용자 비활성화·삭제 시 그 사용자의 family 를 모두 폐기합니다. `GETDEL` 때문에
  Redis 최소 버전이 6.2 이고, 기동 시 확인합니다.
- **비밀번호**(`password_hasher.py`): Argon2id. 예전 bcrypt 해시는 검증 후 Argon2 로 재해시합니다. 없는
  사용자에게도 더미 해시로 같은 비용을 치러 응답 시간으로 사용자명을 알아낼 수 없게 합니다.
- **레이트 리밋**(`rate_limit.py`, Redis 고정 창): 로그인(IP+사용자명, IP), 회원가입(IP). 초과 시 429 와
  `Retry-After`. 클라이언트 IP 는 `TRUSTED_PROXY_HOPS` 로 정합니다(`middlewares/client_ip.py`).
- **접근 수준 선언**(`access.py`): 모든 API 뷰가 `Public`·`PublicWrite`·`LoginRequired`·`SuperuserRequired`
  중 하나를 `dependencies=[...]` 로 선언하거나, 인자 `principal: CurrentPrincipal`·`SuperuserPrincipal` 로
  받습니다. `main.py` 끝의 `AccessPolicyGuard().verify(app)` 가 선언이 없거나 둘 이상인 뷰를 찾으면 **기동을
  멈춥니다**(기본 거부).
- **인가**(`authorization.py`): 슈퍼유저/일반 2단계. 수정·삭제는 `OwnershipPolicy` — 소유자 본인 또는
  슈퍼유저만, 소유자가 NULL 인 행은 슈퍼유저만. `Principal` 은 토큰 claim 으로만 만들어 DB 를 보지 않습니다.
  삭제·비활성화를 즉시 반영해야 하는 `/auth/me` 만 DB 에서 사용자를 다시 읽습니다.
- Redis 연결·시간 초과 오류는 503 `SERVICE_UNAVAILABLE` 로 응답합니다(fail-closed).

## 5. 관리 화면 (SQLAdmin, `/admin`)

- 각 기능의 `admin.py` 가 `ModelView` 와 `admin_views` 를 정의하고, `app/features/admin.py` 가 그것들을
  **명시 import** 해 `ADMIN_VIEWS` 로 등록합니다. 파일이 없거나 `admin_views` 가 빠지면 기동 시 ImportError 입니다.
- 로그인은 **활성 슈퍼유저**만. 자격 확인은 API 와 같은 `AuthService.authenticate` 이고 레이트 리밋도 같은 한도를
  쓰되 키 접두사(`admin:rl:login:`)를 나눕니다. 요청마다 사용자를 다시 읽어 강등·비활성화가 바로 반영됩니다.
- 세션은 Redis 서버 세션입니다(`app/core/security/admin_session.py`). 쿠키 `admin_session` 에는 무작위 세션 ID 만
  있고(path `/admin`, SameSite=Strict, HttpOnly, staging/production 은 Secure), Redis 키는 `SESSION_SECRET_KEY`
  로 만든 HMAC 입니다. 만료는 절대(`ADMIN_SESSION_MAX_AGE_SECONDS`) + 미사용(`ADMIN_SESSION_IDLE_SECONDS`).
  사용자 강등·비활성화·삭제 시 그 사용자의 관리 세션을 모두 지웁니다.
- CSRF: `/admin` 의 POST·PUT·PATCH·DELETE 전부를 synchronizer token(헤더 `X-CSRF-Token` 또는 폼 필드
  `csrf_token`)으로 검사합니다. 로그아웃은 POST 만 받습니다.
- 날짜 필터 `LocalDateFilter`(`app/core/admin_filters.py`)는 업무 시간대(`TIME_ZONE`) 날짜를 UTC 범위로 바꿔
  질의합니다.
- `User` 화면은 `hashed_password` 를 상세·폼에서 제외하고 생성을 막습니다.
- `ADMIN_DISABLED=true` 면 sqladmin 을 import 하지도 마운트하지도 않습니다(`/admin` 404).

## 6. 미들웨어와 예외 처리

등록 순서(바깥 → 안):

1. `unhandled_exception_middleware`(`main.py`) — 처리기가 없는 예외를 받아 500 `ErrorResponse` 로 끝냅니다.
   `DEBUG=true` 면 다시 던집니다.
2. `UserInfoMiddleware`(`app/core/middlewares/user_info_middleware.py`) — `ACCESS_LOG_ENABLED` 이고 제외 경로·
   확장자가 아닌 요청의 IP·User-Agent·경로·응답 상태·소요 시간을 모아, 응답 뒤 백그라운드 태스크로 넘깁니다.
   쿼리스트링의 민감 키(`ACCESS_LOG_SENSITIVE_QUERY_KEYS`)는 값을 가립니다.
3. CORS(`cors_middleware.py`, `CORS_*` 설정).

접속 로그 적재 경로: 미들웨어 → `access_log_tasks`(`background_tasks.py`, 동시 실행 상한 초과분은 버리고 집계) →
등록된 sink(`app/features/home/access_log_sink.py`) → `background_db_session()`. core 는 home 을 import 하지 않고
home 이 import 시점에 sink 를 등록합니다.

예외 처리기(`main.py`): `AppException` → 그 상태 코드(4xx 는 WARNING, 5xx 는 ERROR 로 기록),
요청 검증 실패 → 422, Starlette `HTTPException` → `HTTP_<code>`, Redis 연결 오류 → 503, 나머지 → 500
(`detail` 은 `DEBUG` 에서만, 비밀값은 가림).

## 7. 로깅 (`app/utils/logs`)

- `configure_logging()` 이 `build_dictconfig()` 로 root 로거를 한 번 구성합니다. root 에는
  `BoundedQueueHandler` 하나만 붙고, 실제 출력은 `QueueListener` 스레드가 합니다 — 요청 event loop 에서
  write·flush·회전이 일어나지 않습니다. 큐가 가득 차면 DEBUG~WARNING 은 버리고 집계, ERROR 이상은 stderr 로
  최소 포맷을 바로 씁니다.
- 헤더: `[시각 TZ] LEVEL [app=..] [module:class:func:line] message`(`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`).
  `app=` 은 우리 코드는 소스 경로, 외부 코드는 로거 이름에서 뽑습니다. 클래스명은 `LoggerMixin`(`self.log`)이
  주입하거나 호출 프레임에서 찾습니다. 헤더별 최소 레벨은 `LOG_APP_LEVELS`(예 `blog=DEBUG,sqlalchemy=WARNING`).
- 레벨은 `LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·`LOG_FILE_LEVEL` 이 명시되지 않으면 `DEBUG` 와 `ENV` 로 정해집니다.
- 마스킹: `config.LOG_SECRET_SETTINGS` 에 적힌 설정값(DB·Redis 자격증명, 서명·세션 키)은 모든 로그 줄과
  500 응답 `detail` 에서 가려집니다.
- 파일(`LOG_FILE_ENABLED=true`): 프로세스 종류별로 `LOG_DIR` 아래 `app.log`·`error.log`(웹),
  `celery.log`·`celery-error.log`(worker·beat). 매일 자정과 `LOG_MAX_SIZE_MB` 에서 회전하고
  `LOG_RETENTION_DAYS` 보다 오래된 파일을 지웁니다. **여러 프로세스가 같은 파일을 회전시키는 것은 안전하지
  않습니다** — 워커가 여럿이면 콘솔 출력 + 수집기를 쓰거나 프로세스마다 `LOG_DIR` 을 나눕니다.
- uvicorn CLI·Celery 가 단 콘솔 핸들러도 같은 큐로 바꿔 끼워 같은 포맷·필터를 씁니다.
- listener 의 종료(flush·stop)는 프로세스가 소유합니다(`atexit`, `python main.py` 는 신호 처리 포함).
  lifespan 은 listener 를 멈추지 않고 종료 시 쌓인 로그가 나갈 때까지 기다리기만 합니다.

## 8. Celery (`app/celery`)

- `celery_app` 의 broker·backend 는 Redis(`REDIS_URL`)입니다. 태스크는 각 기능의 `tasks.py` 에 두고,
  `include` 는 `models_registry.iter_task_modules()` 가 디렉터리에서 찾습니다 — 중앙 목록이 없어 기능을 지우면
  태스크도 같이 빠집니다.
- 주기 작업은 기능의 `tasks.py` 가 `celery_app.conf.beat_schedule` 에 스스로 등록합니다. 현재는 `home` 의
  접속 로그 보존 기간 삭제(하루 한 번)와 통계 집계 태스크가 있습니다.
- async 코드는 `run_async()` 로 실행합니다 — worker 프로세스마다 영속 event loop 하나를 재사용합니다(커넥션
  풀이 루프에 묶이기 때문). worker 종료 시 `lifecycle.py` 가 DB 엔진 dispose → async generator 정리 → 루프
  닫기 순서로 정리합니다. 시각은 UTC, beat 의 crontab 은 `TIME_ZONE` 으로 해석합니다.

## 9. 수명주기 (`app/core/resources.py`)

`main.py` 의 lifespan 은 `manage_application_resources(app)` 하나만 엽니다. 자원은 획득 순서대로 중첩되고
정리는 역순입니다:

```
async with _log_queue(), _database(app), _redis(app), _background_tasks():
    _prepare_database()   # 모델 import, DEBUG 면 없는 테이블 생성
# 정리: 백그라운드 태스크 drain → Redis close → DB 엔진 dispose → 로그 큐 flush
```

- startup: Redis `PING` 과 서버 버전(6.2 이상) 확인 — 실패하면 기동 실패. DB 는 `DEBUG=true` 일 때만
  `create_all`(없는 테이블만). 운영 스키마는 Alembic 이 유일한 경로입니다.
- shutdown: 단계마다 시간 예산(백그라운드 5초, DB 10초, Redis 5초, 합계 20초)이 있고, 한 단계가 실패하거나
  취소돼도 뒤 단계는 실행됩니다(중첩 컨텍스트가 보장). 운영 코드에는 `drop_all` 이 없습니다(게이트가 검사).
- `/health` 는 외부 연결을 보지 않고, `/ready` 는 writer DB 와 Redis 를 동시에 확인합니다.
