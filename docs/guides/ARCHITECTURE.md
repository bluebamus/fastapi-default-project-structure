# 아키텍처·런타임 레퍼런스

이 저장소가 **어떻게 조립되고, 어떻게 뜨고, 요청을 어떻게 처리하고, 어떻게 끝나는지**를 한곳에
적습니다. 설치·실행은 [README](../../README.md), 코드를 쓰는 절차는 [DEVELOPMENT](./DEVELOPMENT.md)
를 봅니다. 같은 흐름을 도식과 함께 따라가는 요약은
[서버 수명주기 안내서](./workflows/server-lifecycle.html)이고, 상세 표는 이 문서가 소유합니다. 코드와 이 문서가
다르면 코드가 정답이며, 이 문서(와 요약하는 HTML)를 고칩니다.

본문에 나오는 `ADR-0xx`·`REQ-0xx` 는 `docs/crp/groups/orm-raw-repository/design-baseline.md`,
`AR-`·`TX-`·`NFR-` 등은 `docs/specs/orm-raw-repository/requirements.md` 의 ID 입니다.
`service-hardening ADR-0xx` 처럼 그룹 이름이 붙은 번호는 `docs/crp/groups/service-hardening/design-baseline.md` 의 ID 입니다.
`admin-login ADR-0xx` 는 `docs/crp/groups/admin-login/design-baseline.md` 의 ID 입니다. 관리 화면 인증의 흐름도·운영은
[관리 화면 인증 안내서](./workflows/admin-authentication.html)가 원본입니다.

## 목차

1. [구조와 의존 방향](#1-구조와-의존-방향)
2. [배선 — 라우터·모델·훅](#2-배선--라우터모델훅)
3. [요청 처리 흐름](#3-요청-처리-흐름)
4. [DB 엔진·세션·라우팅](#4-db-엔진세션라우팅)
5. [데이터 접근 계약](#5-데이터-접근-계약)
6. [설정](#6-설정)
7. [기동](#7-기동)
8. [종료](#8-종료)
9. [로깅](#9-로깅)
10. [접속 로그 미들웨어](#10-접속-로그-미들웨어)
11. [인증 (JWT)](#11-인증-jwt)
12. [SQLAdmin](#12-sqladmin)
13. [Celery](#13-celery)
14. [Alembic](#14-alembic)
15. [설계 결정 요약](#15-설계-결정-요약)
16. [변경 이력](#16-변경-이력)
- [부록. 설정 필드 전체](#부록-설정-필드-전체)

---

## 1. 구조와 의존 방향

### 1.1 폴더 구조

```
.
├── main.py                 # FastAPI 조립: 미들웨어·예외 핸들러·라우터·health/ready·Scalar·Admin, run_server()
├── config.py               # Pydantic Settings 9종 — 환경 변수를 읽는 유일한 모듈
├── conftest.py             # pytest 전역 옵션 --mysql-required (루트에 있어야 인식된다)
├── pyproject.toml / uv.lock / .python-version
├── alembic.ini / migrations/        # env.py 가 import_all_models() 로 전 기능 모델 수집
├── compose.test.yaml       # 테스트용 MySQL 8.4(127.0.0.1:3308, tmpfs) + Redis 7(6379, 앱 최소 6.2)
├── compose.e2e.yaml        # E2E 스택 — MySQL primary·GTID replica·Redis 7.4(-p itest-default, 하네스가 띄우고 내린다)
├── scripts/review_gate.py  # 결정적 검수 게이트
├── .github/workflows/ci.yml
├── app/
│   ├── features/                    # 기능 단위 vertical slice
│   │   ├── admin.py                 # SQLAdmin 취합 — ADMIN_VIEWS + 인증 백엔드 조립 + register_admin()
│   │   ├── auth/                    # OAuth2 password + JWT (자체 모델 없음, user 모델 사용) + admin_backend.py(/admin 로그인)
│   │   ├── blog/ reply/ sns/ user/  # CRUD 기능
│   │   ├── home/                    # 접속 로그 조회 + access-log sink
│   │   ├── catalog/                 # ORM 참조 예제 (상품 CRUD)
│   │   └── reports/                 # Raw SQL 참조 예제 (일별 매출 집계·스냅샷 적재)
│   │       ├── __init__.py          # router 공개 + models import
│   │       ├── admin.py             # 기능 소유 ModelView + admin_views
│   │       ├── api/routers/router.py   # <name>_router — v1 서브라우터를 prefix 와 tag 로 취합
│   │       ├── api/routers/v1/*.py     # path operation (HTTP 역할 + 쓰기 커밋)
│   │       ├── dependencies/        # <x>_dependencies.py — 세션 선택 + Service 조립
│   │       ├── services/ repositories/ schemas/ models/
│   │       ├── exceptions.py        # 기능 예외 (AppException 하위)
│   │       ├── tasks.py             # (있으면) Celery 태스크 — worker include 에 자동 발견
│   │       └── tests/
│   ├── core/                        # 프레임워크 인프라
│   │   ├── resources.py             # 프로세스 수명 자원의 생성·해제 단일 지점
│   │   ├── redis.py                 # get_redis — lifespan Redis client 주입 provider, REDIS_MIN_VERSION·ensure_redis_version
│   │   ├── security/                # 토큰·회전 저장소·레이트 리밋·PasswordHasher·Principal·OwnershipPolicy·관리 세션(admin_session.py) + provider — §11·§12
│   │   ├── exception.py             # AppException 계층 + ErrorResponse
│   │   ├── schemas.py               # PatchSchema(모든 Update 스키마의 기반 — null PATCH 거부)
│   │   ├── tags_metadata.py         # OpenAPI 태그 설명
│   │   ├── db/session.py            # 엔진·세션 팩토리·세션 의존성·create_db_tables·ping·dispose
│   │   ├── db/router.py             # 읽기/쓰기 라우팅(RoutingSession)
│   │   ├── db/models_registry.py    # 기능 모델·태스크 모듈 탐색 단일 지점(모델은 import)
│   │   ├── models/models_base.py    # Base + UUID/Created/Updated Mixin
│   │   ├── repositories/            # crud_base·repository_base(ORM) / raw_crud_base·raw_repository_base(Raw) / db_errors(DB 오류 변환 표)
│   │   ├── services/services_base.py
│   │   └── middlewares/             # cors_middleware·user_info_middleware·client_ip·background_tasks·access_log_sink
│   ├── celery/                      # app.py(중앙 앱, include 는 기능 tasks.py 자동 발견)·task.py(run_async)·lifecycle.py
│   ├── templates/admin/sqladmin/            # login.html(Bootstrap 로그인 화면)·base.html(원본 확장 + CSRF meta·스크립트)·filters/ — §12
│   └── utils/                       # logs/ · pagination/ · validators.py
├── tests/                  # core 계약·배선·교차 기능 / utils / integration(실제 uvicorn·MySQL) / e2e(전수 통합, 마커 e2e)
├── docs/                   # guides/ · specs/ · crp/  (색인은 README)
└── media/ static/ poc/ logs/   # 예약 디렉터리 (추적하지 않음, logs/ 는 LOG_FILE_ENABLED=true 일 때 프로세스별 파일 — §9.2)
```

### 1.2 의존 방향과 기능 간 참조

```
features → core → utils        (config 는 누구나 import)
```

| 영역 | 규칙 |
|---|---|
| `app/features/<name>/` | 비즈니스 코드는 전부 여기. `core` 를 쓰고 **다른 기능을 import 하지 않는다.** 예외: `auth` 는 횡단 관심사라 `user` 의 모델·Repository 를 쓴다. 기능 간 데이터 참조는 FK 없는 식별자로 둔다(예: `Reply.post_id`) |
| `app/core/` | 특정 기능을 직접 알지 않는다. 기능이 core 에 붙어야 하면 등록 훅을 쓴다(`access_log_sink.set_access_log_sink()`). `models_registry` 만 등록 목적으로 기능 모델을 동적 import 하고, 기능 `tasks.py` 의 존재를 찾아 Celery include 를 만든다(import 는 Celery 가 한다) |
| `app/utils/` | 순수 유틸. 상위 계층에 의존하지 않는다 |

### 1.3 핵심 파일

| 파일 | 역할 |
|---|---|
| `main.py` | `FastAPI(...)` 생성(lifespan·태그·문서 URL), `CustomCORSMiddleware`·`UserInfoMiddleware` 등록, 예외 핸들러 4종 + Redis 연결 오류 503 + 가장 바깥 `unhandled_exception_middleware`(§3.3), 기능 라우터 8개 `include_router(prefix="/api")`, `/health`·`/ready`·Scalar `/docs`, 422 문서 후처리(`_openapi_with_actual_422`), `ADMIN_DISABLED` 가 아니면 `register_admin(app, engine)`, 마지막에 `AccessPolicyGuard().verify(app)`(§11.2) |
| `app/core/resources.py` | `manage_application_resources()` — Redis 확인, 개발용 테이블 생성, 역순 정리 (§7·§8) |
| `app/core/db/session.py` | 엔진 3종, 세션 의존성 5종, `create_db_tables()`, `ping_writer_db()`, `dispose_engine()` (§4) |
| `app/utils/logs/` | 큐 기반 로깅과 listener 수명 (§9). **손대기 전에 §9 를 읽는다** |
| `app/features/admin.py` | 기능별 `admin_views` 의 명시 취합과 조립 (§12) |

## 2. 배선 — 라우터·모델·훅

### 2.1 라우터

자동 탐색도 중앙 목록도 없습니다. 세 단계를 **명시적으로** 거칩니다(AR-004).

```python
# app/features/catalog/api/routers/router.py
catalog_router = APIRouter()
catalog_router.include_router(products_v1.router, prefix="/v1/catalog", tags=["Catalog"])

# app/features/catalog/__init__.py
from app.features.catalog.api.routers.router import catalog_router as router
from app.features.catalog.models import models as _models  # noqa: F401 (Base.metadata 등록)
__all__ = ["router"]

# main.py
from app.features import auth, blog, catalog, home, reply, reports, sns, user
app.include_router(catalog.router, prefix="/api")
```

- 최종 URL 은 **prefix 의 합**입니다: `v1/products.py` 의 `/products` + `/v1/catalog` + `/api`
  = `/api/v1/catalog/products`. 디렉터리 이름이 URL 을 만들지 않습니다.
- 기능명과 URL 세그먼트가 같아야 합니다 — `tests/test_router_registration.py` 가
  `/api/v1/<기능명>/` 으로 마운트 여부를 확인합니다.
- **폴더가 있어도 `main.py` 에 없으면 라우트는 없습니다.** 버전 세그먼트(`/v1`)는 설정이 아니라 각
  `router.py` 가 직접 선언합니다(버전 설정 `API_VERSION` 은 읽는 코드가 없어 지웠습니다 — config-cleanup-2).
- 기능 `__init__.py` 는 `admin_views` 를 재노출하지 않습니다(§12).

### 2.2 모델 메타데이터

라우터와 달리 모델은 **디렉터리 구조가 진실의 원천**입니다. `models_registry.iter_model_modules()` 가
`app/features/*/models/models.py` 를 찾아 정렬하고, `import_all_models()` 가 import 해
`Base.metadata` 를 채웁니다. `auth` 처럼 모델이 없는 기능은 건너뜁니다.

- 소비처: `app/core/resources.py`(startup), `migrations/env.py`(Alembic), `create_db_tables(import_models=True)`.
- 그래서 `main.py` 에서 라우터를 빼도 폴더가 남아 있으면 **모델은 여전히** 테이블 생성·Alembic 대상입니다.
  기능 제거는 라우터·테이블·데이터·migration 을 함께 판단합니다. 앱에서 빼도 DB 테이블은 지워지지 않습니다.
- 모델 클래스가 import 되면 metadata 에 등록될 뿐, DB 에 테이블이 생기는 것은 개발용 `create_all`
  또는 Alembic 입니다.

### 2.3 import 시점 훅

`app/features/home/__init__.py` 는 import 되는 순간 `register_sink()` 로 `HomeAccessLogSink` 를
미들웨어에 등록합니다(§10). 네트워크 연결이 아니라 프로세스 안의 참조 연결입니다.

## 3. 요청 처리 흐름

### 3.1 한 요청의 경로

```
요청 → unhandled_exception_middleware → UserInfoMiddleware → CORSMiddleware → 라우트
     → Depends: 세션 의존성(get_writer_db_session / get_read_only_db_session)
              → 기능 의존성 get_<name>_service[_readonly] → Service(db_session)
     → View 본문: Service 유스케이스 호출 → (쓰기면) await service.commit() → 응답 DTO
     → 응답 → UserInfoMiddleware 가 접속 로그 저장 태스크 제출 (§10)
     → 의존성 teardown: 세션 close (닫히면서 ROLLBACK 이 나간다)
```

| 계층 | 하는 일 | 하지 않는 일 |
|---|---|---|
| View(`api/routers/v1`) | 파라미터·본문 수신, Service 호출, 쓰기 커밋, 응답 DTO 변환, OpenAPI 메타데이터 | SQL, `AsyncSession` 직접 주입, 복잡한 도메인 분기 |
| Dependency | 세션 선택 + `Service(db_session)` 조립 후 **반환**(`yield` 아님) | 유스케이스 실행, 커밋 |
| Service(`BaseService`) | 유스케이스·비즈니스 규칙, 같은 세션으로 Repository 조립 | HTTP 객체, SQL 문자열, 커밋 시점 결정 |
| Repository | ORM 쿼리 또는 Raw SQL, `flush` 까지 | 커밋, HTTP 응답, 비즈니스 규칙 |
| Schema | 입력 검증·응답 공개 필드·문서 | DB 접근 |

미들웨어는 나중에 등록한 것이 바깥이라 `_register_exception_handlers` 가 마지막에 등록하는
`unhandled_exception_middleware` 가 가장 바깥이고, 그 안이 `UserInfoMiddleware` 입니다(§3.3).
같은 요청 안에서 같은 의존성 함수는 FastAPI 기본(`use_cache=True`)으로 한 번만 실행되지만,
writer 와 read-only 는 다른 함수라 서로 다른 세션입니다.

### 3.2 트랜잭션 경계 — 쓰기 핸들러가 커밋한다

```python
# dependencies — 조립만
async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(db_session)

# View — 응답 DTO 검증 → 커밋(한 번) → 반환
async def create_product(payload: ProductCreate, service: CatalogService = Depends(get_catalog_service)):
    product = await service.create_product(payload)
    response = ProductResponse.model_validate(product)
    await service.commit()
    return response
```

- **성공**: View 본문이 응답 DTO 를 검증한 **뒤** 응답을 반환하기 전에 `await service.commit()` (TX-004).
  모든 쓰기 핸들러(catalog·blog·reply·sns·user·auth)가 이 순서이며, DTO 검증이 실패하면 커밋 0회로
  500 이 됩니다(`tests/test_write_dto_before_commit.py`). reports 스냅샷 적재는 Service 가 커밋 전에
  응답 DTO 를 만들어 돌려줍니다.
- **예외**: 커밋이 실행되지 않고 예외는 그대로 올라갑니다. 롤백은 `async with` 종료가 맡습니다 —
  `AsyncSession.__aexit__` 이 shield 로 감싼 `close()` 를 실행하고 `close()` 가 ROLLBACK 을 보냅니다(ADR-031).
- **조회**: `_readonly` 의존성 → `get_read_only_db_session`, 커밋 0회(TX-002).
- **요청 밖**(background·Celery): `async with background_db_session() as db_session:` 에서 호출자가
  직접 커밋합니다(별도 풀).

**왜 의존성이 아니라 핸들러인가.** 예전에는 의존성이 `yield` 뒤에서 커밋했습니다. FastAPI 0.141 로
올리자 기본 request scope 의 yield 의존성 종료 코드가 **응답 전송 후** 실행되어, 커밋이 실패해도
클라이언트가 `201` 을 받았습니다(`scope="function"` 은 종료 시점이 다릅니다 —
[공식 설명](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)).
커밋을 핸들러 본문으로 옮겨 실패가 응답 코드에 반영되게 했습니다.
구조 증거: `tests/test_read_path_no_commit.py`, `app/features/blog/tests/test_transaction_boundary.py`.

DB 커밋과 HTTP 전송은 하나의 원자적 작업이 아닙니다. 커밋 뒤 연결이 끊기거나 직렬화가 실패할 수
있으므로, 중복이 치명적인 생성 업무는 idempotency 정책을 따로 정합니다([DEVELOPMENT §4](./DEVELOPMENT.md#4-트랜잭션-규칙)).

### 3.3 예외와 오류 응답

`main.py` 의 핸들러 4종(+ Redis 연결 오류 503)이 모든 오류를 `ErrorResponse`(`error_code`·`message`·`detail`)로 바꿉니다.

| 예외 | 응답 |
|---|---|
| `AppException` 과 하위(`NotFoundException`·`DuplicateException`·`DatabaseException`…) | 예외가 가진 상태 코드·`error_code`. 로그는 4xx 면 WARNING(detail 없음), 5xx 면 ERROR(detail 포함) — service-hardening ADR-008 ④ |
| `RequestValidationError` | 422, `detail` 에 `field`·`message`·`type` 목록. OpenAPI 의 422 도 이 `ErrorResponse` 로 광고한다 — FastAPI 기본 `HTTPValidationError` 는 앱 생성 시 후처리(`main._openapi_with_actual_422`)로 바꾼다(integration-e2e ADR-012, `tests/test_openapi_contract.py`) |
| Starlette `HTTPException` | 해당 코드, `error_code=HTTP_<코드>` |
| redis `ConnectionError`·`TimeoutError` | 503 `SERVICE_UNAVAILABLE`(fail-closed — 요청은 거부, 내부 정보 없음). 로그는 ERROR `[RedisUnavailable]` + traceback 한 번. 정상 응답으로 끝나 keep-alive 연결이 유지된다 — 아래 `Exception` 핸들러는 Starlette `ServerErrorMiddleware` 에 걸려 응답 뒤 예외를 다시 던지므로(uvicorn 이 traceback 을 한 번 더 남기고 연결을 닫는다) 그리로 보내지 않는다. 명령 오류(`ResponseError` 등)는 500 그대로 (integration-e2e ADR-009) |
| 그 밖의 `Exception` | 500 `INTERNAL_SERVER_ERROR`. **`DEBUG=true` 면 `detail` 에 예외 문자열**이 실린다 — 로그와 같은 `redact()` 로 비밀값을 가린 뒤(log-redaction ADR-001). `DEBUG=false` 에서는 가장 바깥 사용자 미들웨어 `unhandled_exception_middleware`(`@app.middleware("http")`, 미들웨어 등록의 마지막)가 예외를 받아 같은 처리기로 응답을 끝낸다 — 로그 `[UnhandledException]` 한 번, uvicorn `Exception in ASGI application` 없음, keep-alive 유지. CORS·UserInfo 안에서 난 예외도 받는다. `DEBUG=true` 는 다시 던져 `ServerErrorMiddleware` 까지 간다. 응답 본문 전송 중의 예외는 기존대로(integration-e2e ADR-016, `tests/test_unhandled_exception.py`) |

`AppException`·`HTTPException` 핸들러는 예외의 `headers` 를 응답에 그대로 싣습니다 — 405 `Allow`(라우팅이 채운다),
401 `WWW-Authenticate: Bearer`, 429 `Retry-After`(log-redaction ADR-002, `tests/test_exception_headers.py`).
401 은 예외가 헤더를 싣지 않았어도 두 핸들러가 `WWW-Authenticate: Bearer` 를 보탭니다(`main._with_bearer_challenge`) —
로그인 실패(`InvalidCredentialsException`)·refresh·logout·틀린 토큰(`InvalidTokenException`)까지 모든 401 이 같다(integration-e2e ADR-013).
405 의 `Allow` 는 Starlette 가 **처음 걸린 라우트의 메서드**로 채웁니다 — 같은 경로를 메서드별 함수로 나눈 곳
(`GET`·`POST /api/v1/blog/posts`)에서는 그 경로의 메서드 전부가 아니라 하나만 실립니다.

핸들러는 `JSONResponse(content=model.model_dump(mode="json"))` 로 직렬화합니다 — `detail` 에
datetime·UUID 가 들어와도 깨지지 않게 하기 위해서입니다(`tests/test_response_serialization.py`).
일반 응답은 `response_model` 을 통해 Pydantic 이 직접 JSON 을 만듭니다(커스텀 응답 클래스 없음).
startup 예외는 HTTP 핸들러가 처리하지 않습니다(§7.3).

### 3.4 health 와 ready

| 경로 | 의미 |
|---|---|
| `GET /health` | 프로세스 생존과 `VERSION`. 외부 연결을 검사하지 않는다 (liveness) |
| `GET /ready` | `ping_writer_db()`(writer 엔진에서 `SELECT 1`)와 Redis `PING`(`get_redis` 로 주입받은 lifespan client)을 **동시에**, 각각 2초(`READINESS_TIMEOUT_SECONDS`) 안에 실행한다. 하나라도 실패·초과면 503. 응답에는 원문이 없고, 서버 로그에는 대상(`DB`·`Redis`)과 예외 타입만 남긴다(DSN·호스트·드라이버 원문 비노출). client 가 없으면(lifespan 밖) provider 가 503 (service-hardening ADR-011) |

## 4. DB 엔진·세션·라우팅

### 4.1 엔진과 커넥션 풀

`app/core/db/session.py` 가 **import 시점**에 엔진을 만듭니다. 엔진 생성은 URL·풀 정책 준비일 뿐
접속이 아닙니다 — 실제 연결은 DDL·`/ready`·첫 쿼리에서 생깁니다.

| 객체 | 풀 | 용도 |
|---|---|---|
| `engine`(= `writer_engine`) | `pool_size=20`, `max_overflow=20`, `pool_timeout=30` | 요청 세션, 개발 DDL, `/ready`, SQLAdmin |
| `read_engines` | replica 마다 20+20 | `DB_ROUTER_ENABLED` 와 `DB_REPLICATION_ENABLED` 가 모두 true 일 때만 생성 |
| `background_engine` | `pool_size=10`, `max_overflow=10`, `pool_timeout=60` | 접속 로그 sink, `background_db_session()`, Celery |

공통: `pool_recycle=280`, `pool_pre_ping=True`, `pool_reset_on_return="rollback"`, `hide_parameters=True`,
`connect_timeout=10`, `charset=utf8mb4`. `hide_parameters` 는 드라이버 예외의 `str()`·echo 로그에서 바인드 값을 뺀다 —
SQL 문은 남고 값(이메일·해시·토큰)만 `[SQL parameters hidden due to hide_parameters=True]` 로 바뀐다. 앱의 엔진 생성
지점은 이 파일의 셋뿐이고, 새 지점이 생기면 `tests/core/test_db_hide_parameters.py` 가 실패한다(security-ops-hardening ADR-001). 세션 팩토리는 `expire_on_commit=False`, `autoflush=False`.

**연결 예산**(NFR-007): API 프로세스 하나가 최대 `40 + 20 + 40 × replica 수` 개를 엽니다.
uvicorn worker·reload 프로세스마다 곱해지고, Celery worker 프로세스도 import 한 엔진을 따로 가집니다.
DB `max_connections` 안에 들어오는지 배포 전에 계산합니다.

### 4.2 세션 의존성

이름에 `db_session` 을 넣어 사용자·HTTP 세션과 구분합니다(TX-005). 아래 다섯이 공개 이름의 전부이며,
옛 이름(`get_session` 등)은 제거됐고 `tests/core/test_db_session_naming.py` 가 부활을 막습니다.

| 이름 | 용도 | 동작 |
|---|---|---|
| `get_read_only_db_session` | GET/HEAD·변경 없는 조회 | `mark_read_only()` — 라우터가 켜져 있으면 replica 로, 쓰기 시 `ReadOnlyRoutingError` |
| `get_writer_db_session` | 쓰기, 조회 후 쓰기 | `using_writer()` — 첫 쿼리부터 primary 고정 |
| `get_routed_db_session` | 승인된 특수 경로 | 구문마다 동적 선택(첫 SELECT 가 replica 로 샐 수 있다) |
| `get_background_db_session` | DI 안에서 background 풀이 필요할 때 | background 엔진 |
| `background_db_session()` | 요청 밖 컨텍스트(Celery·fire-and-forget) | 예외 시 rollback, 종료 시 close, 커밋은 호출자 |

다섯 모두 `async with` 안에서 세션을 내주고 종료 시 close 합니다. 세션은 풀에서 빌린 연결이므로 반드시 이
경로로 닫혀야 합니다. `get_read_only_db_session`·`get_writer_db_session` 에는 `try/except/rollback` 이
**없습니다**(ADR-031) — `AsyncSession.__aexit__` 이 shield 로 감싼 `close()` 를 실행하고 `close()` 가
ROLLBACK 을 보내므로 중복이었고, 명시 `except Exception` 은 `CancelledError` 를 놓쳐 오히려 좁았습니다.
의존성 넷 중 `get_routed_db_session`·`get_background_db_session` 만 `except` 를 남겨 두었습니다. 그 블록은
`await session.rollback()` 을 **여전히 호출하지만**, 그 호출은 위와 같은 이유로 중복입니다 — 블록을
남긴 이유는 롤백이 아니라 **로그 부수효과**(예외 타입·소요 시간, DEBUG 에서는 전문)입니다.
예외 **메시지**를 기본 로그에 남기지 않는 것도 의도입니다: DB 예외의 `str()` 에는 실행된 SQL 과
바인딩 값이 들어 있고 이 로거 이름(`app.core.*`)은 SQL 소음 필터를 통과합니다.

### 4.3 읽기/쓰기 라우팅

`DB_ROUTER_ENABLED=true` 면 `create_routing_sessionmaker()` 의 `RoutingSession.get_bind()` 가 구문마다
엔진을 고릅니다(`app/core/db/router.py`).

1. ORM flush·Core DML·`text()` 의 쓰기 키워드(`INSERT`·`UPDATE`·`DELETE`·`CREATE`…), CTE 로 감싼 DML
   (`WITH … UPDATE/DELETE`), 잠금 읽기(`FOR UPDATE`·`FOR SHARE`·`LOCK IN SHARE MODE`, ORM
   `select(...).with_for_update()` 포함) → writer
2. 그 밖의 SELECT → 세션당 하나의 replica(라운드로빈으로 고른 뒤 고정)
3. 쓰기가 일어난 세션의 이후 SELECT → writer (`DB_READ_STICKY_AFTER_WRITE=true`, 기본)

| `routing_mode` | 조건 | 결과 |
|---|---|---|
| `single` | `DB_ROUTER_ENABLED=false`(기본) | 단일 엔진 세션. 라우팅만 없고 **읽기 세션의 쓰기 차단은 동작한다** |
| `router-single` | 라우터만 켬 | 전부 primary |
| `router-replicated` | 라우터 + 복제 + `MYSQL_REPLICA_HOSTS` | SELECT → replica, 쓰기 → primary |

읽기 세션의 쓰기 차단은 위 모드와 **무관합니다**. `app/core/db/router.py` 가 `Session` 기반 클래스에
`before_flush`·`do_orm_execute` 리스너를 전역 등록하므로, 어떤 sessionmaker 로 만든 세션이든
`mark_read_only()` 가 걸린 세션에서는 ORM flush·Core DML·Raw `text()` DML 이 `ReadOnlyRoutingError`
로 거부됩니다. 판정은 default-deny 이고 절차는 DEVELOPMENT §7.2 에 있습니다.

- **replica 장애:** 읽기 전용 세션(`get_read_only_db_session`)의 읽기가 replica **연결** 오류(MySQL 2002·2003·2006·2013
  또는 SQLAlchemy 가 연결을 무효화한 오류 — 접속 불가·연결 끊김·타임아웃)로 실패하면 `RoutingSession` 의
  `do_orm_execute` 리스너가 같은 구문을 primary 로 **한 번** 다시 실행하고 WARNING `[database] replica 연결 실패(<타입>(code=…))`
  를 남깁니다(호스트·DSN 없음). 그 세션은 이후 primary 에 고정됩니다. 쿼리 문법·제약 오류는 재시도하지 않고,
  읽기 전용이 아닌 세션(writer·투명 라우팅)도 재시도하지 않습니다 — 쓰기와 한 트랜잭션에 섞일 수 있어서입니다.
  replica 가 없으면(단일 DB) 동작 변화가 없습니다. `/ready` 는 그대로 writer·Redis 만 봅니다(integration-e2e ADR-010).
- **인증 사용자 조회는 primary:** `get_current_user`(`/me`)는 읽기 전용 세션에 `using_writer()` 를 더해 primary 에서 읽습니다 —
  복제 지연 동안 막 가입한 사용자의 유효한 토큰이 401 이 되지 않고, 비활성화·삭제가 즉시 반영됩니다. 쓰기 차단은 그대로이고
  나머지 읽기 라우팅은 바뀌지 않습니다(integration-e2e ADR-014).
- 복제만 켜고 라우터를 끄거나 replica 목록이 비면 `DatabaseSettings` 가 기동 시 거부합니다.
  replica 주소는 `host`·`host:port`·`[IPv6]:port` 만 허용합니다.
- 기동 로그 `[database] 라우팅 구성: {...}` 에 모드와 비밀번호를 가린 DSN 이 남습니다(`URL.render_as_string(hide_password=True)`).
- DSN 은 문자열로 조립하지 않고 `config.mysql_url()` → `sqlalchemy.engine.URL.create()` 로 만듭니다.
  `MYSQL_URL`·`MYSQL_WRITER_URL`·`MYSQL_REPLICA_URLS`·`ALEMBIC_URL` 은 `URL` 객체이고, 비밀번호의
  `@ : / # % ?` 와 IPv6 호스트가 그대로 왕복합니다(`tests/core/test_dsn.py`, service-hardening ADR-004).
- **라우팅** 판별(`_text_is_write`)과 읽기 세션의 **차단** 판별(`_text_is_readable`)은 방향이 반대인
  별개지만 같은 괄호 깊이 0 스캐너(`_depth0_words`)를 씁니다. 둘 다 `WITH … UPDATE/DELETE` 를
  잡습니다(ADR-036). 잠금 읽기도 같은 `_LOCKING_READ` 정규식 하나로 판정합니다 — `FOR UPDATE`·`FOR SHARE`·
  `LOCK IN SHARE MODE` 전부입니다. 다만 적용 대상은 다릅니다: 라우팅(`_text_is_write`)은 깊이 0 단어 목록에
  적용해 `WHERE note = 'for share'` 같은 리터럴에 걸리지 않지만(ADR-038), 차단(`_text_is_readable`)은 주석만
  걷어낸 원본 문자열에 적용하므로 그런 리터럴도 거부합니다(fail-closed).
  스캔이 무너지면 라우팅은 writer 로(fail-safe), 차단은 거부로(fail-closed) 기웁니다.
- ORM 잠금 읽기(`with_for_update()`, `read=True` 포함)는 문자열이 아니라 `Select._for_update_arg` 로
  판정합니다(`_is_locking_select`). 라우팅은 writer, 읽기 세션은 거부 — text 의 `FOR UPDATE` 와 같습니다
  (service-hardening ADR-005).
  sticky 는 세션 안의 정책이라 다음 요청의 복제 지연까지 없애지 않습니다.
  읽기 전용 표시는 DB 권한을 대신하지 않으므로 운영에서는 replica 전용 읽기 계정
  (`MYSQL_REPLICA_USER`)을 함께 씁니다.

## 5. 데이터 접근 계약

데이터 접근 방식은 **Repository 계층에서만** 갈라집니다. Dependency 조립·Service·트랜잭션 경계·
응답 검증·OpenAPI 는 같습니다. 만드는 순서는 [DEVELOPMENT §5·§6](./DEVELOPMENT.md#5-orm-워크플로--catalog).

### 5.1 모델 기반 클래스

`app/core/models/models_base.py`

| 클래스 | 컬럼 | 쓰는 곳 |
|---|---|---|
| `UUIDPrimaryKeyMixin` | `id: String(36)` — Python 기본값 `uuid4()` | |
| `CreatedAtMixin` / `UpdatedAtMixin` | `created_at` / `updated_at` (`UTCDateTime` — UTC·마이크로초 저장, 기본값 `timezone_settings.utc_now()`, `updated_at` 은 ORM UPDATE 시 `onupdate`) | |
| `UUIDTimestampModel` | id + created + updated | Post·Reply·SnsPost·User·Product |
| `UUIDCreatedModel` | id + created (불변 기록) | UserAccessLog·SalesOrder |
| `Base` 직접 상속 | 자연키 | SalesDailySnapshot(`sales_date` PK, ADR-012) |

기본값과 `onupdate` 는 **ORM/Core 가 만든 문장에서만** 적용됩니다. Raw DML 은 PK·시간 값을 SQL
바인드로 직접 넣어야 합니다.

### 5.2 ORM — `BaseRepository`

`BaseRepository[ModelT, PrimaryKeyT]`(`PrimaryKeyT` 기본 `str`)의 공개 계약은 8개뿐입니다(ORM-REP-002).

| 메서드 | 동작 |
|---|---|
| `create(data)` | 입력 dict 를 바꾸지 않고 add → flush → refresh |
| `get_by_id(pk)` / `get_by_id_or_raise(pk)` | 없으면 `None` / `NotFoundException` |
| `list(skip, limit)` | 페이지. 기본 정렬 `created_at DESC, <PK> DESC`(created_at 이 없으면 PK 만) — 같은 시각도 순서가 정해지고 offset 페이지가 겹치지 않는다(service-hardening ADR-005). 다른 정렬은 기능 Repository 에서 |
| `count(**filters)` / `exists(pk)` | 개수 / SQL `EXISTS` |
| `update_by_id(pk, data)` / `delete_by_id(pk)` | 없으면 `None` / 삭제 여부 `bool` |

- 모든 경로가 같은 예외 변환을 거칩니다 — 표는 `app/core/repositories/db_errors.py` 의
  `DatabaseErrorTranslator` 하나이고 Raw 계층도 같은 표를 씁니다(service-hardening ADR-008 ②·ADR-022).
  드라이버 오류 코드로 판정합니다(SQLite 는 메시지로 대체):

  | MySQL 코드 / SQLite | 예외 | 응답 |
  |---|---|---|
  | 1062 / `UNIQUE` | `DuplicateException` | 409 `DUPLICATE` |
  | 1048·1364 / `NOT NULL` | `ValidationException` | 422 (필수 값 누락) |
  | 1452 / `FOREIGN KEY` | `ValidationException` | 422 (참조 대상 없음) |
  | 1451 | `ConflictException` | 409 `CONFLICT` (다른 행이 참조 중) |
  | 그 밖 | `DatabaseException` | 500 |

  원본은 chaining 으로 보존하고 **응답 `detail` 에는 모델·연산 이름만** 싣습니다(무결성 위반 메시지에는
  중복된 값 자체가 들어 있습니다). 로그도 예외 타입과 드라이버 코드만 남기고(4xx 는 WARNING, 5xx 는 ERROR),
  엔진은 `hide_parameters=True` 라 예외 문자열 자체에 바인딩 값이 없습니다.
- 기능 Repository 의 추가 쿼리는 `self.db_session.execute()` 대신 `self._execute(statement, "<연산 이름>")`
  로 실행해 같은 변환을 거칩니다(`tests/core/test_db_errors.py` 가 직접 호출을 막습니다).
- eager loading·join·문자열 컬럼명 필터 같은 범용 API 는 두지 않습니다 — 기능 Repository 가
  SQLAlchemy 속성으로 명시적 메서드를 소유합니다(ORM-REP-005).
- 커밋은 하지 않습니다(`flush` 까지). `CRUDBase` 는 `_get`·`_add`·`_delete`·`_flush`·`_refresh`
  primitive 만 가집니다.

### 5.3 Raw SQL — `RawRepositoryBase`

```python
async def fetch_one(statement, params=None, *, query_name) -> RowMapping | None
async def fetch_all(statement, params=None, *, query_name) -> Sequence[RowMapping]
async def fetch_scalar(statement, params=None, *, query_name) -> Any
async def execute(statement, params=None, *, query_name) -> int     # 영향 행 수, 커밋 없음
```

- 입력은 `text()` 로 만든 `TextClause` 와 **named bind parameter** 입니다.
- 바인딩할 수 없는 식별자(컬럼명·정렬 방향)는 `resolve_identifier()`·`resolve_sort_direction()` 으로
  코드가 가진 허용 목록에서만 고릅니다(RAW-REP-004). 허용 밖이면 `ValueError`.
- `query_name`(예: `sales_report.daily_sales`)은 필수 키워드입니다. 로그에는 이름·소요 시간·성공/실패만
  남기고 **SQL 본문과 파라미터는 남기지 않습니다**(NFR-004). `SQLAlchemyError` 는 ORM 과 같은 표(§5.2)로
  바뀌고 `detail` 은 `{"query": query_name}` 입니다 — 중복 INSERT 는 409, 그 밖의 실패는 500.
- 결과 `RowMapping` 은 Service 가 `dict(row)` 로 바꿔 Pydantic DTO 로 검증합니다(RAW-REP-005).

### 5.4 두 방식의 비교

| | ORM (`BaseRepository`) | Raw (`RawRepositoryBase`) |
|---|---|---|
| 언제 | 엔티티 생명주기(CRUD)·관계 적재 | 집계·리포트·집합 연산(`INSERT … SELECT`)·방언 특화 구문 |
| 반환 | ORM 인스턴스 → `from_attributes=True` DTO | `RowMapping` → 명시 변환 후 DTO |
| 예시 | `app/features/catalog/` | `app/features/reports/` |

두 Base 는 **상속 관계가 없습니다**(AR-003, 게이트 INV-5). Raw 가 ORM Base 를 상속하면 매핑되지 않은
결과에 identity map·flush 의미가 딸려 옵니다. 집계 **결과** 전용 ORM 모델은 만들지 않지만, 이 프로젝트가
생명주기를 소유하는 **원본 테이블**(`sales_orders`)은 모델로 둡니다 — metadata 에 없으면 Alembic 이
지워야 할 테이블로 봅니다.

## 6. 설정

### 6.1 로딩 규칙

- `config.py` 의 9개 `BaseSettings` 는 각각 `env_file=".env"`, `extra="ignore"` 로 자기 필드를 읽습니다.
  우선순위는 **프로세스 환경 변수 → 작업 디렉터리의 `.env` → 코드 기본값**입니다.
- `get_*_settings()` 는 `@lru_cache` 이고, 파일 끝의 `app_settings = get_app_settings()` 등이 import 시점에
  전역 객체를 만듭니다. 실행 중 `.env` 를 바꿔도 반영되지 않습니다. 테스트에서 캐시만 비워도 이미 가져간
  전역 참조는 그대로이므로 새 프로세스나 monkeypatch 로 확인합니다.
- 타입 오류·validator 위반은 `config` import 자체를 실패시켜 lifespan 전에 기동을 막습니다.
  validator: 복제 설정 모순·replica 주소 형식(`DatabaseSettings`), `CORS_ALLOW_ORIGINS=["*"]` +
  `CORS_ALLOW_CREDENTIALS=true`(`CORSSettings`), 관리 세션 미사용 만료 > 절대 만료(`SessionSettings`).
- 전역 객체를 만든 뒤 파일 끝에서 설정 검사 세 개가 차례로 돕니다. 모두 `RuntimeError` 로 `config` import 를
  실패시키고, 메시지에는 설정 이름만 나옵니다. `ENV=test` 는 모두 건너뜁니다(pytest 가 지정).
  1. `validate_env_source()` — **출처**(ADR-045 ①). `.env` 가 없으면 `ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE`
     (`REQUIRED_WITHOUT_ENV_FILE`)가 환경 변수로 모두 있어야 합니다. 컨테이너 주입은 통과하고, 아무것도 없으면 멈춥니다.
  2. `validate_no_legacy_admin()` — **예전 이름**(admin-login ADR-005). `ADMIN`(true=켬)은 뜻이 뒤집힌 `ADMIN_DISABLED`(true=끔)로
     바뀌었으므로, 환경 변수나 `.env` 에 `ADMIN` 이 남아 있으면(대소문자 무시) 조용히 무시하지 않고 멈춥니다.
  3. `validate_deployment_safety()` — **내용**. 위반을 모두 모아 한 번에 알립니다.
     - test 외 모든 ENV(ADR-027·030·045 ②): `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY`·`MYSQL_PASSWORD`
       가 예시 값(`change-this` 포함·`your-` 시작·빈 값), 비밀 키 3종이 32자 미만, access 와 refresh 가 같음.
       `REDIS_PASSWORD` 는 **값이 있을 때만** 예시 값인지 봅니다 — 비밀번호 없는 사설망 Redis 가 정당한 구성이라 빈 값은 통과합니다.
     - staging/production 만(ADR-028): `DEBUG=true`, `LOG_LEVEL=DEBUG`. 관리 화면을 켠 배포는 막지 않습니다 — 슈퍼유저
       로그인이 붙어 ADR-045 ③ 의 확인 플래그를 없앴습니다(admin-login ADR-004).
  예시 값 판정은 `is_placeholder_secret()` 하나가 맡습니다(`tests/core/test_deployment_safety.py`). `SERVER_HOST` 등
  그 밖의 운영 조합은 막지 않습니다(C-8).
- 환경 변수를 직접 읽는 곳은 `config.py` 뿐입니다(`tests/core/test_settings_contract.py`).

### 6.2 설정 클래스와 소비 지점

| 전역 객체 | 소비 지점 |
|---|---|
| `timezone_settings` | 로그 시각(`TzFormatter`), 모델 시간 기본값, Celery `timezone`, 스냅샷 `generated_at` |
| `app_settings` | FastAPI 메타데이터, `DEBUG`(문서·DDL·로그 레벨 기본값·500 detail·reload), `ADMIN_DISABLED`(관리 화면 마운트 여부), `ENV`(로그 구성·관리 세션 쿠키 `Secure`), `SERVER_HOST/PORT` |
| `db_settings` | DSN·라우팅·replica(`session.py`), `ALEMBIC_URL`(`migrations/env.py`) |
| `cors_settings` | `CustomCORSMiddleware.configure_cors()` |
| `log_settings` | `build_dictconfig()` — `LOG_LEVEL`·`LOG_APP_LEVELS`·`LOG_CONSOLE_LEVEL`·`LOG_SQL_ECHO_ENABLED`, `console_formatter_kwargs()`·`file_formatter_kwargs()`(`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`), `console_enabled()`(`LOG_CONSOLE_ENABLED`), `setup.attach_log_files()`(`LOG_FILE_*`·`LOG_DIR`·`LOG_MAX_SIZE_MB`·`LOG_RETENTION_DAYS`) — §9.2 |
| `middleware_settings` | `UserInfoMiddleware` 활성·제외 규칙 |
| `redis_settings` | startup ping client(`REDIS_URL`), Celery broker/backend |
| `jwt_settings` | `app/core/security/dependencies.py` 의 provider(`TokenService`·`RefreshTokenStore` 생성), `app/features/auth/dependencies/auth_dependencies.py` 의 레이트 리밋 한도, 관리 화면 로그인 레이트 리밋(`AdminAuthBackend.login`, §12) |
| `session_settings` | `SESSION_SECRET_KEY` — 관리 세션 ID → Redis 키 HMAC(`new_admin_session_store`, §12). `ADMIN_SESSION_MAX_AGE_SECONDS`·`ADMIN_SESSION_IDLE_SECONDS` — 관리 세션 절대·미사용 만료(§12, 기본값은 README [세션·토큰 만료](../../README.md#세션토큰-만료)). `SESSION_COOKIE_NAME` — 접속 로그의 `session_id` 기록(§10, 인증에 쓰지 않음). |

읽는 코드가 없는 필드는 `tests/core/test_settings_usage.py` 가 막습니다 — 예외 목록은 없습니다.
메일(`SMTP_*`)·업로드(`UPLOAD_*`)·`SESSION_EXPIRE_SECONDS`(config-cleanup)와 `API_VERSION`·`ApiSettings`
(config-cleanup-2)는 읽는 코드가 없어 지웠고, 옛 `.env` 줄은 `extra="ignore"` 로 무시됩니다.

## 7. 기동

### 7.1 import 시점

`uv run python main.py` 는 `main` 을 import 해 조립한 뒤 `run_server()` 가 `uvicorn.run("main:app", …)` 을
부르고, `uvicorn main:app` 은 uvicorn 이 `main` 을 import 합니다. 어느 쪽이든 순서는 같습니다.

1. `config` — 설정 생성·검증, 배포 안전 검사(`validate_deployment_safety()`, §6.1)
2. `get_logger()` 첫 호출 → `configure_logging()` — dictConfig 적용, listener 시작, `atexit`·신호 훅 등록(§9.5)
3. `app/core/db/session.py` — 엔진·세션 팩토리 생성, 라우팅 구성 로그
4. `app.features` 각 패키지 — 라우터·모델 import, `home` 의 sink 등록
5. `FastAPI(...)` → 미들웨어 → 예외 핸들러 → `include_router` × 8 → health/ready/`/docs` → `ADMIN_DISABLED` 가 아니면 SQLAdmin 마운트(인증 백엔드·세션 미들웨어 포함) → `AccessPolicyGuard().verify(app)`(접근 수준 검사 — 위반이면 import 실패, §11.2)

reload·다중 worker 는 새 프로세스마다 이 과정을 반복하므로 Redis client·DB 풀·listener 는 프로세스마다
따로 있습니다.

### 7.2 lifespan 진입

```python
# main.py
@asynccontextmanager
async def lifespan(app):
    async with manage_application_resources(app):
        yield

# app/core/resources.py
resources = ApplicationResources()          # model_modules · table_count · tables_created
app.state.resources = resources
async with _log_queue(), _database(app), _redis(app), _background_tasks():
    await _prepare_database(resources)
    yield resources
```

| 단계 | 하는 일 |
|---|---|
| `_log_queue()` 진입 | 없음 (종료 때 flush 담당) |
| `_database(app)` 진입 | 없음 (엔진은 이미 있다 — 종료 때 dispose 담당) |
| `_redis(app)` 진입 | `Redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)` → `await client.ping()` → `ensure_redis_version(client)`(`INFO server` 의 `redis_version` ≥ `REDIS_MIN_VERSION`=6.2.0, 아래 표). 성공해야 `app.state.redis = client`. **끄는 설정 없음** |
| `_background_tasks()` 진입 | 없음 (종료 때 drain 담당) |
| `_prepare_database()` | `import_all_models()` → `len(Base.metadata.tables)`. 0개면 DB 접속 안 함 / `DEBUG=false` 면 DDL 생략 / `DEBUG=true` 면 `create_db_tables(import_models=False)` — writer `engine.begin()` 안에서 `create_all`, 30초 guard |
| `yield` | 서버가 요청을 받기 시작한다 |

`app.state.redis` 의 client 는 주입 provider `get_redis(request)`(`app/core/redis.py`) 하나로만 꺼냅니다 —
client 가 없으면 `ServiceUnavailableException`(503). 라우트·의존성이 `app.state` 를 직접 읽지 않으므로 테스트는
`dependency_overrides[get_redis]` 로 바꿔 끼웁니다(service-hardening ADR-011). `create_all` 은 없는 테이블만 만들며 컬럼 변경·삭제·데이터 이동을 하지 않습니다.
여러 worker 가 `DEBUG=true` 로 동시에 뜨면 DDL 도 동시에 시도되므로 운영은 `DEBUG=false` + Alembic 입니다.

**Redis 최소 버전 6.2** — `app/core/redis.py` 의 `REDIS_MIN_VERSION` 이 정본입니다. 코드가 실제로 보내는 명령 중
가장 높은 요구치로 정합니다(log-redaction ADR-003). `EXPIRE … NX`(7.0)·Lua 는 쓰지 않습니다 — 쓰게 되면 상수를 올리고,
`tests/core/test_redis_version.py` 의 계약 테스트가 소스의 호출과 상수를 맞춰 봅니다.

| 명령 | 도입 버전 | 사용처 |
|---|---|---|
| `GETDEL` | 6.2.0 | `RefreshTokenStore.consume`(refresh 회전) |
| `SET key v EX n NX` | 2.6.12 | `RateLimiter.hit`(첫 hit 에만 만료) |
| `MULTI`·`INCR`·`TTL`·`EXPIRE`·`SADD`·`SMEMBERS`·`EXISTS`·`DEL`·`PING`·`INFO` | 2.6 이하 | 레이트 리밋·회전 저장소·startup·`/ready` |

보고된 버전이 낮으면 `RedisVersionError` 로 기동을 멈춥니다(Redis 필수 정책과 같다). `INFO` 를 막아 둔 관리형 Redis·
`INFO` 를 모르는 fakeredis 처럼 버전을 알 수 없으면 WARNING 을 남기고 계속합니다.

### 7.3 기동 실패 경로

| 실패 지점 | 결과 |
|---|---|
| 설정 타입·validator·설정 검사(`.env` 출처, 예전 `ADMIN` 잔존, 예시 비밀값, 배포 환경 debug) | `config` import 실패 — lifespan 전 |
| 접근 수준 선언 위반(선언 없음·수준 둘·쓰기에 `Public`·조회에 `PublicWrite`) | `AccessPolicyError`(위반 전체 목록) — `main` import 실패, lifespan 전(§11.2) |
| Redis ping (연결·인증·timeout) | `[startup] Redis 연결 실패: <오류 타입>` ERROR 후 재전파. background 컨텍스트에는 아직 들어가지 않았으므로 drain 없이 **Redis `aclose()` → DB dispose(“자원 해제 완료” 로그) → 로그 flush** 만 실행. `app.state.redis`·`app.state.resources` 는 `None` (`tests/core/test_resources.py::test_redis_connection_failure_stops_startup_and_cleans_up`) |
| Redis 버전 6.2 미만 | `RedisVersionError`(`Redis <버전> 는 지원하지 않는다 — 최소 6.2.0 …`) 전파, 정리는 ping 실패와 같다 (`tests/core/test_redis_version.py`) |
| 개발용 DDL (MySQL 없음 등) | 네 컨텍스트가 모두 역순으로 정리된 뒤 예외 전파 |
| 공통 | uvicorn 이 `Application startup failed. Exiting.` 과 traceback 을 남기고 종료. listener 가 프로세스 소유라 이 로그가 유실되지 않는다(§9.5) |

## 8. 종료

### 8.1 순서와 강제 방식

순서를 강제하는 코드는 없습니다. **중첩 컨텍스트가 곧 순서**이고, 파이썬이 역순으로 풉니다(ADR-017).

```
uvicorn: 신규 요청 수신 중단 → 진행 중 요청 처리 → lifespan shutdown
① _background_tasks  "[shutdown] 애플리케이션 요청 처리 자원 해제 시작" → 접속 로그 태스크 drain
② _redis             app.state.redis = None → client.aclose()
③ _database          dispose_engine() — writer·replica·background 를 gather 로 동시에
                     → app.state.resources = None → "[shutdown] 애플리케이션 요청 처리 자원 해제 완료"
④ _log_queue         flush_log_queue() — 쌓인 로그가 다 쓰일 때까지 **기다린다**(멈추지 않는다)
uvicorn: "Application shutdown complete" · "Finished server process"
프로세스 종료: atexit / 신호 핸들러 → stop_log_listener()  ("[log-lifecycle] stop 완료", stderr 직접)
```

- ①이 ②③보다 먼저인 이유: 외부 자원을 쓰는 주체(background task)가 살아 있는데 client·풀을 닫으면
  연결이 강제로 끊깁니다.
- ④가 마지막인 이유: 앞 단계가 남긴 로그까지 내보내야 합니다.
- **이 중첩을 평평한 `finally` 안의 연속 `await` 로 되돌리지 마세요.** `asyncio.CancelledError` 는
  `BaseException` 이라 `_run_cleanup()` 의 `except Exception` 을 통과하고, 연속 `await` 였을 때는 첫
  단계에서 취소를 맞으면 **뒤 단계가 통째로 건너뛰어졌습니다**(DB 풀이 닫히지 않았다). 중첩 컨텍스트는
  취소가 전파되어도 바깥 `__aexit__` 를 시도합니다.
  회귀 테스트: `tests/core/test_resources.py::test_manager_cancellation_still_runs_remaining_cleanup`.
- 요청별 `AsyncSession` 은 이 사슬 밖에서 세션 의존성이 닫습니다. Celery worker 의 연결은 worker 가
  닫습니다(AR-006, §13). 종료에서 테이블을 drop 하지 않습니다.

### 8.2 시간 예산

| 단계 | 예산 | 정의 |
|---|---|---|
| background drain | 5초 (완료 대기는 4초 = `DRAIN_WAIT_RATIO` 0.8, 남는 1초는 취소한 태스크 회수) | `resources.py` |
| Redis close | 5초 | `resources.py` |
| DB dispose | 10초 | `resources.py` |
| 로그 큐 flush | 2초 | `LOG_FLUSH_TIMEOUT_SECONDS` |
| listener 정지(프로세스 종료 훅) | sentinel 적재 2초 + join 5초 | `queue_handler.py` |

- drain 이 자기 guard 보다 **짧게** 기다리는 이유: 같은 값을 주면 취소 직후 바깥 guard 가 끊어, 취소된
  태스크의 `finally`(세션 rollback·close)가 실행되지 못합니다.
- `SHUTDOWN_TOTAL_TIMEOUT_SECONDS=20.0` 은 **전체를 감싸는 timeout 이 아닙니다.** 테스트
  (`test_shutdown_timeout_budget_fits_total`)는 background·DB·flush 합(17초)이 20 이하인지만 봅니다.
  Redis 를 더하면 lifespan 정리만 최대 약 22초, listener 정지까지 약 29초이며 진행 중 요청 대기는 별도입니다.
  컨테이너 종료 유예(Kubernetes `terminationGracePeriodSeconds`, `docker stop -t`)는 이보다 길게 잡습니다.
- Celery worker 정리는 별도 10초입니다(§13).

### 8.3 오류·취소 전파 계약

| 상황 | 동작 |
|---|---|
| cleanup 의 일반 `Exception`·timeout | `_run_cleanup()` 이 자원명과 함께 기록하고 삼킨다 → 다음 단계 계속, 원래 예외 보존 |
| lifespan 취소(`CancelledError`) | 삼키지 않는다. 중첩 구조가 남은 정리를 시도한 뒤 호출자에게 재전파 |
| DB 엔진 일부 dispose 실패 | `asyncio.gather(return_exceptions=True)` 로 전부 시도, 실패는 엔진 이름과 기록, 상위로 던지지 않음. `dispose_engine()` 은 인자를 받지 않는다(Celery 가 인자 없이 부름) |
| background 태스크 예외 | done callback 이 회수해 ERROR 로 남김(취소는 오류로 보지 않음) |
| 로그 flush 초과 | 경고만 남기고 종료 계속 |
| listener 정지 실패 | 참조를 유지해 재시도 가능, 상태는 queue 를 거치지 않고 `sys.__stderr__` 에 기록 |

### 8.4 보장하지 않는 것

- **SIGKILL**(`kill -9`, 유예 초과) — 어떤 정리도 실행되지 않습니다. DB 연결은 서버 측 timeout 이 정리하고,
  큐에 남은 로그는 사라집니다.
- **uvicorn force exit**(Ctrl+C 두 번) — uvicorn 이 `lifespan.shutdown()` 을 호출하지 않습니다.
- uvicorn 의 graceful shutdown timeout 초과는 **요청 task** 를 취소하지 lifespan 을 취소하지 않습니다.
  lifespan 취소는 테스트 하네스·다른 ASGI 서버·앱을 감싸는 코드에서 일어나며, 그 경로가 §8.1 의 이유입니다.
- 반복 취소·무응답 I/O 에서 모든 정리의 성공, 다중 worker(gunicorn 등)·POSIX 실경로의 신호 처리는
  실행 검증하지 않았습니다(CRP residual-risk 참고).

## 9. 로깅

관련 코드: `app/utils/logs/`, `app/core/resources.py`, `main.py` · 결정: NFR-009, ADR-017·018·020·021·022·023.
이 영역의 결함은 lifespan 바깥(프로세스 종료·신호·uvicorn 내부)에 살아서 단위 테스트로는 보이지 않습니다.
실제로 이 구조를 고치기 전 391개 테스트가 모두 초록이었지만 결함 12건을 하나도 잡지 못했습니다.
"단순하게 정리한다" 는 수정이 로그를 조용히 없앤 적이 여러 번 있으니 이 절을 먼저 읽으세요.

### 9.1 큐를 거치는 이유와 포화 정책

stdout·stderr 쓰기는 느린 동기 I/O 라 요청 스레드에서 하면 event loop 전체가 멈춥니다. 그래서:

```
요청 코드 ─ put_nowait ─▶ [bounded queue 10,000] ─▶ QueueListener 스레드 ─▶ stdout / stderr / 파일(LOG_FILE_ENABLED)
```

root 로거에는 `BoundedQueueHandler` 하나만 붙고, 필터(`SqlNoiseFilter`, `RedactingFilter`, `ContextFilter`, `AppLevelFilter`)는
**적재 전에 요청 스레드에서** 돕니다(`ContextFilter` 는 호출 스택에서 클래스명을 뽑으므로 listener 스레드에서는 늦습니다).
파일 쓰기·회전도 listener 스레드가 하므로 요청 event loop 를 막지 않습니다.

> **`logger.info()` 가 반환됐다고 출력된 것은 아닙니다.** 임계값·필터에서 걸러질 수 있고, 큐가 차면
> 버려질 수 있으며, 큐에 들어갔더라도 listener 가 쓰기 전에 프로세스가 죽으면 사라집니다(listener 는
> daemon 스레드입니다). 아래 설계는 전부 이 성질에서 나옵니다.

| 큐가 가득 찼을 때 | 처리 |
|---|---|
| DEBUG·INFO·WARNING | 버리고 `dropped` 증가, 5초에 한 번 `[log-fallback] log queue full — dropped N record(s)` |
| ERROR·CRITICAL | logging API 를 다시 타지 않고 `sys.stderr` 에 최소 포맷으로 직접 기록, `fallbacks` 증가 |

producer 를 막는 선택지는 쓰지 않습니다 — 로그 때문에 API 가 느려지는 것이 로그 몇 줄을 잃는 것보다
나쁩니다. 관측 지표: `BoundedQueueHandler.dropped`/`fallbacks`,
`access_log_tasks.dropped`/`cancelled`.

### 9.2 출력 구성과 포맷

`build_dictconfig()`(`app/utils/logs/config.py`)가 유일한 설정 지점이며 `ENV` 로 갈립니다.

| ENV | 출력 | 시각 |
|---|---|---|
| `development` | stdout | 설정 타임존(`TIME_ZONE`), 밀리초 포함 |
| `test` | stdout | 설정 타임존 |
| `staging`·`production` | stdout + **ERROR 이상은 stderr 에도** | UTC |

기본은 파일이 없고 저장·검색·rotation 은 Docker·Kubernetes·수집 agent 가 맡습니다. `LOG_FILE_ENABLED=true` 면
설정 로드 직후(`configure_logging()`, 첫 `get_logger()`) 실행 프로그램 `sys.argv[0]` 으로 프로세스 종류를 정해
`setup.attach_log_files()` 로 listener 에 파일 핸들러를 더합니다(`setup.entry_process()`) — `python main.py`·`uvicorn`
(`-m uvicorn` 포함)은 `app.log`·`error.log`, `celery`(`-m celery`, worker·beat)는 `celery.log`·`celery-error.log`.
그래서 import 중에 찍히는 줄(`[database] 라우팅 구성` 등)도 파일에 남습니다. 그 밖의 프로그램(pytest·alembic·스크립트)은
파일을 열지 않고, 진입점의 호출(`main.py` import, Celery `after_setup_logger` 수신자)이 그 판정을 못 하는 실행을
덮습니다 — 여러 번 불러도 한 번만 붙습니다(integration-e2e ADR-011 이 logging-overhaul ADR-002 의 "진입점이 정한다"를
대체). 에러 파일도 프로세스별로 나눈 이유는 웹과 worker 가 한 파일을 회전시키지 않게 하려는 것입니다
(logging-overhaul ADR-002). 핸들러는 `DailySizeRotatingFileHandler`(`app/utils/logs/handlers.py`) 하나입니다 —
매일 자정(포매터와 같은 시간대)에 `app.log.YYYY-MM-DD`, 하루 안에서 `LOG_MAX_SIZE_MB` 초과면 `.1`·`.2`…, 교체 때
`LOG_RETENTION_DAYS` 보다 오래된 날짜 파일(분할 포함)을 지웁니다. 이미 있는 이름은 덮지 않고 다음 번호를 씁니다.
`uvicorn --workers` 2 이상·Celery prefork 처럼 여러 프로세스가 같은 파일을 쓰면 회전이 엇갈리므로 파일을 끄고
콘솔 + 수집기를 씁니다(README "여러 워커 주의").

포맷은 `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`(`style="{"`), 시각은 `LOG_DATE_FORMAT`(strftime)이 정하고
`console_formatter_kwargs()`·`file_formatter_kwargs()` 가 `TzFormatter` 에 넘깁니다. 기본값(= `LOG_FORMAT`)은 다음과 같습니다:

```
[{asctime} {tzname}] {levelname:5} [app={appname}] [{module}:{classname}:{funcName}:{lineno}] {message}
[2026-09-17 16:29:05.704 KST] INFO  [app=core] [session:-:<module>:166] [database] 라우팅 구성: {...}
```

- 필드는 `LogRecord` 속성과 `TzFormatter` 가 채우는 `{tzname}`·`{appname}`·`{classname}`. 설정 로드 때 샘플
  레코드를 한 번 포맷해 보고, 모르는 필드·괄호 불일치·잘못된 서식 지정자·빈 날짜 형식이면 기동을 멈춥니다.
  필수 필드(`config.LOG_REQUIRED_FIELDS` — `{asctime}`·`{levelname}`·`{appname}`·`{module}`·`{classname}`·
  `{funcName}`·`{message}`)가 하나라도 빠져도 빠진 목록과 함께 기동을 멈춥니다.
- 시각: `development` 는 날짜 형식 뒤에 밀리초(`.704`)가 붙고, `staging`·`production` 은 UTC 로 렌더합니다.
- 비밀값 마스킹(§9.4.1)은 queue 적재 전 필터라 포맷과 무관합니다.
- `LOG_CONSOLE_ENABLED=false` 면 콘솔(stdout/stderr) 핸들러를 하나도 만들지 않습니다. 판단은
  `console_enabled()` 한 곳이고, 앱 dictConfig 가 그것을 보며 uvicorn CLI·Celery 의 콘솔 핸들러는 공유 queue 로
  바뀌어 같은 결정을 따릅니다. 파일 출력(`LOG_FILE_ENABLED`·Celery `--logfile`)은 남습니다. 파일도 꺼져 있으면
  앱 로그는 버려지고, 기동 때 stderr 에 `[logging] 경고: LOG_CONSOLE_ENABLED=false …` 한 줄이 나옵니다.
- **모든 실행 경로가 같은 형식입니다**(logging-overhaul L1). `uvicorn main:app`(·`fastapi dev`) CLI 와 Celery
  worker 는 자기 콘솔 핸들러를 다는데, `setup.adopt_foreign_handlers()` 가 그것을 떼고 공유 queue 핸들러를 답니다 —
  CLI 는 `configure_logging()` 이 uvicorn 로거 3종에, Celery 는 `after_setup_logger`·`after_setup_task_logger`
  수신자가. 핸들러가 없던 로거(`--no-access-log`)는 그대로 두고, Celery `--logfile` 파일 핸들러는 남긴 채
  `LOG_FILE_FORMAT` 과 같은 필터만 입힙니다. uvicorn 접속 줄은 요청 줄(`client - "GET /p HTTP/1.1" 200`)을
  `{message}` 로 담습니다 — uvicorn `AccessFormatter` 가 만드는 상태 문구(`OK`)는 빠집니다.

- `app=` 은 판별 함수 하나(`filters._app_from_path(pathname, logger_name)`)가 정합니다. 우리 코드는 **소스
  경로**로: 기능명(`app/features/<name>/`), `core`·`celery`·`utils`·`migrations`, 그 밖의 저장소 코드는 `app`.
  저장소 밖 코드는 **로거 이름**으로: `celery.*`·`kombu.*` → `celery`, `uvicorn.*` → `uvicorn`, `sqlalchemy.*` →
  `sqlalchemy`, `alembic.*` → `alembic`, 그 밖은 `ext`. `ContextFilter` 를 거치지 않은 줄도 `TzFormatter` 가 같은
  함수로 헤더를 채웁니다.
- `classname` 은 `LoggerMixin`(`self.log`)이면 주입값, 아니면 호출 프레임의 `self`/`cls`, 없으면 `-`.
- 앱별 로거를 dictConfig 에 등록하지 않습니다(charter §2-4, 가드 `test_dictconfig_has_no_per_app_loggers`).
  새 기능이 로깅 설정을 건드릴 일이 없습니다. 헤더별 레벨은 로거 대신 필터(`AppLevelFilter`, §9.3)로 줍니다.

### 9.3 레벨이 정해지는 방식

root 와 console 핸들러의 임계값이 각각 정해지고, 둘 다 통과해야 출력됩니다.

- root = `LOG_LEVEL` 이 있으면 그 값, 없으면 `DEBUG=true` → DEBUG, false → INFO
- console = `LOG_CONSOLE_LEVEL` 이 있으면 그 값, 없으면 같은 규칙

| DEBUG | LOG_LEVEL / LOG_CONSOLE_LEVEL | 보이는 것 |
|---|---|---|
| false | 미설정 / 미설정 | INFO 이상 |
| true | 미설정 / 미설정 | DEBUG 이상 |
| false | DEBUG / DEBUG | DEBUG 이상 (앱은 여전히 DEBUG=false 모드) |
| true | WARNING / WARNING | WARNING 이상 — startup INFO 도 안 보인다 |
| 무관 | INFO / DEBUG | INFO 이상 (root 가 DEBUG 를 먼저 막는다) |
| 무관 | DEBUG / INFO | INFO 이상 |

`[startup] 애플리케이션 자원 초기화 시작 (DEBUG=%s)` 의 `DEBUG` 는 표시값일 뿐 출력 조건이 아닙니다.
uvicorn 로거 레벨은 `python main.py` 경로에서 root 와 같은 규칙(`LOG_LEVEL`/`DEBUG`)을 따릅니다.

**헤더별 레벨 `LOG_APP_LEVELS`**(`"blog=DEBUG,celery=INFO,sqlalchemy=WARNING"`)는 Django
`LOGGING["loggers"][name]["level"]` 자리입니다. root·queue·uvicorn 로거 레벨은 `LOG_LEVEL` 과 이 값들 중
**최솟값**(`config.lowest_level()`)으로 내려 레코드가 필터까지 오게 하고, queue 의 `ContextFilter` 바로 뒤
`AppLevelFilter` 가 헤더별 최소 레벨(지정 없으면 `LOG_LEVEL`)보다 낮은 레코드를 버립니다. 잘못된 형식·레벨은
기동 오류, 모르는 헤더는 WARNING 한 줄입니다. 파일은 `LOG_FILE_LEVEL`(없으면 같은 규칙), 에러 파일은 ERROR 고정.
Celery worker 의 root 레벨은 `celery -l` 이 정합니다.

### 9.4 SQL 로그 차단

`DEBUG=true` 면 유효 레벨이 DEBUG 라 SQLAlchemy·드라이버가 실행 SQL 과 **바인딩 값**(비밀번호 해시·토큰·
검색어)을 찍습니다. `SqlNoiseFilter` 가 `sqlalchemy.engine`·`sqlalchemy.pool`·`aiosqlite`·`aiomysql`·
`asyncmy`·`pymysql` 로거의 **WARNING 미만**을 막습니다(장애는 계속 보입니다). SQL 을 봐야 할 때만
`LOG_SQL_ECHO_ENABLED=true` 로 엽니다(NFR-001, `tests/core/test_sql_logging_leak.py`).

### 9.4.1 비밀값 마스킹 — traceback 포함

`RedactingFilter`(`app/utils/logs/filters.py`)가 메시지·traceback·`stack_info` 의 비밀값을 `***` 로 가립니다.
규칙의 정본은 같은 파일의 `redact()` 하나이고 DEBUG 500 응답의 `detail` 도 이것을 씁니다(log-redaction ADR-001).

| 가리는 형태 | 예 |
|---|---|
| DSN 계정(사용자명·비밀번호) | `mysql+asyncmy://***:***@h/db` · `redis://:***@cache:6379/0` |
| 설정 비밀값 원문(`config.LOG_SECRET_SETTINGS` — DB 계정·비밀번호, Redis 비밀번호, JWT·세션 키) | 어디에 나오든 `***`. 4글자 미만 값은 `user=`·`username=` 형태에서만 |
| `Authorization` 값·`Bearer` 토큰 | `Authorization: Bearer ***` |
| 이름에 `password`·`passwd`·`pwd`·`secret`·`token`·`api_key` 가 든 키의 값 | `password=***` · `"refresh_token": "***"` |

traceback 은 보통 포매터가 나중에 `exc_info` 에서 만들어 필터가 볼 수 없습니다. 그래서 필터가 `exc_info` 를
미리 `exc_text` 로 포맷해 가려 둡니다(포매터는 `exc_text` 가 있으면 다시 만들지 않는다). `exc_info` 는 남겨
예외 타입·체인·파일·줄은 그대로 보입니다. 메시지는 가릴 것이 있을 때만 바꿉니다. 비밀값이 인자 하나 안에만 있으면
그 인자만 가리고 `args` 모양을 지킵니다 — `args` 를 직접 푸는 uvicorn access 포매터가 깨져 접속 줄이 사라지지 않게
(config-cleanup F-008). 틀과 인자에 걸치면(`"password=%s"`) 합친 문자열로 바꿉니다.

| 출력 경로 | 붙는 곳 |
|---|---|
| 앱·SQLAlchemy·`python main.py` 의 uvicorn 로거 | root 의 queue 핸들러 필터 `redact` — stdout·stderr·큐 포화 fallback 모두 |
| `uvicorn main:app` CLI 의 `uvicorn`·`uvicorn.error`·`uvicorn.access` | 콘솔 핸들러가 공유 queue 로 바뀌어 queue 필터를 탄다. `configure_logging()` 이 그 **로거**에도 붙여 둔다. 접속 줄의 `?token=…` 도 가려지고 요청 줄은 남는다 |
| Celery worker | 콘솔은 공유 queue, `--logfile` 파일 핸들러에는 `after_setup_logger`·`after_setup_task_logger` 수신자가 같은 필터를 붙인다(`app/celery/lifecycle.py`) |
| 파일(`LOG_FILE_ENABLED`) | listener 의 출력처라 queue 필터를 이미 거친 레코드만 쓴다 |

형태로 찾는 규칙이라 모든 비밀을 잡지는 못합니다 — 비밀값을 로그·예외 메시지에 넣지 않는 것이 먼저입니다
(`tests/utils/test_log_redaction.py`).

### 9.5 listener 수명 — 프로세스가 소유한다

listener 는 FastAPI lifespan 보다 **오래** 살아야 합니다. lifespan 에서 멈추면 그 뒤에 uvicorn 이 남기는
최종 로그와 startup 실패 traceback 이 소비자 없는 큐에 갇힙니다 — 실제 증상은 "DB 가 꺼진 채 서버를
띄우면 오류 원인이 한 글자도 안 나온다"(14줄 출력, traceback 0건)였습니다(ADR-018).

| 장치 | 위치 | 하는 일 |
|---|---|---|
| 시작 | `configure_logging()` | dictConfig 가 만든 `handler.listener`(`TimeoutSentinelListener`)를 시작 — Celery·Alembic·테스트처럼 lifespan 이 없는 프로세스에서도 로그가 나간다 |
| `atexit` 훅 | 같은 곳, 프로세스당 1회 | 정상 종료·`sys.exit`·Ctrl+C(`SIGINT` → `KeyboardInterrupt`)에서 `stop_log_listener()` |
| `SIGTERM`·`SIGBREAK` 핸들러 | 같은 곳, main thread 에서만 | 이 신호들은 기본 동작이 즉시 종료라 `atexit` 이 돌지 않는다(`docker stop`·Kubernetes·Windows Ctrl+Break). 로그를 비우고 → `SIG_DFL` 로 되돌려 → 같은 신호를 다시 올린다. **신호를 삼키지 않는다**(삼키면 컨테이너가 안 죽어 SIGKILL 까지 간다). 이미 다른 핸들러가 있으면 건드리지 않는다(gunicorn·Celery) |
| `SIGINT` | — | 일부러 건드리지 않는다 — `KeyboardInterrupt` 를 기대하는 pytest·REPL·디버거가 달라진다 |
| lifespan 끝의 flush | `_log_queue()` → `flush_log_queue()` | 멈추지 않고 `unfinished_tasks == 0` 을 2초까지 기다린다(ADR-023). `Queue.join()` 과 같은 조건이지만 timeout 이 있어야 listener 가 죽었을 때 매달리지 않는다 |
| 포화 시 정지 | `TimeoutSentinelListener` | `enqueue_sentinel()` 오버라이드로 sentinel 적재에 2초 예산(stdlib 가 지정한 확장 지점, ADR-021), `stop()` join 에 5초 예산 |
| fork 후 재시작 | `restart_log_listener()` | Celery prefork 자식에서 스레드를 다시 세운다(§13) |

⚠️ **`app/core/resources.py` 에 listener 정지 코드를 넣지 마세요.** 기다리기(flush)는 되지만 멈추기(stop)는
프로세스의 몫입니다. `stop_log_listener_async()` 는 공개돼 있지만 lifespan 은 호출하지 않습니다.

### 9.6 실행 명령에 따른 차이

| | `uv run python main.py` | `uv run uvicorn main:app` |
|---|---|---|
| uvicorn 로그 | 프로젝트 포맷 + `[app=uvicorn]`, 같은 큐 | 같다 — 앱 import 때 uvicorn 콘솔 핸들러를 공유 큐로 바꾼다(§9.2). 그 전에 나온 줄은 없다(uvicorn 은 앱을 import 한 뒤 `Started server process` 를 쓴다) |
| 앱 로그 | 프로젝트 포맷 | 프로젝트 포맷 |
| 오류·traceback | 출력 | 출력 |
| `SIGTERM` 시 로그 비우기 | 신호 핸들러 + lifespan flush | lifespan flush 만 |

`run_server()` 가 `uvicorn.run(log_config=setup_uvicorn_logging())` 을 넘기기 때문입니다(ADR-020).
앱 dictConfig 에 uvicorn 로거를 넣어도 포맷은 통일되지만, "우리 설정이 uvicorn 것보다 나중에 적용된다"는
uvicorn 내부 순서에 기대게 되어 이 저장소 안에서 검증할 수 없으므로 채택하지 않았습니다.

`uvicorn main:app` 에서 신호 핸들러가 안 통하는 이유: uvicorn 은 시작할 때 **현재 신호 핸들러를
스냅샷**하고 종료할 때 그대로 복구한 뒤 신호를 다시 올리는데, CLI 경로에서는 스냅샷을 찍은 **뒤에** 앱을
import 합니다. 스냅샷에는 `SIG_DFL` 이 찍혀 있어 복구 순간 프로세스가 즉시 끝납니다. 그 경로에서 우리 큐에
들어가는 것은 앱 로그뿐이고 앱의 마지막 로그는 lifespan 종료 안에서 나오므로, lifespan 끝에서 flush 하면
잃을 것이 없습니다(ADR-023).

### 9.7 장치별로 막는 구멍

| 장치 | 막는 구멍 | 결정 |
|---|---|---|
| 큐 + listener 스레드 | 로깅이 event loop 를 막음 | NFR-009 |
| 중첩 `async with` | 취소 시 뒤 단계 정리 건너뜀 | ADR-017 |
| lifespan 은 listener 를 멈추지 않음 | lifespan 이후 로그·startup traceback 유실 | ADR-018 |
| `atexit` | 정상 종료에서 listener 정지 | ADR-018 |
| `SIGTERM`/`SIGBREAK` 핸들러 | `docker stop` 에서 `atexit` 미실행 | ADR-022 |
| lifespan 끝의 flush | `uvicorn main:app` 경로의 꼬리 유실 | ADR-023 |
| sentinel·join 예산 | 큐 포화·listener 무응답 시 종료 불가 | ADR-021 |
| `RedactingFilter` | traceback·stack 에 실린 DSN 비밀번호·토큰 노출 | log-redaction ADR-001 |

이 계약은 실제 프로세스를 띄우는 테스트가 지킵니다. 지우거나 약화시키지 마세요 — 게이트가 존재를 확인합니다.

```
tests/integration/test_uvicorn_lifecycle.py   정상 종료 순서 · startup 실패 원인 출력 · uvicorn CLI 꼬리
                                              (DEBUG=false 로 띄워 MySQL 불필요, REDIS_HOST·REDIS_PORT 미지정이면 실패, 닿지 않으면 skip)
tests/utils/test_logs.py                      신호 종료 경로의 flush
tests/core/test_resources.py                  취소·기동 실패 정리, 예산
```

```bash
docker compose -f compose.test.yaml up -d --wait redis-test
REDIS_HOST=127.0.0.1 REDIS_PORT=6379 uv run python -m pytest tests/integration/test_uvicorn_lifecycle.py tests/utils/test_logs.py -rs
```

## 10. 접속 로그 미들웨어

`UserInfoMiddleware`(`app/core/middlewares/user_info_middleware.py`)가 대상 요청(`ACCESS_LOG_ENABLED` 이고 아래 제외 경로·확장자가 아닌 요청)마다 정보를 모으고, 응답을
받은 뒤 `access_log_tasks.spawn()` 으로 저장 태스크를 제출합니다. core 는 저장 방법을 모르고,
`access_log_sink.get_access_log_sink()` 에 등록된 sink 에 위임합니다. `home` 이 import 시점에
`HomeAccessLogSink` 를 등록하며, 이 sink 는 `background_db_session()`(별도 풀)으로 저장하고 직접 커밋합니다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_LOG_ENABLED` | `true` |
| `ACCESS_LOG_EXCLUDE_PATHS` | `["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]` (정확히 일치) |
| `ACCESS_LOG_EXCLUDE_EXTENSIONS` | `[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"]` (접미사) |
| `ACCESS_LOG_SENSITIVE_QUERY_KEYS` | `["password", "token", "access_token", "refresh_token", "secret", "api_key", "code"]` (대소문자 무시, 값을 `***` 로 저장) |
| `ACCESS_LOG_RETENTION_DAYS` | `365` (보존 일수. `0` 이면 지우지 않는다, 음수는 기동 시 검증 오류 — 아래 "보존") |
| `TRUSTED_PROXY_HOPS` | `0` (앞단 신뢰 프록시 수 — 0 이면 전달 헤더를 보지 않는다. **프록시 뒤 배포는 단 수만큼** — 0 이면 전원이 프록시 IP 하나로 보여 접속 로그·로그인 레이트 리밋이 한 사람으로 취급하고, 크게 잡으면 IP 위조) |

- 수집: `ip_address`(아래 IP 결정 규칙), `forwarded_for`·`real_ip`(원본 헤더 — 감사용),
  `user_agent` 와 파싱 결과(`os_name`·`os_version`·`browser_name`·`browser_version`·`device_type`
  (`mobile`/`tablet`/`desktop`/`other`)·`device_brand`·`device_model`·`is_bot`), `request_path`,
  `request_method`, `query_string`(민감 키 값은 `***`), `referer`, `accept_language`,
  `session_id`(설정 `SESSION_COOKIE_NAME` 쿠키의 값), `user_id`(`request.state.user_id` — 인증 의존성
  `get_current_principal` 이 라우트 처리 중에 채우므로 미들웨어가 **응답 뒤에** 읽는다. 익명·401 요청은 NULL, §11.1),
  `response_status`, `response_time_ms`.
- **IP 결정** — `app/core/middlewares/client_ip.py` 의 `ClientIPResolver` 가 정하고, 미들웨어는 생성자로
  받습니다(`setup_user_info_middleware` 가 설정에서 한 번 만든다, service-hardening ADR-006·ADR-021).
  `TRUSTED_PROXY_HOPS=0`(기본)이면 직접 피어 주소만 씁니다. `N` 이면 `X-Forwarded-For` 의 **오른쪽에서
  N번째** 값(신뢰 프록시 N단이 덧붙인 값)이고, 목록이 N개보다 짧거나 값이 IP 가 아니면 직접 피어로
  물러납니다. `X-Real-IP` 는 hops>0 이고 `X-Forwarded-For` 가 없을 때만 봅니다. uvicorn
  `--forwarded-allow-ips` 와 같은 모델이며, 실제 프록시 단수보다 크게 잡으면 다시 위조할 수 있게 됩니다.
- **길이** — 문자열은 저장 직전 home 기능(`fit_to_columns`)이 `UserAccessLog` 컬럼 길이로 자릅니다. 길이는
  모델 컬럼에서 읽습니다(숫자를 두 번 적지 않는다). MySQL strict 모드에서 길이 초과 INSERT 가 실패해 기록이
  조용히 버려지던 경로를 막습니다.
- `user_access_logs` 테이블의 `country`·`country_code`·`city` 컬럼은 채우는 코드가 없습니다.
  인덱스: `created_at`·`ip_address`·`os_name`·`browser_name`·`device_type`·`country`·`session_id`·`user_id`.
- `session_id` 쿠키 값·`referer`·`forwarded_for`(`X-Forwarded-For`)·`real_ip` 는 **원문 그대로** 저장합니다 —
  사용자 결정으로 유지합니다(log-redaction ADR-004). 조회 API 는 슈퍼유저 전용입니다.
- **보존**(security-ops-hardening ADR-002·ADR-003) — Celery beat 가 매일 03:30(`TIME_ZONE` 기준) `home.purge_expired_access_logs` 를
  실행해 `created_at < 지금(UTC) − ACCESS_LOG_RETENTION_DAYS 일` 인 행을 지웁니다(정확히 N일 전 행은 남는다). 정책은
  `AccessLogRetentionService`(보존 일수·시계 주입), 쿼리는 `UserAccessLogRepository.delete_created_before` — `created_at`
  인덱스로 id 를 최대 5,000개 고른 뒤 `DELETE ... WHERE id IN (...)` 하고 **배치마다 커밋**합니다(긴 잠금·거대 트랜잭션
  방지, MySQL·SQLite 공통 쿼리). `0` 이면 쿼리 없이 끝납니다. beat 를 띄우지 않으면 아무것도 지워지지 않습니다(§13).
- `X-Forwarded-For` 는 클라이언트가 위조할 수 있으므로 신뢰 프록시 홉 수(`TRUSTED_PROXY_HOPS`) 밖의 값은
  믿지 않습니다. 이전에는 맨 왼쪽 값을 무조건 믿었습니다 — 기본값 0 은 이 동작을 바꾼 것이니 프록시 뒤 배포는
  홉 수를 설정해야 실제 클라이언트 IP 가 기록됩니다.
- `BackgroundTaskRunner` 는 동시 256개가 상한이고 넘치면 **버리고** `dropped` 를 올립니다. 비핵심 로그용이라
  결제·발송 같은 업무 저장을 이 러너에 넣지 않습니다. 종료 시 drain 합니다(§8).
- 저장 실패는 요청에 영향을 주지 않고 ERROR 로그만 남깁니다. 제출 시점은 `call_next` 가 응답 객체를 돌려준
  뒤이며, 클라이언트가 본문을 다 받았다는 보장은 아닙니다. `call_next` 가 예외로 끝난 요청은 status 500 으로
  기록한 뒤 예외를 그대로 다시 던집니다(바깥 500 처리는 그대로 — service-hardening ADR-007).
- 조회 API 는 `/api/v1/home/access-logs` 계열 5개(전부 읽기 세션)이고, 예시 Celery 태스크
  `home.aggregate_access_stats` 가 통계를 집계합니다.

## 11. 인증 (JWT)

OAuth2 password flow + JWT access/refresh 토큰(service-hardening ADR-013~018·ADR-025·ADR-026). 자격증명은 `user` 기능의
`User.hashed_password` 에 두고, `auth` 기능(`app/features/auth/`)이 흐름(`AuthService`)을, `app/core/security/` 가
여러 기능이 쓰는 부품(해시·토큰·회전 저장소·레이트 리밋·인증 주체·소유권 정책과 그 provider)을 맡습니다.

| 메서드·경로 | 인증 | 요청 | 성공 | 실패 |
|---|---|---|---|---|
| `POST /api/v1/auth/register` | — | JSON (`username`·`email`·`password` 8~128자) | 201 | 409 중복 · 422 · 429 |
| `POST /api/v1/auth/login` | — | **form** (`username`·`password`) | 200 | 401 · 422 · 429 |
| `POST /api/v1/auth/refresh` | — | JSON (`refresh_token`) | 200 | 401 · 422 |
| `POST /api/v1/auth/logout` | — | JSON (`refresh_token`) | 204 | 401 · 422 |
| `GET /api/v1/auth/me` | Bearer | — | 200 | 401 |

```bash
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer","expires_in":900}
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'
curl -X POST localhost:8000/api/v1/auth/refresh -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'          # 새 쌍. 보낸 refresh 는 이제 못 쓴다
curl -X POST localhost:8000/api/v1/auth/logout -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'          # 204
```

**조립(주입)** — 협력 객체는 모두 생성자로 받고 provider 가 만듭니다(service-hardening C-1). 여러 기능이 쓰는 provider 는
core 의 `app/core/security/dependencies.py`, auth 전용은 `auth_dependencies.py` 에 있습니다.

```text
# core (app/core/security/dependencies.py)
get_password_hasher()                                # 프로세스 단일(lru_cache) — auth·user
get_token_service()                                  # TokenService(jwt_settings) — 발급(auth)·검증(principal)
get_refresh_token_store(redis=get_redis)             # RefreshTokenStore(refresh TTL) — auth 회전·user 폐기
get_ownership_policy()                               # OwnershipPolicy — blog·sns·reply·user
get_current_principal(request, token=oauth2_scheme, tokens=get_token_service) -> Principal   # DB 조회 없음
require_superuser(principal=get_current_principal)   # 403
# core (app/core/security/access.py) — 뷰가 dependencies=[...] 에 넣는 접근 수준(§11.2)
Public / PublicWrite                                 # 표식(아무것도 안 함) — 인증 없는 조회 / 쓰기
LoginRequired = Depends(get_current_principal)       # 401
SuperuserRequired = Depends(require_superuser)       # 401 / 403
AccessPolicyGuard().verify(app)                      # main.py 조립 끝 — 선언 없거나 모순되면 기동 거부
# auth
get_auth_service(session=get_writer_db_session, hasher, tokens, store)
login_rate_limit / register_rate_limit               # RateLimiter(get_redis) + ClientIPResolver
get_current_user(principal=get_current_principal, session=get_read_only_db_session)   # /me — 엔티티 필요
```

테스트는 `dependency_overrides[get_redis]` 에 fakeredis 를 넣으면 회전 저장소·레이트 리밋이 함께 바뀝니다.

**비밀번호 — `PasswordHasher`** (`app/core/security/password_hasher.py` — auth 의 가입·로그인과 user 의 관리자 생성이 함께 쓴다, ADR-026)
- 새 해시는 Argon2id(`pwdlib`). 이전 버전의 bcrypt 해시(`$2` 접두사)는 그때 규칙(UTF-8 72바이트 절단)으로 검증하고,
  맞으면 Argon2 로 다시 해시해 **로그인 핸들러가 커밋**합니다(점진 이전 — 그 밖의 로그인은 커밋하지 않습니다).
- **상수 시간 인증**: 사용자가 없거나 비밀번호가 없어도 더미 Argon2 해시로 같은 비용을 치릅니다.
  **논블로킹 해싱**: 해시·검증은 `asyncio.to_thread` 에서 돕니다.

**토큰 — `TokenService`** (`app/core/security/tokens.py`)
- claims `sub, type, iat, nbf, exp, jti(uuid4 hex), iss, aud` + access 는 `username`·`su`(슈퍼유저 여부), refresh 는 `fam`(회전 family).
  access 의 `username`·`su` 는 필수입니다 — `su` 가 없는 토큰(인가 도입 전 발급분)은 401 이고 다시 로그인하면 됩니다.
- 검증: 알고리즘은 설정 하나(`algorithms=[JWT_ALGORITHM]`), `iss`·`aud` 일치, 위 claim 전부 필수, `leeway`, `type` 일치.
  access·refresh 는 서명 키도 다릅니다. 실패는 사유와 관계없이 `InvalidTokenException`(401, `AUTH_INVALID_TOKEN`).

**회전·폐기 — `RefreshTokenStore`** (`app/core/security/refresh_store.py`, Redis)

| 키 | 값 · TTL | 쓰임 |
|---|---|---|
| `auth:rt:{jti}` | `{"sub","fam"}` · refresh 만료 | 아직 안 쓴 refresh. 회전 시 `GETDEL` 로 소비 |
| `auth:user:{sub}:fams` | family 집합 · refresh 만료 | 사용자 단위 폐기(`revoke_user`) |
| `auth:fam:{fam}:revoked` | `1` · refresh 만료 | 폐기된 family |

- `refresh`: 서명 검증 → family 폐기 여부 → `GETDEL` 로 jti 소비. 값이 없으면 **재사용**(이미 쓴 토큰)이라 family 를
  폐기하고 401 — 그 사이 발급된 새 refresh 도 함께 막힙니다. 사용자가 없거나 비활성이어도 family 폐기 후 401.
  `GETDEL` 하나가 원자적이라 같은 토큰으로 동시에 회전해도 한쪽만 성공합니다.
- `logout`: family 폐기, 204. 이미 폐기됐어도 204(멱등). access 토큰은 폐기하지 않습니다 — 만료(기본 15분)까지 유효합니다.

**레이트 리밋 — `RateLimiter`** (`app/core/security/rate_limit.py`, Redis 고정 창)
- `MULTI` 안에서 `SET key 0 EX window NX` → `INCR` → `TTL`. 창은 첫 hit 에 시작하고 이후 hit 이 늘리지 않습니다.
- 로그인: `auth:rl:login:{ip}:{username 소문자}`(기본 5회/60초)와 `auth:rl:login:{ip}`(20회/60초). 성공하면 앞의 키만 지웁니다.
  회원가입: `auth:rl:register:{ip}`(5회/3600초). IP 는 접속 로그와 같은 `ClientIPResolver`(`TRUSTED_PROXY_HOPS`, §10).
  관리 화면 로그인은 같은 한도를 `admin:rl:login:{ip}:{username}`·`admin:rl:login:{ip}` 로 따로 셉니다(§12).
  **프록시 뒤 배포는 `TRUSTED_PROXY_HOPS` 를 앞단 프록시 단 수로 설정합니다** — 0 이면 모든 클라이언트가 프록시 IP 하나로
  보여 IP 한도가 전체 사용자에게 함께 걸리고, 실제보다 크게 잡으면 IP 를 위조할 수 있습니다.
- 초과는 `TooManyRequestsException` — 429 + `Retry-After`(창이 끝날 때까지 초). `AppException.headers` 를 전역 핸들러가 싣습니다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | README [세션·토큰 만료](../../README.md#세션토큰-만료) |
| `JWT_ALGORITHM` | `HS256` (`HS256`·`HS384`·`HS512` 만 허용) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `fastapi-default-project-structure` / `fastapi-default-project-structure-api` |
| `JWT_LEEWAY_SECONDS` | `10` |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` — 교체 필수, 서로 달라야 함(test 외 기동 거부, §6.1) |
| `AUTH_LOGIN_MAX_ATTEMPTS` / `AUTH_LOGIN_IP_MAX_ATTEMPTS` / `AUTH_LOGIN_WINDOW_SECONDS` | `5` / `20` / `60` |
| `AUTH_REGISTER_MAX_ATTEMPTS` / `AUTH_REGISTER_WINDOW_SECONDS` | `5` / `3600` |

- 비활성 사용자(`is_active=false`)는 로그인·회전·`me` 에서 막힙니다. 비활성화·삭제는 `revoke_user` 로 refresh 를 모두 폐기합니다.
- `get_current_user` 는 `get_current_principal` 위에서 읽기 세션(primary 고정, §4.3)의 `UserRepository` 로 조회합니다 — Redis 를 쓰지 않습니다.

### 11.1 인가 — Principal · 슈퍼유저 · 소유권

인가는 **슈퍼유저/일반 2단계**입니다(service-hardening ADR-017·018). RBAC 세분화는 비목표입니다.

- **`Principal(id, username, is_superuser)`** (`app/core/security/authorization.py`, frozen dataclass) — access 토큰의
  `sub`·`username`·`su` 로만 만듭니다. 요청마다 DB·Redis 왕복이 없고, 기능은 사용자 모델 대신 이 값 하나에 기댑니다.
  `get_current_principal` 이 만들고 `request.state.user_id` 를 채웁니다 — 접속 로그 미들웨어가 **응답 뒤에** 읽어
  `user_access_logs.user_id` 에 남깁니다(§10).
- **별칭** — 인자용 `CurrentPrincipal`(로그인)·`SuperuserPrincipal`(슈퍼유저), 데코레이터용 접근 수준
  `LoginRequired`·`SuperuserRequired`·`Public`·`PublicWrite`(§11.2 — 뷰마다 하나 선언, 없으면 기동 거부).
  토큰 문제는 401(`WWW-Authenticate: Bearer`), 권한 부족은 403 `FORBIDDEN`.
- **`OwnershipPolicy.ensure_can_modify(owner_id, principal)`** — 소유자 본인 또는 슈퍼유저만 통과. `owner_id` 가 `None`
  (인가 도입 전 행)이면 슈퍼유저만. blog·sns·reply·user 서비스가 생성자로 받고 수정·삭제(user 는 단건 조회 포함) 메서드가
  `principal` 을 받아 부릅니다. 존재 확인(404)이 먼저이고 user 만 반대로 권한이 먼저입니다(남의 ID 로 계정 존재를 캐지 못하게).
- **스키마** — `users.is_superuser`(기본 false), blog·sns·reply 의 `author_id`(String(36), NULL, 인덱스, FK 없음 — 기능 모델끼리
  참조하지 않는다). 리비전 `c9e1a3b5d7f0`. 작성자(`author`·`author_id`)는 생성 시 서버가 주체로 채우고 수정 스키마에 없습니다.

| 기능 | 조회 | 생성 | 수정·삭제 |
|---|---|---|---|
| blog·sns·reply | `Public` | 인자 `CurrentPrincipal` | 인자 `CurrentPrincipal` + `OwnershipPolicy` |
| catalog | `Public` | `SuperuserRequired` | `SuperuserRequired` |
| reports·home(접속 로그) | 뷰마다 `SuperuserRequired` | 〃 | — |
| user | 목록 `SuperuserRequired` · 단건 인자 `CurrentPrincipal` + `OwnershipPolicy` | `SuperuserRequired`(비밀번호 필수) | 수정 인자 `CurrentPrincipal` + `OwnershipPolicy` + `is_active`·`is_superuser` 는 슈퍼유저 · 삭제 `SuperuserRequired` |
| auth | `/me` — `get_current_user`(안에서 `get_current_principal`) | `register`·`login`·`refresh`·`logout` 은 `PublicWrite` | — |
| health·ready | `Public` | — | — |

- **첫 슈퍼유저** — `python -m scripts.create_superuser`(`scripts/create_superuser.py`). `background_db_session` + core 의
  `get_password_hasher` + `UserRepository` 로 조립해 만들거나 승격하고 한 번 커밋합니다. 비밀번호는 `getpass` 또는
  `--password-stdin` 으로만 받습니다(환경 변수를 읽지 않는다 — 설정 계약).
  이 계정이 관리 화면(`/admin`) 로그인 계정이기도 합니다.
- **SQLAdmin 은 이 인가 밖**입니다(§12) — `/admin` 은 JWT 가 아니라 **활성 슈퍼유저의 Redis 서버 세션**으로 들어가고,
  그 세션은 API 를 인증하지 않습니다.

### 11.2 접근 수준 선언과 기본 거부

모든 API 뷰는 접근 수준을 **하나** 선언합니다(access-policy ADR-001~003). 경로 데코레이터의 `dependencies=[...]` 에 넣는
`Depends` 객체 넷이 `app/core/security/access.py` 에 있습니다.

| 수준 | 정체 | 쓰는 곳 | 실패 |
|---|---|---|---|
| `Public` | 아무것도 하지 않는 `async` 표식 함수 | 인증 없는 조회 — GET·HEAD·OPTIONS 만 | — |
| `PublicWrite` | 또 다른 표식 함수 | 인증 없는 쓰기를 의도적으로 연다 — 가입·로그인·refresh·logout | — |
| `LoginRequired` | `Depends(get_current_principal)` | 로그인 | 401 |
| `SuperuserRequired` | `Depends(require_superuser)` | 슈퍼유저 | 401 / 403 |

- **판정** — `AccessPolicyGuard.levels()` 가 라우트의 의존성 트리(dependant)를 재귀로 훑어 위 호출 대상이 있는지 봅니다.
  그래서 인자 `principal: CurrentPrincipal`/`SuperuserPrincipal`, 안에서 `get_current_principal` 을 쓰는 의존성(`/me` 의
  `get_current_user`), 라우터 단위·`include_router(dependencies=…)` 선언도 같은 선언으로 인정됩니다. `require_superuser` 는
  안에서 `get_current_principal` 을 쓰므로 둘이 함께 보이면 슈퍼유저로 접습니다.
- **기본 거부** — `main.py` 가 라우터 include·health/ready·`/docs`·SQLAdmin 마운트를 마친 직후 `AccessPolicyGuard().verify(app)`
  를 부릅니다. 위반이 하나라도 있으면 위반 **전체** 목록을 담은 `AccessPolicyError`(`RuntimeError`)로 `main` import 가
  실패합니다(§7.3). 위반: ① 선언 없음 ② 서로 다른 수준 둘 이상(Public 계열 + 인증 계열 등) ③ 쓰기 메서드에 `Public`
  (→ `PublicWrite` 를 쓰라는 안내) ④ 안전한 메서드에 `PublicWrite`.
- **대상** — `fastapi.routing.iter_route_contexts(app.routes)` 로 FastAPI 0.141 의 `_IncludedRouter` 중첩을 펼친 모든
  `APIRoute`. `include_in_schema=False` 인 경로(DEBUG 의 Scalar `/docs`)도 포함합니다. FastAPI 가 붙이는 문서 경로(Starlette
  `Route`)와 `Mount`(`/admin` — 자체 세션 인증, §12)는 `APIRoute` 가 아니라 빠집니다.
- **함수를 감싸는 데코레이터는 쓰지 않습니다.** FastAPI 는 핸들러 시그니처로 주입·검증·OpenAPI 를 만듭니다 — Django 식
  `@login_required` 로 감싸면 그 시그니처가 가려집니다. 경로 데코레이터의 `dependencies=` 가 FastAPI 에서 "데코레이터로
  거는" 방법이고, 데코레이터만으로는 생기지 않는 기본 정책을 기동 검사가 채웁니다.
- **OpenAPI** — 401/403 응답 문서(`UNAUTHORIZED_RESPONSES`·`FORBIDDEN_RESPONSES`)는 종전대로 `responses=` 에 펼칩니다.
  home·reports 는 의존성만 뷰로 옮기고 `responses=FORBIDDEN_RESPONSES` 는 라우터 단위로 둡니다 — 생성되는 OpenAPI 는
  바뀌지 않았습니다(security 표시 포함).
- **테스트** — 가드 규칙은 `tests/core/test_access_policy.py`, 예시 정책은 `tests/test_authorization.py` 의 `EXPECTED_ACCESS`
  (유일한 기대 표 — 401/403 실요청 대상도 여기서 뽑는다), 조립 경로는 `tests/test_main.py` 의
  `test_main_refuses_to_start_when_a_view_declares_no_access_level`(별도 프로세스에서 선언 없는 뷰를 더하면 import 실패).

## 12. SQLAdmin

```text
main.py (ADMIN_DISABLED 가 아닐 때만 — true 면 이 모듈을 import 하지도 않는다)
  └─ register_admin(app, engine)          app/features/admin.py — main 이 아는 유일한 이름
       ├─ create_admin_interface(...)     Admin(app, engine, title, authentication_backend, templates_dir) = /admin 마운트
       │    └─ build_admin_auth_backend(app)   AdminAuthBackend 를 기존 provider 로 조립
       └─ register_admin_views(admin)     ADMIN_VIEWS 를 선언 순서대로 add_view
```

- 세 함수(와 백엔드 조립 함수)는 SQLAdmin 공식 API 가 아니라 이 프로젝트의 조립 함수입니다. 생성 쪽은
  앱·엔진·인증 백엔드·템플릿 위치(모두 `Admin` 생성 인자라 여기에만 넣을 수 있다)를, 등록 쪽은 뷰 목록만
  압니다. 회귀 가드: `tests/test_admin_wiring.py`.
- **로그인**(admin-login ADR-001~003): `/admin` 은 **활성 슈퍼유저**만 들어갑니다. `AdminAuthBackend`
  (`app/features/auth/admin_backend.py`)가 SQLAdmin `AuthenticationBackend` 를 구현합니다 — `login` 은 레이트 리밋
  (`admin:rl:login:` 키, `AUTH_LOGIN_*` 한도) → API 로그인과 같은 `AuthService.authenticate`(bcrypt→Argon2 재해시 포함)
  → `is_superuser` 확인 → `session.clear()` 후 `user_id` 만 저장하고 `rotate_session` 으로 세션 ID 를 바꿉니다. 그 앞에
  **CSRF 토큰 대조**가 있습니다(아래). 실패 사유는 구분하지 않고(400), 한도 초과는 로그인 화면을
  429 + `Retry-After` 로 다시 그립니다. `authenticate` 는 **요청마다 DB** 에서 활성·슈퍼유저를 확인하고, `logout` 은 세션을
  비웁니다(→ Redis 키 삭제).
- **관리 세션 = Redis 서버 세션**(admin-session-hardening ADR-001) — `app/core/security/admin_session.py` 의
  `AdminSessionStore`(저장·조회·삭제·사용자 단위 폐기)와 `RedisSessionMiddleware`(`scope["session"]` 에 dict — `request.session`
  인터페이스 그대로). 쿠키 `admin_session` 에는 무작위 세션 ID(`secrets.token_urlsafe(32)`)만 있고, 내용은
  `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}` → JSON `{"data", "user_id", "created_at"}`, 사용자별 인덱스
  `admin:user_sessions:{user_id}`(SET). 만료는 절대(`ADMIN_SESSION_MAX_AGE_SECONDS`, 연장 없음)와 미사용
  (`ADMIN_SESSION_IDLE_SECONDS`, 요청마다 TTL 갱신·절대 만료 이내) — 기본값은 README [세션·토큰 만료](../../README.md#세션토큰-만료). 기존 세션 저장은 `SET XX` 라 요청 도중
  폐기된 세션을 응답이 되살리지 않습니다. 쿠키: `Path=/admin`, `SameSite=Strict`, HttpOnly, `Max-Age`=절대 만료,
  staging/production 은 `Secure`. 쿠키의 ID 가 Redis 에 없으면 빈 세션 + 쿠키 삭제. Redis 장애는 **503**(fail-closed).
  미들웨어는 SQLAdmin **하위 앱에만** 있어 API 인증과 섞이지 않습니다(`tests/test_admin_session_scope.py`). Redis 는
  `_app_redis(app)` 로 바깥 앱의 것을 요청마다 받습니다(lifespan 이 연 뒤에야 있다).
- **즉시 폐기**(ADR-002) — 비활성화·슈퍼유저 강등·삭제 시 그 사용자의 관리 세션을 모두 지웁니다(다른 브라우저 포함). API 경로는
  `UserService` 가 refresh 토큰 `revoke_user` 와 같은 자리에서 주입된 `AdminSessionStore.revoke_user` 를 부르고
  (`get_admin_session_store` — `ADMIN_DISABLED=true` 면 `None`), 관리 화면 경로는 `UserAdmin.on_model_change`·
  `on_model_delete`(sqladmin 의 **커밋 전** 훅, ADR-007)가 이 요청의 저장소(`request_session_store`)로 부릅니다 — 수정은 변경 전
  모델과 저장할 값을 `revocations` 하나로 비교해 두 집합을 정합니다 — API refresh 토큰은 비활성화·비밀번호 해시 변경·삭제
  (`UserService` 와 같은 집합), 관리 세션은 그 집합 + 슈퍼유저 해제(ADR-009). 일반 수정은 아무것도 폐기하지 않습니다. 폐기가
  실패하면(Redis) 커밋 전이라 변경도 저장되지 않습니다. 자기 자신을 강등하면 현재 세션도 끊깁니다. 매 요청 DB 확인은 이중 방어로 남깁니다.
- **CSRF**(ADR-003·004) — `AdminCsrfMiddleware`(하위 앱, 세션 미들웨어 안쪽)가 `/admin` 의 POST·PUT·PATCH·DELETE 전부
  (로그인·로그아웃 포함)에서 세션의 `csrf_token` 과 요청 토큰(헤더 `X-CSRF-Token` 또는 폼 필드 `csrf_token`)을
  `hmac.compare_digest` 로 대조합니다. 폼 본문은 버퍼링해 읽고 같은 바이트를 sqladmin 에 다시 흘립니다 — 본문 10 MiB 초과는 413(`Content-Length` 로
  먼저, 없거나 거짓이면 읽는 도중 누적 크기로), 필드 하나 1 MiB 초과·깨진 폼은 400(integration-e2e ADR-015, 상수 `MAX_FORM_BODY_BYTES`·`MAX_FORM_FIELD_BYTES`). 실패는
  403 — 로그인 POST 는 로그인 화면(새 토큰), 그 밖은 관리 화면 오류 화면(`AdminAuthBackend.csrf_rejected`). 엔드포인트보다
  먼저라 위조 로그인 POST 는 레이트 리밋·자격 확인에 닿지 않습니다(security-ops-hardening ADR-004 의 검사를 여기로 옮겼다).
  화면은 `app/templates/admin/sqladmin/base.html` 이 원본(`sqladmin_original/base.html`)을 확장해 `<meta name="csrf-token">`
  과 인라인 스크립트(POST 폼 hidden 필드, 같은 출처 fetch/XHR 헤더, 로그아웃 링크 → POST 폼)를 더합니다. 로그아웃 라우트는
  `_logout_post_only` 가 POST 전용으로 바꿔 끼워 GET 은 405 입니다. sqladmin 을 올릴 때 원본 블록·로그아웃 링크가 바뀌면
  `tests/test_admin_csrf.py` 의 드리프트 검사가 실패합니다. sqladmin `@action`(GET 으로 상태 변경)은 쓰지 않습니다(테스트로 고정).
- **로그인 화면** — `app/templates/admin/sqladmin/login.html`(Bootstrap 5.3.8 CSS, jsDelivr + SRI, JS 없음, hidden `csrf_token`)이
  SQLAdmin 기본 화면을 덮어씁니다. `templates_dir` 의 FileSystemLoader 가 패키지 템플릿보다 먼저 찾아지기 때문입니다.
- **끄기** — `ADMIN_DISABLED=true` 면 sqladmin·백엔드·세션 미들웨어·관리 세션 저장소를 만들지 않고 `/admin` 이하가 404 이며, 앱 응답·기동
  로그에 경로가 나오지 않습니다(`tests/test_admin_disabled.py`). 예전 `ADMIN` 설정이 남아 있으면 기동을 거부합니다(§6.1).
- 흐름도·쿠키 구조·위협 모델·운영 문제 해결은 [관리 화면 인증 안내서](./workflows/admin-authentication.html)가 원본입니다.
- ModelView 는 기능이 소유합니다(`app/features/<name>/admin.py` 의 `admin_views`). 취합은 **명시 import**
  입니다 — 예전의 `getattr(module, "admin_views", [])` 수집은 빈 `admin.py` 를 조용히 건너뛰었습니다.
  `ADMIN_VIEWS` 는 기능명 사전순이며 테스트가 순서까지 대조합니다. 모델이 있는 기능은 `admin.py` 를 가져야 합니다.
- 기능 `__init__.py` 로 `admin_views` 를 재노출하지 않습니다 — 재노출하면 라우터 import 만으로 sqladmin 이
  로드되어 `ADMIN_DISABLED=true` 가 "라우트만 안 붙임" 이 됩니다(`ADMIN_DISABLED=true` 미로드 검사).
- `column_filters` 에는 `sqladmin.filters` 객체(`BooleanFilter`·`OperationColumnFilter`)를 넣습니다 — 모델 컬럼을 그대로
  넣으면 sqladmin 0.32 의 목록 화면이 500 입니다. 생성 시각(`UTCDateTime`)에는 sqladmin 연산 필터 대신 `LocalDateFilter`
  (`app/core/admin_filters.py`, 템플릿 `app/templates/admin/sqladmin/filters/local_date_filter.html`)를 겁니다 — 날짜
  `YYYY-MM-DD` 를 `TIME_ZONE` 의 로컬 자정으로 해석해 UTC aware 범위로 질의하고(같은 날 / 이후(포함) / 이전(미포함)),
  빠른 선택(오늘·최근 7일·최근 30일)을 함께 그립니다. **기간**(admin-session-hardening ADR-005) 연산 `between` 은 값
  `YYYY-MM-DD~YYYY-MM-DD` 를 양 끝 포함(시작일 0시 ≤ t < 종료일 다음날 0시)으로 질의하고, 한쪽만 주면 열린 구간입니다 —
  sqladmin 이 값 하나만 넘기므로 필터 템플릿의 두 번째 폼이 날짜 입력 두 개를 합쳐 보냅니다. 형식이 틀린 입력·역순 기간은
  필터를 적용하지 않고 WARNING 만 남깁니다(500 아님).
  `created_at` 이 있는 모든 뷰가 이 필터를 가집니다(security-ops-hardening ADR-005). 모든 뷰의 목록·필터·상세 화면은 `tests/test_admin_views_render.py` 가 로그인 상태로 확인합니다(admin-login F-005).
- 배포 전 확인은 [README 운영 배포 체크리스트](../../README.md#운영-배포-체크리스트)에 있습니다.
- `User` 뷰는 `hashed_password` 를 목록·상세·폼·내보내기에서 제외하고 `can_create = False` 입니다
  (비밀번호 없이 만든 계정은 로그인할 수 없습니다). 이 제외 설정을 지우면 해시가 노출됩니다
  (`tests/core/test_admin_views.py`).

## 13. Celery

- 앱: `app/celery/app.py` 의 `celery_app` — broker·backend 모두 `REDIS_URL`, `include=iter_task_modules()`,
  JSON 직렬화, `timezone=TIME_ZONE`, `enable_utc=True`(내부 시각은 UTC, crontab 은 TIME_ZONE 으로 해석), 빈 `beat_schedule`.
- **주기 작업(beat)** — 중앙 앱은 빈 `beat_schedule` 만 두고, 기능의 `tasks.py` 가 import 될 때 자기 항목을
  `celery_app.conf.beat_schedule[...]` 에 더합니다(security-ops-hardening ADR-003 — 중앙이 기능을 import 하지 않는 태스크 자동 발견과 같은
  철학). beat 도 기동 시 include 모듈을 import 하므로(`loader.init_worker`) 그 등록이 보입니다. 현재 항목은
  `home.purge_expired_access_logs`(매일 03:30 `TIME_ZONE`, §10 보존) 하나입니다. 실행:
  `uv run python -m celery -A app.celery.app:celery_app beat --loglevel=INFO` — worker 와 **별도 프로세스 하나만** 띄웁니다
  (beat 가 둘이면 같은 작업이 두 번 실행된다). beat 는 실행 시각을 `celerybeat-schedule` 파일에 기록하므로 쓰기 가능한
  작업 디렉터리가 필요합니다.
- 태스크는 각 기능의 `app/features/<name>/tasks.py` 에 둡니다(예: `app/features/home/tasks.py` 의
  `home.aggregate_access_stats`). include 는 모델 등록과 같은 기능 패키지 탐색(`app/core/db/models_registry.py` 의
  `iter_task_modules()`)이 만듭니다 — `tasks.py` 가 있는 기능만 들어가고, 탐색은 `find_spec` 으로 존재만 확인해
  태스크 모듈을 import 하지 않습니다(태스크 모듈은 `celery_app` 을 import 하므로 앱 생성 중 import 하면 순환이 된다).
  `app/celery` 는 기능을 import 하지 않으므로 **기능 디렉터리를 지우면 그 태스크도 include 에서 함께 빠지고 worker 는
  깨지지 않습니다**(service-hardening ADR-012, `tests/core/test_celery_app.py` 가 AST 로 고정). 같은 모듈이
  `import_all_models()` 로 기능 모델을 모두 등록합니다(worker 진입점이 이 모듈이다).
- 태스크 본문의 서비스 조립은 그 기능의 provider 함수(세션을 인자로 받는 일반 함수, 예:
  `build_user_access_log_service(session)`)를 재사용합니다 — HTTP provider 도 같은 함수를 부릅니다.
- FastAPI 는 worker·beat 를 띄우지 않습니다. 실행 예:
  `uv run python -m celery -A app.celery.app:celery_app worker --loglevel=INFO` (Redis 필요, 이 문서
  작성 시점에 worker 기동은 검증하지 않음).
- 태스크 함수는 동기이고 내부 코루틴은 `run_async()`(`app/celery/task.py`)로 실행합니다. **프로세스당 영속
  event loop** 를 재사용합니다 — aiomysql 연결은 만든 루프에 묶이는데, 매번 `asyncio.run()` 으로 루프를 닫으면
  두 번째 태스크가 `Event loop is closed` 로 실패했습니다. 태스크 안 DB 는 `background_db_session()`.
- 수명(`app/celery/lifecycle.py`, AR-010): `worker_process_init` → `restart_log_listener()`(fork 로 사라진
  listener 스레드 복구). `worker_process_shutdown` → 루프가 살아 있는 동안 `dispose_engine()`(10초) →
  `shutdown_asyncgens()` → `loop.close()` → 루프 참조 제거. FastAPI lifespan 과 소유권이 섞이지 않습니다.
- 요청의 세션·Service·Request 객체를 태스크 인자로 넘기지 않습니다 — JSON 직렬화 가능한 id·값만 넘기고
  태스크가 자기 세션을 엽니다. 재시도·중복 처리는 태스크마다 정합니다.

## 14. Alembic

```python
# migrations/env.py
fileConfig(config.config_file_name, disable_existing_loggers=False)   # 앱 로거를 끄지 않는다
import_all_models()
target_metadata = Base.metadata
config.set_main_option(
    "sqlalchemy.url",
    db_settings.ALEMBIC_URL.render_as_string(hide_password=False).replace("%", "%%"),
)
```

- URL: `ALEMBIC_DATABASE_URL` 이 있으면 그 값을 `make_url` 로 읽은 것, 없으면 primary URL 의 드라이버만
  `mysql+pymysql` 로 바꾼 것. 마이그레이션은 항상 primary 에서 실행합니다. Alembic Config 는 ConfigParser 라
  `%` 를 보간으로 읽으므로 `%%` 로 바꿔 넘깁니다(퍼센트 인코딩된 비밀번호 대비).
- revision 체인(단일 head, CI 가 확인): `f4adf0ae24ea`(baseline — 기존 5개 테이블) → `b2f1a9c0d3e4`
  (`users.hashed_password`) → `c3d5e7f9a1b2`(`catalog_products`) → `d4e6f8a0b2c3`(`sales_orders`) →
  `e5f7a9b1c4d5`(`sales_daily_snapshots`) → `a7c9e1f3b5d6`(시각 컬럼 전부 MySQL `DATETIME(6)` + 기존 값
  KST→UTC 변환, SQLite 는 no-op — service-hardening ADR-010) → `c9e1a3b5d7f0`(`users.is_superuser`·작성자 `author_id`
  소유권 컬럼 — head). **배포 전:** `a7c9e1f3b5d6` 은 기존 MySQL 값을 모두 +09:00 으로
  가정합니다 — 다른 시간대였다면 적용 전에 리비전의 `_LEGACY_OFFSET` 을 바꾸고, 값을 고쳐 쓰므로 적용 전에 백업합니다.
- `env.py` 는 `app/core/models/types.py` 의 `compare_type`(MySQL `UTCDateTime` 의 소수 초 자릿수 비교 — 기본 비교는
  `DATETIME` 과 `DATETIME(6)` 을 같다고 본다)과 `render_item`(autogenerate 가 앱 import 없는
  `sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")` 로 쓰게)을 넘깁니다.
- Alembic 은 lifespan 에 들어가지 않으므로 Redis 확인을 하지 않습니다. 서버 기동은 upgrade 를 하지 않습니다.
- `DEBUG=true` 의 `create_all` 은 migration 결함을 가립니다(예전 baseline 이 테이블 4개를 빠뜨렸는데 개발
  환경에서는 보이지 않았습니다). 그래서 빈 DB 에서 head 까지 올리고 모델과 비교하는 테스트가 있습니다:
  `tests/core/test_migration_chain.py`(SQLite), `tests/integration/test_mysql_raw_sql.py`(MySQL 8.4 —
  upgrade → downgrade → 재-upgrade).
- 작성 절차는 [DEVELOPMENT §8](./DEVELOPMENT.md#8-마이그레이션).

## 15. 설계 결정 요약

| 결정 | 이유 |
|---|---|
| 라우터는 `main.py` 명시 `include_router` (FastAPI Bigger Applications 패턴) | 로딩 순서와 공개 API 구성을 코드에서 바로 추적할 수 있다. 앱 레지스트리·자동 탐색·`INSTALLED_APPS` 식 목록은 한 번씩 도입했다가 제거했다(§16) |
| 모델은 디렉터리 스캔 | 모델 import 목록이 세 곳에 복제돼 한쪽만 고치는 누락이 있었다 |
| UnitOfWork 없음 — 쓰기 핸들러가 커밋 | FastAPI 0.141 의 yield 의존성 종료 시점 변화에서 커밋 실패가 2xx 로 둔갑했다(§3.2) |
| `BaseRepository` 를 최소 CRUD 8개로 | 사용처 0건인 고급 메서드 20종을 제거했다. 공통성은 두 기능 이상에서 확인될 때만 올린다(ADR-007) |
| ORM·Raw Base 독립 | Raw 결과에 ORM 의미가 새지 않게(AR-003) |
| 로그는 큐 + stdout/stderr, 파일은 기본 꺼짐(`LOG_FILE_ENABLED` 로 프로세스별 파일), 앱별 로거 없음 | event loop 비차단(NFR-009 — 파일 쓰기도 listener 스레드), 수집은 런타임 책임, 새 기능이 로깅 설정을 건드리지 않게 |
| 표준 라이브러리 우선 · 자원은 소유자가 닫는다 · 실패와 취소를 구분한다 · 테스트 없는 보장은 문서에 쓰지 않는다 | 종료 신뢰성 작업(REQ-010)의 원칙 |
| Redis(서버 6.2 이상 — `GETDEL`)는 필수 startup 조건이자 `/ready` 판정 대상 | Celery broker 와 같은 서버가 준비됐는지 기동 시점에 드러낸다(REQ-011). 기동 후 Redis 가 끊기면 `/ready` 가 503 으로 트래픽을 뺀다(service-hardening ADR-011). 그동안 Redis 를 쓰는 API 는 503 `SERVICE_UNAVAILABLE`(§3.3, integration-e2e ADR-009) |
| 관리 화면은 기본 켜짐 + 활성 슈퍼유저 로그인, `ADMIN_DISABLED=true` 로 흔적 없이 끈다 | 개발 우선 템플릿이라 받자마자 DB 를 볼 수 있어야 하고, 배포에서는 로그인이 지킨다. 쓰지 않는 배포는 공격 표면 자체를 없앤다. 세션은 `/admin` 하위 앱 전용이라 API 의 Bearer 계약과 섞이지 않는다(admin-login ADR-001~006 — ADR-045 ③ 의 확인 플래그를 대체) |
| 예시·빈 비밀값, 짧은 키, access==refresh 는 test 외 **모든 ENV** 에서 기동 거부. staging/production 은 `DEBUG=true`·`LOG_LEVEL=DEBUG` 도 거부 | 예시 키로 뜨면 누구나 토큰을 위조하고, debug 는 SQL 과 바인딩 값을 로그로 내보낸다. 잘못된 설정은 개발 단계부터 오류로 드러나야 `.env` 를 고친다(ADR-027·028·030·045) |
| `.env` 가 없으면 필수 값이 환경 변수로 와야 한다 | 코드 기본값은 유지하되 기본값만으로는 뜨지 않게 한다. 파일 없이 주입하는 컨테이너 배포는 통과(ADR-045 ①) |
| 응답 직렬화는 FastAPI 기본(Pydantic) | `ORJSONResponse` 는 이득이 없고 0.141 에서 deprecated. 제거 전후 응답 바이트 동일 확인 |
| 템플릿 프로필 분리(minimal/api-db/production) 보류 | 세 벌을 유지하는 비용이 크다. "무겁다" 는 피드백이 반복되면 선택 기능을 걷어내는 스크립트 쪽으로 재검토 |
| 라우트 검사는 `app.openapi()` 기준 | FastAPI 0.141 부터 `app.routes` 가 하위 라우터를 평탄화하지 않는다(`_IncludedRouter`) |
| 비밀번호는 Argon2id(pwdlib), 기존 bcrypt 는 로그인 시 재해시 | FastAPI 공식 문서의 현행 권장. 평문이 없어 일괄 이전은 불가능하다(service-hardening ADR-013) |
| refresh 는 회전 + 재사용 탐지(Redis `GETDEL`), access 는 짧은 만료 | 탈취된 refresh 로 만료까지 재발급되던 구멍을 닫는다. access 즉시 폐기는 비목표 — 15분 만료로 대신한다(service-hardening ADR-014·015) |
| 로그인·가입 레이트 리밋은 Redis 고정 창 + 라우트 의존성 | 명령 세 개로 끝나는 가장 단순한 방식. 창 경계 버스트는 수용(service-hardening ADR-016) |
| 인가는 토큰만으로 만드는 `Principal` + 슈퍼유저/일반 2단계 + `OwnershipPolicy` 한 클래스 | 기능끼리 import 하지 않고(core 하나만 의존) 요청마다 DB 왕복이 없다. 권한 회수는 access 만료(15분)까지 늦다(service-hardening ADR-017·018) |
| 여러 기능이 쓰는 인증 provider·`PasswordHasher` 는 core | user 가 auth 를 import 하는 지름길 대신 core 로 올린다(service-hardening ADR-026) |

## 16. 변경 이력

현재 동작은 본문과 코드를 따릅니다. 아래는 전환 기록입니다(최신순).

| 날짜 | 변경 |
|---|---|
| 2026-10-22 | HTML 가이드 사이트(docs-guide-site): `docs/guides/index.html` 허브와 주제별 HTML 요약 19편(부팅·설계·API·설정·요청·인증·기능 8편·개발·테스트·운영·시퀀스)을 코드에 맞춰 추가, 내용 계약 `tests/test_docs_guide_site.py`(API 표 = openapi × 접근 수준, 설정 표 = Settings 전 필드, Mermaid `11.12.0` 고정, 허브 링크). 서비스 docstring 의 트랜잭션 경계 문구를 핸들러 커밋으로 정정 |
| 2026-10-21 | 안내서 검수 반영(docs-guide-review): 미들웨어 순서(가장 바깥 = `unhandled_exception_middleware`)·설정 클래스 9종·revision head `c9e1a3b5d7f0`·파일 로그·`/ready` Redis·관리 세션(Redis 서버 세션)·e2e 실행·경로 수 24/39 등 HTML 안내서·DEVELOPMENT·README 를 코드에 맞춤, 결정 인용을 ADR 번호로, 이 표를 최신순으로 |
| 2026-10-21 | e2e 정책 결정 2차(integration-e2e ADR-012~017): §3.3 OpenAPI 422 = `ErrorResponse`, 모든 401 에 `WWW-Authenticate: Bearer`, 처리기 없는 예외는 가장 바깥 사용자 미들웨어(로그 1번·keep-alive), §4.3 인증 사용자 조회 primary, 관리 화면 CSRF 상한(413 `Content-Length` 선판정·필드 1 MiB 400), 의존성 `aiomysql[rsa]` |
| 2026-10-20 | 장애 동작 결정(integration-e2e ADR-009~011): §3.3 Redis 연결 오류 → 503 `SERVICE_UNAVAILABLE`(traceback 한 번, keep-alive 유지), §4.3 읽기 전용 세션의 replica 연결 오류 → primary 한 번 재시도 + WARNING, §9.2 프로세스 파일을 설정 로드 직후 실행 프로그램으로 붙여 import 중 줄도 기록 |
| 2026-10-20 | 전수 통합(integration-e2e): `tests/e2e/`(마커 `e2e`) + `compose.e2e.yaml`(MySQL primary·GTID replica·Redis 7.4, `-p itest-default`) — API 전수 매트릭스·연동 시나리오·관리 화면(Playwright)·장애 주입·운영, 인벤토리 대조·비밀값 grep, CI job `e2e`. Redis 가 필요한 기존 통합 테스트는 `REDIS_HOST`·`REDIS_PORT` 를 명시해야 돈다(W0) |
| 2026-10-19 | 보안·운영(security-ops-hardening): §4.1 `hide_parameters` 회귀 고정, §10 접속 로그 보존(`ACCESS_LOG_RETENTION_DAYS`, beat 매일 03:30 배치 삭제), §12 로그인 폼 CSRF 토큰·`created_at` 날짜 필터(`LocalDateFilter`), §13 beat 등록 구조 |
| 2026-10-19 | 관리 세션(admin-session-hardening): §12 서명 쿠키 → Redis 서버 세션(`AdminSessionStore`·`RedisSessionMiddleware`, 절대·미사용 만료, 강등·비활성화·삭제 즉시 폐기), 로그인 이후 CSRF(`AdminCsrfMiddleware`·`base.html` meta·스크립트), POST 로그아웃, 기간 필터. 설정 `ADMIN_SESSION_*`, 의존성 `itsdangerous` 제거 |
| 2026-10-19 | 설정 정리(config-cleanup): 읽는 코드가 없던 `SMTPSettings`·`UploadSettings`·`SESSION_EXPIRE_SECONDS` 삭제(옛 `.env` 줄은 무시), 세션·토큰 만료의 정본을 README 표 하나로, 사용처 계약 테스트 `tests/core/test_settings_usage.py` |
| 2026-10-19 | 로깅 개편(logging-overhaul): §9.2 모든 실행 경로 같은 형식(`adopt_foreign_handlers`)·필수 필드 검사·헤더를 외부 로거 이름으로도 판별·프로세스별 파일(`attach_log_files`, `DailySizeRotatingFileHandler`), §9.3 `LOG_APP_LEVELS`(`AppLevelFilter`), §9.4.1 DSN 사용자명·설정 비밀값 원문 마스킹. README "로깅" 절이 Django `LOGGING` 대응표 |
| 2026-10-13 | 접근 수준 선언(access-policy): §11.2 신설 — `Public`·`PublicWrite`·`LoginRequired`·`SuperuserRequired`, 기동 시 기본 거부 `AccessPolicyGuard`(§7.1·§7.3), home·reports 라우터 단위 인가를 뷰 단위 선언으로, §11.1 표 갱신. OpenAPI 불변 |
| 2026-10-13 | 로그 마스킹·헤더·Redis 버전(log-redaction-fixes): §9.4.1 `RedactingFilter`(traceback·stack·DEBUG 500 detail, uvicorn CLI·Celery 경로 포함), §3.3 예외 헤더 보존 확인, §7.2 Redis 최소 6.2 확인(`REDIS_MIN_VERSION`), §10 접속 로그 원문 저장은 사용자 결정으로 유지 |
| 2026-10-12 | 인증 코어(service-hardening 단계 F1): `app/core/security/`(토큰·회전 저장소·레이트 리밋), Argon2 `PasswordHasher` + bcrypt 점진 이전, `POST /auth/logout`, 429 `Retry-After`. `app/utils/authenticator/` 제거 |
| 2026-10-12 | 관리 화면 로그인(admin-login): §12 — `AdminAuthBackend`(슈퍼유저·요청마다 DB 확인·레이트 리밋)·`admin_session` 쿠키·Bootstrap 로그인 템플릿, `ADMIN`→`ADMIN_DISABLED`(잔존 시 기동 거부, §6.1), 배포 환경의 관리 화면 확인 플래그 제거, `session_settings` 소비처, 의존성 `itsdangerous`. [관리 화면 인증 안내서](./workflows/admin-authentication.html) 신설 |
| 2026-10-12 | 인가(service-hardening 단계 F2): §11.1 신설 — `Principal`·`require_superuser`·`OwnershipPolicy`, access `su` claim, `users.is_superuser`·`author_id` 리비전, 라우트 권한 표, `scripts/create_superuser.py`. `PasswordHasher`·공용 provider 를 core 로 이동. §10 `user_id` 가 이제 채워진다 |
| 2026-10-07 | 설정 검사 확장(ADR-045): `.env` 부재 시 필수 환경 변수 요구, 예시 비밀값·짧은 키를 개발 환경에서도 거부, 배포 환경 `ADMIN=true` 는 `ADMIN_ALLOW_UNAUTHENTICATED` 확인 필요. CI 가 `review_gate --fast` 실행(ADR-044) |
| 2026-09-17 | Redis startup 검증과 종료 순서 확장(`_redis`), 가이드를 `docs/guides/` 로 이동, 착수 명세를 `docs/specs/` 로 추적, CI 에 Redis·MySQL job(ADR-024) |
| 2026-09-17 | 문서 재구성(ADR-025): README·ARCHITECTURE·DEVELOPMENT 3종으로 통합. QUICKSTART → README, LOGGING-AND-SHUTDOWN·서버 수명 HTML → 이 문서, ORM-RAW-WORKFLOW·개발 HTML·명세의 workflow-guide → DEVELOPMENT |
| 2026-09-17 | 문서 일관성(ADR-026): HTML 안내서 두 편(`server-lifecycle-guide.html`·`feature-development-guide.html`)과 명세 `workflow-guide.md` 복원, 통일 문서 배치. HTML 은 요약, 상세 표는 Markdown. `API_DESCRIPTION`·미사용 설정 설명·`requires-python>=3.13`(ruff/mypy 대상 3.13) 정합. 모든 쓰기 핸들러를 응답 DTO 검증 → 커밋 → 반환 순서로 통일(`tests/test_write_dto_before_commit.py`) |
| 2026-09-17 | 배포 안전 검사(ADR-027): staging/production 에서 예시 비밀 키·access==refresh 면 `config` import 실패. `.env.example` 비밀 키 예시를 서로 다른 `change-this-...` 로 |
| 2026-08-27 | 종료 신뢰성(REQ-010): 중첩 `async with`(ADR-017), listener 프로세스 소유(ADR-018), `run_server(log_config=…)`(ADR-020), dictConfig 네이티브 큐(ADR-021), 신호 핸들러(ADR-022), lifespan 끝 flush(ADR-023), 실제 uvicorn 통합 테스트, `--mysql-required` |
| 2026-08-25 | 종료 조립을 `AsyncExitStack` → 평문 `try/finally`(ADR-016) — 이후 취소 안전성 손실이 확인됨 |
| 2026-08-20 | Raw 쓰기 예제(스냅샷 적재, ADR-010~013), 세션 옛 이름 제거, 게이트 요구 ID·INV-10 검사 |
| 2026-08-13 | ORM/Raw Repository 이원화(REQ-001): `app/core/resources.py`, 큐 기반 로깅, 모델 Mixin, `BaseRepository` 823→185줄, `RawRepositoryBase`, 참조 예제 `catalog`·`reports`, MySQL 8.4 통합 환경, OpenAPI 규칙 테스트 |
| 2026-08-11 | `app/features/` 명칭 확정, SQLAdmin ModelView 를 기능 소유로 이전 + 명시 취합(`app/features/admin.py`), 중앙 목록 순회 → 명시 `include_router`, `scripts/new_app.py` 제거, 문서 드리프트 정정 |
| 2026-08-10 | 외부 검수 후속: mypy 오류 해소, 트랜잭션 경계 회귀 테스트, 모델 import SSOT(`models_registry`), 조회 라우트 읽기 세션 전환, Alembic baseline 복구, FastAPI 0.115 → 0.141(커밋을 핸들러 본문으로 이동), `ORJSONResponse` 제거 |
| 2026-07-01 | 표준 FastAPI 배선으로 전환 — `AppRegistry`·`bootstrap.create_app()`·`app/apps.py` 제거, 기능 `__init__.py` 가 `router` 공개 |
| 2026-06-23 | 기능 모델 레지스트리 아키텍처 도입, 이 문서 최초 작성. 곧이어 자동 발견을 제거하고 `app/apps.py` 수동 등록으로 전환 |

---

## 부록. 설정 필드 전체

`config.py` 의 필드 선언 기준 코드 기본값입니다(`.env.example` 의 예시 값과 다를 수 있습니다). 비밀 값은
기본값을 적지 않습니다. 소비 지점은 §6.2.

**TimezoneSettings** — `TIME_ZONE`=`Asia/Seoul`

**AppSettings**

| 키 | 타입 | 기본값 |
|---|---|---|
| `PROJECT_NAME` | str | `FastAPI Project` |
| `VERSION` | str | `0.1.0` |
| `DESCRIPTION` | str | `config.API_DESCRIPTION` |
| `DEBUG` | bool | `true` |
| `ADMIN_DISABLED` | bool | `false` |
| `ENV` | `development`/`staging`/`production`/`test` | `development` |
| `SERVER_HOST` / `SERVER_PORT` | str / int | `0.0.0.0` / `8000` |

**DatabaseSettings**

| 키 | 타입 | 기본값 |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` | str / int | `localhost` / `3306` |
| `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | str | `root` / 빈 값 / `fastapi_db` |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` | bool | `false` / `false` |
| `DB_READ_STICKY_AFTER_WRITE` | bool | `true` |
| `MYSQL_REPLICA_HOSTS` | list[str] (JSON) | `[]` |
| `MYSQL_REPLICA_PORT` | int | `3306` |
| `MYSQL_REPLICA_USER` / `MYSQL_REPLICA_PASSWORD` / `MYSQL_REPLICA_DATABASE` | str \| None | 없음 → primary 값 재사용 |
| `ALEMBIC_DATABASE_URL` | str \| None | 없음 → primary DSN 에서 유도 |

**CORSSettings** — `CORS_ALLOW_ORIGINS`=`["*"]`, `CORS_ALLOW_CREDENTIALS`=`false`,
`CORS_ALLOW_METHODS`=`["*"]`, `CORS_ALLOW_HEADERS`=`["*"]`, `CORS_EXPOSE_HEADERS`=`[]`, `CORS_MAX_AGE`=`600`

**LogSettings**

| 키 | 기본값 | 비고 |
|---|---|---|
| `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` / `LOG_FILE_LEVEL` | 없음 | §9.3 |
| `LOG_APP_LEVELS` | 빈 값 | 헤더별 최소 레벨 `blog=DEBUG,sqlalchemy=WARNING` — §9.3 |
| `LOG_SQL_ECHO_ENABLED` | `false` | §9.4 |
| `LOG_CONSOLE_ENABLED` | `true` | false 면 콘솔 핸들러 없음(앱·uvicorn CLI·Celery), 파일도 꺼져 있으면 기동 시 경고 한 줄 — §9.2 |
| `LOG_CONSOLE_FORMAT` / `LOG_FILE_FORMAT` | `[{asctime} {tzname}] {levelname:5} [app={appname}] [{module}:{classname}:{funcName}:{lineno}] {message}` | 콘솔 / 파일 포매터 fmt, 잘못되거나 필수 필드가 빠지면 기동 오류 — §9.2 |
| `LOG_DATE_FORMAT` | `%Y-%m-%d %H:%M:%S` | 포매터 datefmt(빈 값 금지) — §9.2 |
| `LOG_FILE_ENABLED` / `LOG_DIR` | `false` / `logs` | 프로세스별 파일 출력 — §9.2 |
| `LOG_MAX_SIZE_MB` / `LOG_RETENTION_DAYS` | `10` / `30` | 하루 안 분할 크기(1 이상) / 회전 파일 보관 일수(0 = 지우지 않음) — §9.2 |

**MiddlewareSettings** — §10 표

**RedisSettings** — `REDIS_HOST`=`localhost`, `REDIS_PORT`=`6379`, `REDIS_DB`=`0`, `REDIS_PASSWORD`=없음
(`REDIS_URL` = `redis://[:비밀번호@]호스트:포트/DB`, 비밀번호는 퍼센트 인코딩)

**JWTSettings** — §11 표

**SessionSettings** — `SESSION_COOKIE_NAME`=`session`(접속 로그의 `session_id` 쿠키 이름으로만 읽힌다), `SESSION_SECRET_KEY`=(placeholder — test 외 기동 거부, §6.1. 관리 세션 ID → Redis 키 HMAC 키, §12), `ADMIN_SESSION_MAX_AGE_SECONDS`·`ADMIN_SESSION_IDLE_SECONDS`(관리 세션 만료, §12 — 기본값은 README [세션·토큰 만료](../../README.md#세션토큰-만료))

파생 값(`MYSQL_URL`·`ALEMBIC_URL`·`MYSQL_REPLICA_URLS`·`replication_active`·`routing_mode`·`REDIS_URL`·유효 로그
레벨)은 필드가 아니라 `config.py` 의 property/메서드입니다.
