# 아키텍처·런타임 레퍼런스

이 저장소가 **어떻게 조립되고, 어떻게 뜨고, 요청을 어떻게 처리하고, 어떻게 끝나는지**를 한곳에
적습니다. 설치·실행은 [README](../../README.md), 코드를 쓰는 절차는 [DEVELOPMENT](./DEVELOPMENT.md)
를 봅니다. 같은 흐름을 도식과 함께 따라가는 요약은
[서버 수명주기 안내서](./server-lifecycle-guide.html)이고, 상세 표는 이 문서가 소유합니다. 코드와 이 문서가
다르면 코드가 정답이며, 이 문서(와 요약하는 HTML)를 고칩니다.

본문에 나오는 `ADR-0xx`·`REQ-0xx` 는 `docs/crp/groups/orm-raw-repository/design-baseline.md`,
`AR-`·`TX-`·`NFR-` 등은 `docs/specs/orm-raw-repository/requirements.md` 의 ID 입니다.

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
├── config.py               # Pydantic Settings 12종 — 환경 변수를 읽는 유일한 모듈
├── conftest.py             # pytest 전역 옵션 --mysql-required (루트에 있어야 인식된다)
├── pyproject.toml / uv.lock / .python-version
├── alembic.ini / migrations/        # env.py 가 import_all_models() 로 전 기능 모델 수집
├── compose.test.yaml       # 테스트용 MySQL 8.4(127.0.0.1:3308, tmpfs) + Redis 7(6379)
├── scripts/review_gate.py  # 결정적 검수 게이트
├── .github/workflows/ci.yml
├── app/
│   ├── features/                    # 기능 단위 vertical slice
│   │   ├── admin.py                 # SQLAdmin 취합 — ADMIN_VIEWS + register_admin()
│   │   ├── auth/                    # OAuth2 password + JWT (자체 모델 없음, user 모델 사용)
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
│   │       └── tests/
│   ├── core/                        # 프레임워크 인프라
│   │   ├── resources.py             # 프로세스 수명 자원의 생성·해제 단일 지점
│   │   ├── exception.py             # AppException 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 설명
│   │   ├── db/session.py            # 엔진·세션 팩토리·세션 의존성·create_db_tables·ping·dispose
│   │   ├── db/router.py             # 읽기/쓰기 라우팅(RoutingSession)
│   │   ├── db/models_registry.py    # 모델 모듈 탐색·import 단일 지점
│   │   ├── models/models_base.py    # Base + UUID/Created/Updated Mixin
│   │   ├── repositories/            # crud_base·repository_base(ORM) / raw_crud_base·raw_repository_base(Raw)
│   │   ├── services/services_base.py
│   │   └── middlewares/             # cors_middleware·user_info_middleware·background_tasks·access_log_sink
│   ├── celery/                      # app.py(중앙 앱)·tasks.py(중앙 태스크)·task.py(run_async)·lifecycle.py
│   └── utils/                       # logs/ · authenticator/ · pagination/ · validators.py
├── tests/                  # core 계약·배선·교차 기능 / utils / integration(실제 uvicorn·MySQL)
├── docs/                   # guides/ · specs/ · crp/  (색인은 README)
└── media/ static/ poc/ logs/   # 예약 디렉터리 (.gitkeep 만 추적, 파일 로그는 쓰지 않는다)
```

### 1.2 의존 방향과 기능 간 참조

```
features → core → utils        (config 는 누구나 import)
```

| 영역 | 규칙 |
|---|---|
| `app/features/<name>/` | 비즈니스 코드는 전부 여기. `core` 를 쓰고 **다른 기능을 import 하지 않는다.** 예외: `auth` 는 횡단 관심사라 `user` 의 모델·Repository 를 쓴다. 기능 간 데이터 참조는 FK 없는 식별자로 둔다(예: `Reply.post_id`) |
| `app/core/` | 특정 기능을 직접 알지 않는다. 기능이 core 에 붙어야 하면 등록 훅을 쓴다(`access_log_sink.set_access_log_sink()`). `models_registry` 만 등록 목적으로 기능 모델을 동적 import 한다 |
| `app/utils/` | 순수 유틸. 상위 계층에 의존하지 않는다 |

### 1.3 핵심 파일

| 파일 | 역할 |
|---|---|
| `main.py` | `FastAPI(...)` 생성(lifespan·태그·문서 URL), `CustomCORSMiddleware`·`UserInfoMiddleware` 등록, 예외 핸들러 4종, 기능 라우터 8개 `include_router(prefix="/api")`, `/health`·`/ready`·Scalar `/docs`, `ADMIN=true` 면 `register_admin(app, engine)` |
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
- **폴더가 있어도 `main.py` 에 없으면 라우트는 없습니다.** `ApiSettings.API_VERSION` 은 존재하지만
  prefix 는 각 `router.py` 가 `/v1` 을 직접 선언하므로 설정값만 바꿔서는 버전이 바뀌지 않습니다.
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
요청 → UserInfoMiddleware → CORSMiddleware → 라우트
     → Depends: 세션 의존성(get_writer_db_session / get_read_only_db_session)
              → 기능 의존성 get_<name>_service[_readonly] → Service(db_session)
     → View 본문: Service 유스케이스 호출 → (쓰기면) await service.commit() → 응답 DTO
     → 응답 → UserInfoMiddleware 가 접속 로그 저장 태스크 제출 (§10)
     → 의존성 teardown: 예외로 빠졌으면 rollback, 세션 close
```

| 계층 | 하는 일 | 하지 않는 일 |
|---|---|---|
| View(`api/routers/v1`) | 파라미터·본문 수신, Service 호출, 쓰기 커밋, 응답 DTO 변환, OpenAPI 메타데이터 | SQL, `AsyncSession` 직접 주입, 복잡한 도메인 분기 |
| Dependency | 세션 선택 + `Service(db_session)` 조립 후 **반환**(`yield` 아님) | 유스케이스 실행, 커밋 |
| Service(`BaseService`) | 유스케이스·비즈니스 규칙, 같은 세션으로 Repository 조립 | HTTP 객체, SQL 문자열, 커밋 시점 결정 |
| Repository | ORM 쿼리 또는 Raw SQL, `flush` 까지 | 커밋, HTTP 응답, 비즈니스 규칙 |
| Schema | 입력 검증·응답 공개 필드·문서 | DB 접근 |

미들웨어는 나중에 등록한 것이 바깥이라 `UserInfoMiddleware` 가 가장 바깥입니다.
같은 요청 안에서 같은 의존성 함수는 FastAPI 기본(`use_cache=True`)으로 한 번만 실행되지만,
writer 와 read-only 는 다른 함수라 서로 다른 세션입니다.

### 3.2 트랜잭션 경계 — 쓰기 핸들러가 커밋한다

```python
# dependencies — 조립만
async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(db_session)

# View — 커밋은 여기서, 응답 전에 한 번
async def create_product(payload: ProductCreate, service: CatalogService = Depends(get_catalog_service)):
    product = await service.create_product(payload)
    await service.commit()
    return ProductResponse.model_validate(product)
```

- **성공**: View 본문이 응답을 만들기 전에 `await service.commit()` (TX-004).
- **예외**: 커밋이 실행되지 않고 세션 의존성의 `except` 가 `rollback()` 후 재전파합니다.
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

`main.py` 의 핸들러 4종이 모든 오류를 `ErrorResponse`(`error_code`·`message`·`detail`)로 바꿉니다.

| 예외 | 응답 |
|---|---|
| `AppException` 과 하위(`NotFoundException`·`DuplicateException`·`DatabaseException`…) | 예외가 가진 상태 코드·`error_code` |
| `RequestValidationError` | 422, `detail` 에 `field`·`message`·`type` 목록 |
| Starlette `HTTPException` | 해당 코드, `error_code=HTTP_<코드>` |
| 그 밖의 `Exception` | 500 `INTERNAL_SERVER_ERROR`. **`DEBUG=true` 면 `detail` 에 예외 문자열**이 실린다 |

핸들러는 `JSONResponse(content=model.model_dump(mode="json"))` 로 직렬화합니다 — `detail` 에
datetime·UUID 가 들어와도 깨지지 않게 하기 위해서입니다(`tests/test_response_serialization.py`).
일반 응답은 `response_model` 을 통해 Pydantic 이 직접 JSON 을 만듭니다(커스텀 응답 클래스 없음).
startup 예외는 HTTP 핸들러가 처리하지 않습니다(§7.3).

### 3.4 health 와 ready

| 경로 | 의미 |
|---|---|
| `GET /health` | 프로세스 생존과 `VERSION`. 외부 연결을 검사하지 않는다 (liveness) |
| `GET /ready` | `ping_writer_db()` — writer 엔진에서 `SELECT 1`, 2초(`READINESS_TIMEOUT_SECONDS`). 실패·초과 시 503, 원인은 서버 로그에만(DSN·드라이버 원문 비노출). **Redis 는 다시 검사하지 않는다** |

## 4. DB 엔진·세션·라우팅

### 4.1 엔진과 커넥션 풀

`app/core/db/session.py` 가 **import 시점**에 엔진을 만듭니다. 엔진 생성은 URL·풀 정책 준비일 뿐
접속이 아닙니다 — 실제 연결은 DDL·`/ready`·첫 쿼리에서 생깁니다.

| 객체 | 풀 | 용도 |
|---|---|---|
| `engine`(= `writer_engine`) | `pool_size=20`, `max_overflow=20`, `pool_timeout=30` | 요청 세션, 개발 DDL, `/ready`, SQLAdmin |
| `read_engines` | replica 마다 20+20 | `DB_ROUTER_ENABLED` 와 `DB_REPLICATION_ENABLED` 가 모두 true 일 때만 생성 |
| `background_engine` | `pool_size=10`, `max_overflow=10`, `pool_timeout=60` | 접속 로그 sink, `background_db_session()`, Celery |

공통: `pool_recycle=280`, `pool_pre_ping=True`, `pool_reset_on_return="rollback"`,
`connect_timeout=10`, `charset=utf8mb4`. 세션 팩토리는 `expire_on_commit=False`, `autoflush=False`.

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

세 요청 의존성은 `async with` 안에서 세션을 내주고, 전달된 `Exception` 에 `rollback()` 후 재전파하며,
종료 시 close 합니다. 세션은 풀에서 빌린 연결이므로 반드시 이 경로로 닫혀야 합니다.

### 4.3 읽기/쓰기 라우팅

`DB_ROUTER_ENABLED=true` 면 `create_routing_sessionmaker()` 의 `RoutingSession.get_bind()` 가 구문마다
엔진을 고릅니다(`app/core/db/router.py`).

1. ORM flush·Core DML·`text()` 의 쓰기 키워드(`INSERT`·`UPDATE`·`DELETE`·`CREATE`… , `SELECT … FOR UPDATE`) → writer
2. 그 밖의 SELECT → 세션당 하나의 replica(라운드로빈으로 고른 뒤 고정)
3. 쓰기가 일어난 세션의 이후 SELECT → writer (`DB_READ_STICKY_AFTER_WRITE=true`, 기본)

| `routing_mode` | 조건 | 결과 |
|---|---|---|
| `single` | `DB_ROUTER_ENABLED=false`(기본) | 단일 엔진 세션. **읽기 세션의 쓰기 차단도 동작하지 않는다** |
| `router-single` | 라우터만 켬 | 전부 primary, 쓰기 차단은 동작 |
| `router-replicated` | 라우터 + 복제 + `MYSQL_REPLICA_HOSTS` | SELECT → replica, 쓰기 → primary |

- 복제만 켜고 라우터를 끄거나 replica 목록이 비면 `DatabaseSettings` 가 기동 시 거부합니다.
  replica 주소는 `host`·`host:port`·`[IPv6]:port` 만 허용합니다.
- 기동 로그 `[database] 라우팅 구성: {...}` 에 모드와 비밀번호를 가린 DSN 이 남습니다.
- 한계: `text()` 판별은 선두 키워드 기준이라 `WITH … DELETE` 같은 CTE DML 을 읽기로 오판합니다
  (residual-risk R-001). sticky 는 세션 안의 정책이라 다음 요청의 복제 지연까지 없애지 않습니다.
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
| `CreatedAtMixin` / `UpdatedAtMixin` | `created_at` / `updated_at` (`DateTime(timezone=True)`, `TIME_ZONE` 기준, `updated_at` 은 ORM UPDATE 시 `onupdate`) | |
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
| `list(skip, limit)` | 단순 페이지(정렬 없음 — 정렬이 필요하면 기능 Repository 에서) |
| `count(**filters)` / `exists(pk)` | 개수 / SQL `EXISTS` |
| `update_by_id(pk, data)` / `delete_by_id(pk)` | 없으면 `None` / 삭제 여부 `bool` |

- 모든 경로가 같은 예외 변환을 거칩니다: `IntegrityError` → `DuplicateException`, 그 밖의
  `SQLAlchemyError` → `DatabaseException`. 원본은 chaining 으로 보존하고 **응답 `detail` 에는
  모델·연산 이름만** 싣습니다(무결성 위반 메시지에는 중복된 값 자체가 들어 있습니다).
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
  남기고 **SQL 본문과 파라미터는 남기지 않습니다**(NFR-004). `SQLAlchemyError` 는
  `DatabaseException(detail={"query": query_name})` 으로 바뀝니다.
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

- `config.py` 의 12개 `BaseSettings` 는 각각 `env_file=".env"`, `extra="ignore"` 로 자기 필드를 읽습니다.
  우선순위는 **프로세스 환경 변수 → 작업 디렉터리의 `.env` → 코드 기본값**입니다.
- `get_*_settings()` 는 `@lru_cache` 이고, 파일 끝의 `app_settings = get_app_settings()` 등이 import 시점에
  전역 객체를 만듭니다. 실행 중 `.env` 를 바꿔도 반영되지 않습니다. 테스트에서 캐시만 비워도 이미 가져간
  전역 참조는 그대로이므로 새 프로세스나 monkeypatch 로 확인합니다.
- 타입 오류·validator 위반은 `config` import 자체를 실패시켜 lifespan 전에 기동을 막습니다.
  validator: 복제 설정 모순·replica 주소 형식(`DatabaseSettings`), `CORS_ALLOW_ORIGINS=["*"]` +
  `CORS_ALLOW_CREDENTIALS=true`(`CORSSettings`), `SMTP_TLS` + `SMTP_SSL`(`SMTPSettings`).
- 환경 변수를 직접 읽는 곳은 `config.py` 뿐입니다(`tests/core/test_settings_contract.py`).

### 6.2 설정 클래스와 소비 지점

| 전역 객체 | 소비 지점 |
|---|---|
| `timezone_settings` | 로그 시각(`TzFormatter`), 모델 시간 기본값, Celery `timezone`, 스냅샷 `generated_at` |
| `app_settings` | FastAPI 메타데이터, `DEBUG`(문서·DDL·로그 레벨 기본값·500 detail·reload), `ADMIN`, `ENV`(로그 구성), `SERVER_HOST/PORT` |
| `db_settings` | DSN·라우팅·replica(`session.py`), `ALEMBIC_URL`(`migrations/env.py`) |
| `cors_settings` | `CustomCORSMiddleware.configure_cors()` |
| `log_settings` | `build_dictconfig()` — `LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·`LOG_SQL_ECHO_ENABLED` |
| `middleware_settings` | `UserInfoMiddleware` 활성·제외 규칙 |
| `redis_settings` | startup ping client(`REDIS_URL`), Celery broker/backend |
| `jwt_settings` | `app/utils/authenticator/auth.py` |
| `api_settings`·`session_settings`·`smtp_settings`·`upload_settings` | **소비 코드 없음** — 설정만 준비돼 있다(쿠키 세션·메일 발송·업로드 구현 없음) |

`LogSettings` 의 `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 도 필드만 있고 코드가
읽지 않습니다 — false 로 줘도 콘솔이 꺼지지 않고, 포맷은 §9.2 의 고정값입니다.

## 7. 기동

### 7.1 import 시점

`uv run python main.py` 는 `main` 을 import 해 조립한 뒤 `run_server()` 가 `uvicorn.run("main:app", …)` 을
부르고, `uvicorn main:app` 은 uvicorn 이 `main` 을 import 합니다. 어느 쪽이든 순서는 같습니다.

1. `config` — 설정 생성·검증
2. `get_logger()` 첫 호출 → `configure_logging()` — dictConfig 적용, listener 시작, `atexit`·신호 훅 등록(§9.5)
3. `app/core/db/session.py` — 엔진·세션 팩토리 생성, 라우팅 구성 로그
4. `app.features` 각 패키지 — 라우터·모델 import, `home` 의 sink 등록
5. `FastAPI(...)` → 미들웨어 → 예외 핸들러 → `include_router` × 8 → health/ready/`/docs` → `ADMIN` 이면 SQLAdmin 마운트

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
| `_redis(app)` 진입 | `Redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)` → `await client.ping()`. 성공해야 `app.state.redis = client`. **끄는 설정 없음** |
| `_background_tasks()` 진입 | 없음 (종료 때 drain 담당) |
| `_prepare_database()` | `import_all_models()` → `len(Base.metadata.tables)`. 0개면 DB 접속 안 함 / `DEBUG=false` 면 DDL 생략 / `DEBUG=true` 면 `create_db_tables(import_models=False)` — writer `engine.begin()` 안에서 `create_all`, 30초 guard |
| `yield` | 서버가 요청을 받기 시작한다 |

`app.state.redis` 는 기동 확인에 쓴 client 를 보관할 뿐이고, 기능에 주입되는 공용 Redis 의존성은 아직
없습니다. `create_all` 은 없는 테이블만 만들며 컬럼 변경·삭제·데이터 이동을 하지 않습니다.
여러 worker 가 `DEBUG=true` 로 동시에 뜨면 DDL 도 동시에 시도되므로 운영은 `DEBUG=false` + Alembic 입니다.

### 7.3 기동 실패 경로

| 실패 지점 | 결과 |
|---|---|
| 설정 타입·validator | `config` import 실패 — lifespan 전 |
| Redis ping (연결·인증·timeout) | `[startup] Redis 연결 실패: <오류 타입>` ERROR 후 재전파. background 컨텍스트에는 아직 들어가지 않았으므로 drain 없이 **Redis `aclose()` → DB dispose(“자원 해제 완료” 로그) → 로그 flush** 만 실행. `app.state.redis`·`app.state.resources` 는 `None` (`tests/core/test_resources.py::test_redis_connection_failure_stops_startup_and_cleans_up`) |
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
요청 코드 ─ put_nowait ─▶ [bounded queue 10,000] ─▶ QueueListener 스레드 ─▶ stdout / stderr
```

root 로거에는 `BoundedQueueHandler` 하나만 붙고, 필터(`SqlNoiseFilter`, `ContextFilter`)는 **적재 전에
요청 스레드에서** 돕니다(`ContextFilter` 는 호출 스택에서 클래스명을 뽑으므로 listener 스레드에서는 늦습니다).

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

파일 핸들러·rotation 은 없습니다. 저장·검색·rotation 은 Docker·Kubernetes·수집 agent 가 맡습니다.

포맷은 고정입니다(`LOG_FORMAT`):

```
[{asctime} {tzname}] {levelname:5} [app={appname}] [{module}:{classname}:{funcName}:{lineno}] {message}
[2026-09-17 16:29:05.704 KST] INFO  [app=core] [session:-:<module>:166] [database] 라우팅 구성: {...}
```

- `app=` 은 로거 이름이 아니라 **소스 경로**에서 정합니다: 기능명(`app/features/<name>/`), `core`·`celery`·
  `utils`·`migrations`, 그 밖의 저장소 코드는 `app`, 설치된 패키지는 `ext`. uvicorn 로거는
  `setup_uvicorn_logging()` 이 붙인 필터로 `app=uvicorn`.
- `classname` 은 `LoggerMixin`(`self.log`)이면 주입값, 아니면 호출 프레임의 `self`/`cls`, 없으면 `-`.
- 앱별 로거를 dictConfig 에 등록하지 않습니다(charter §2-4, 가드 `test_dictconfig_has_no_per_app_loggers`).
  새 기능이 로깅 설정을 건드릴 일이 없는 대신, 앱별·서드파티별 레벨을 따로 줄 수 없습니다.

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

### 9.4 SQL 로그 차단

`DEBUG=true` 면 유효 레벨이 DEBUG 라 SQLAlchemy·드라이버가 실행 SQL 과 **바인딩 값**(비밀번호 해시·토큰·
검색어)을 찍습니다. `SqlNoiseFilter` 가 `sqlalchemy.engine`·`sqlalchemy.pool`·`aiosqlite`·`aiomysql`·
`asyncmy`·`pymysql` 로거의 **WARNING 미만**을 막습니다(장애는 계속 보입니다). SQL 을 봐야 할 때만
`LOG_SQL_ECHO_ENABLED=true` 로 엽니다(NFR-001, `tests/core/test_sql_logging_leak.py`).

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
| uvicorn 로그 | 프로젝트 포맷 + `[app=uvicorn]`, 같은 큐 | uvicorn 기본 포맷(`INFO:     …`) |
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

이 계약은 실제 프로세스를 띄우는 테스트가 지킵니다. 지우거나 약화시키지 마세요 — 게이트가 존재를 확인합니다.

```
tests/integration/test_uvicorn_lifecycle.py   정상 종료 순서 · startup 실패 원인 출력 · uvicorn CLI 꼬리
                                              (DEBUG=false 로 띄워 MySQL 불필요, Redis 없으면 모듈 skip)
tests/utils/test_logs.py                      신호 종료 경로의 flush
tests/core/test_resources.py                  취소·기동 실패 정리, 예산
```

```bash
docker compose -f compose.test.yaml up -d --wait redis-test
uv run python -m pytest tests/integration/test_uvicorn_lifecycle.py tests/utils/test_logs.py -rs
```

## 10. 접속 로그 미들웨어

`UserInfoMiddleware`(`app/core/middlewares/user_info_middleware.py`)가 요청마다 정보를 모으고, 응답을
받은 뒤 `access_log_tasks.spawn()` 으로 저장 태스크를 제출합니다. core 는 저장 방법을 모르고,
`access_log_sink.get_access_log_sink()` 에 등록된 sink 에 위임합니다. `home` 이 import 시점에
`HomeAccessLogSink` 를 등록하며, 이 sink 는 `background_db_session()`(별도 풀)으로 저장하고 직접 커밋합니다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_LOG_ENABLED` | `true` |
| `ACCESS_LOG_EXCLUDE_PATHS` | `["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]` (정확히 일치) |
| `ACCESS_LOG_EXCLUDE_EXTENSIONS` | `[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"]` (접미사) |

- 수집: `ip_address`(`X-Forwarded-For` 첫 값 → `X-Real-IP` → 소켓 주소), `forwarded_for`, `real_ip`,
  `user_agent` 와 파싱 결과(`os_name`·`os_version`·`browser_name`·`browser_version`·`device_type`
  (`mobile`/`tablet`/`desktop`/`other`)·`device_brand`·`device_model`·`is_bot`), `request_path`,
  `request_method`, `query_string`, `referer`, `accept_language`, `session_id`(쿠키 `session_id`),
  `user_id`(`request.state.user_id` — 현재 이를 채우는 코드는 없다), `response_status`, `response_time_ms`.
- `user_access_logs` 테이블의 `country`·`country_code`·`city` 컬럼은 채우는 코드가 없습니다.
  인덱스: `created_at`·`ip_address`·`os_name`·`browser_name`·`device_type`·`country`·`session_id`·`user_id`.
- `X-Forwarded-For` 는 클라이언트가 위조할 수 있으므로 신뢰할 프록시 뒤에서만 의미가 있습니다.
- `BackgroundTaskRunner` 는 동시 256개가 상한이고 넘치면 **버리고** `dropped` 를 올립니다. 비핵심 로그용이라
  결제·발송 같은 업무 저장을 이 러너에 넣지 않습니다. 종료 시 drain 합니다(§8).
- 저장 실패는 요청에 영향을 주지 않고 ERROR 로그만 남깁니다. 제출 시점은 `call_next` 가 응답 객체를 돌려준
  뒤이며, 클라이언트가 본문을 다 받았다는 보장은 아닙니다. `call_next` 가 예외로 끝난 요청은 기록되지 않습니다.
- 조회 API 는 `/api/v1/home/access-logs` 계열 5개(전부 읽기 세션)이고, 예시 Celery 태스크
  `home.aggregate_access_stats` 가 통계를 집계합니다.

## 11. 인증 (JWT)

OAuth2 password flow + JWT access/refresh 토큰. 자격증명은 `user` 기능의 `User.hashed_password`(bcrypt)에
두고, `auth` 기능(`app/features/auth/`)은 인증 로직만, `app/utils/authenticator/auth.py` 는 해시·토큰
유틸을 맡습니다.

| 메서드·경로 | 인증 | 요청 | 성공 | 실패 |
|---|---|---|---|---|
| `POST /api/v1/auth/register` | — | JSON (`username`·`email`·`password` 8~128자) | 201 | 409 중복 · 422 |
| `POST /api/v1/auth/login` | — | **form** (`username`·`password`) | 200 | 401 · 422 |
| `POST /api/v1/auth/refresh` | — | JSON (`refresh_token`) | 200 | 401 · 422 |
| `GET /api/v1/auth/me` | Bearer | — | 200 | 401 |

```bash
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer"}
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'
curl -X POST localhost:8000/api/v1/auth/refresh -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

| 설정 | 기본값 |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | 30 / 7 |
| `JWT_ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` — 교체 필수, 서로 다른 값 권장 |

- `refresh` 는 access·refresh 를 **둘 다** 새로 발급합니다(회전). 토큰에 종류가 들어 있어 access 를 refresh
  자리에 쓰면 거부됩니다. 비활성 사용자(`is_active=false`)는 로그인·재발급·`me` 에서 막힙니다.
- 서버 측 폐기 목록(logout·revoke)은 없습니다 — 유출된 refresh 토큰은 만료까지 유효합니다.
- **상수 시간 인증**: 사용자가 없어도 더미 해시로 bcrypt 검증을 수행해 응답 시간으로 사용자명 존재를
  알아낼 수 없게 합니다. **논블로킹 해싱**: bcrypt 는 `asyncio.to_thread` 로 돌립니다.
- `get_current_user` 는 읽기 세션을 씁니다. 다른 기능의 엔드포인트에는 인증이 자동으로 붙지 않으므로
  필요하면 `Depends(get_current_user)` 와 소유권·역할 검사를 직접 둡니다.

## 12. SQLAdmin

```text
main.py (ADMIN=true)
  └─ register_admin(app, engine)          app/features/admin.py — main 이 아는 유일한 이름
       ├─ create_admin_interface(...)     Admin(app, engine, title=...) 생성 = /admin 마운트
       └─ register_admin_views(admin)     ADMIN_VIEWS 를 선언 순서대로 add_view
```

- 세 함수는 SQLAdmin 공식 API 가 아니라 이 프로젝트의 조립 함수입니다. 생성 쪽은 앱·엔진(과 향후 인증
  백엔드 — `Admin` 생성 인자라 여기에만 넣을 수 있다)을, 등록 쪽은 뷰 목록만 압니다. 회귀 가드:
  `tests/test_admin_wiring.py`.
- ModelView 는 기능이 소유합니다(`app/features/<name>/admin.py` 의 `admin_views`). 취합은 **명시 import**
  입니다 — 예전의 `getattr(module, "admin_views", [])` 수집은 빈 `admin.py` 를 조용히 건너뛰었습니다.
  `ADMIN_VIEWS` 는 기능명 사전순이며 테스트가 순서까지 대조합니다. 모델이 있는 기능은 `admin.py` 를 가져야 합니다.
- 기능 `__init__.py` 로 `admin_views` 를 재노출하지 않습니다 — 재노출하면 라우터 import 만으로 sqladmin 이
  로드되어 `ADMIN=false` 가 "라우트만 안 붙임" 이 됩니다(`ADMIN=false` 미로드 검사).
- **`/admin` 에는 인증이 없습니다**(확정 정책, 로그인 화면 없음 — `/admin/login` 은 503). 운영 차단은
  [README 운영 배포 체크리스트](../../README.md#운영-배포-체크리스트)의 책임입니다.
- `User` 뷰는 `hashed_password` 를 목록·상세·폼·내보내기에서 제외하고 `can_create = False` 입니다
  (비밀번호 없이 만든 계정은 로그인할 수 없습니다). 이 제외 설정을 지우면 해시가 노출됩니다
  (`tests/core/test_admin_views.py`).

## 13. Celery

- 앱: `app/celery/app.py` 의 `celery_app` — broker·backend 모두 `REDIS_URL`, `include=["app.celery.tasks"]`,
  JSON 직렬화, `timezone=TIME_ZONE`, `enable_utc=False`, 빈 `beat_schedule`. 기능별 `worker/` 디렉터리는 없고
  모든 태스크를 `app/celery/tasks.py` 에 둡니다(예: `home.aggregate_access_stats`).
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
config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)
```

- URL: `ALEMBIC_DATABASE_URL` 이 있으면 그 값, 없으면 primary DSN 의 `+aiomysql` 을 `+pymysql` 로 바꾼 값.
  마이그레이션은 항상 primary 에서 실행합니다.
- revision 체인(단일 head, CI 가 확인): `f4adf0ae24ea`(baseline — 기존 5개 테이블) → `b2f1a9c0d3e4`
  (`users.hashed_password`) → `c3d5e7f9a1b2`(`catalog_products`) → `d4e6f8a0b2c3`(`sales_orders`) →
  `e5f7a9b1c4d5`(`sales_daily_snapshots`).
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
| 로그는 큐 + stdout/stderr, 파일 없음, 앱별 로거 없음 | event loop 비차단(NFR-009), 수집은 런타임 책임, 새 기능이 로깅 설정을 건드리지 않게 |
| 표준 라이브러리 우선 · 자원은 소유자가 닫는다 · 실패와 취소를 구분한다 · 테스트 없는 보장은 문서에 쓰지 않는다 | 종료 신뢰성 작업(REQ-010)의 원칙 |
| Redis 는 필수 startup 조건 | Celery broker 와 같은 서버가 준비됐는지 기동 시점에 드러낸다(REQ-011) |
| `/admin` 무인증 + `ADMIN=true` 기본값, 앱이 운영 조합을 막지 않음 | 개발 우선 템플릿. 차단 책임은 배포(C-8) |
| 응답 직렬화는 FastAPI 기본(Pydantic) | `ORJSONResponse` 는 이득이 없고 0.141 에서 deprecated. 제거 전후 응답 바이트 동일 확인 |
| 템플릿 프로필 분리(minimal/api-db/production) 보류 | 세 벌을 유지하는 비용이 크다. "무겁다" 는 피드백이 반복되면 선택 기능을 걷어내는 스크립트 쪽으로 재검토 |
| 라우트 검사는 `app.openapi()` 기준 | FastAPI 0.141 부터 `app.routes` 가 하위 라우터를 평탄화하지 않는다(`_IncludedRouter`) |

## 16. 변경 이력

현재 동작은 본문과 코드를 따릅니다. 아래는 전환 기록입니다.

| 날짜 | 변경 |
|---|---|
| 2026-06-23 | 기능 모델 레지스트리 아키텍처 도입, 이 문서 최초 작성. 곧이어 자동 발견을 제거하고 `app/apps.py` 수동 등록으로 전환 |
| 2026-07-01 | 표준 FastAPI 배선으로 전환 — `AppRegistry`·`bootstrap.create_app()`·`app/apps.py` 제거, 기능 `__init__.py` 가 `router` 공개 |
| 2026-08-10 | 외부 검수 후속: mypy 오류 해소, 트랜잭션 경계 회귀 테스트, 모델 import SSOT(`models_registry`), 조회 라우트 읽기 세션 전환, Alembic baseline 복구, FastAPI 0.115 → 0.141(커밋을 핸들러 본문으로 이동), `ORJSONResponse` 제거 |
| 2026-08-11 | `app/features/` 명칭 확정, SQLAdmin ModelView 를 기능 소유로 이전 + 명시 취합(`app/features/admin.py`), 중앙 목록 순회 → 명시 `include_router`, `scripts/new_app.py` 제거, 문서 드리프트 정정 |
| 2026-08-13 | ORM/Raw Repository 이원화(REQ-001): `app/core/resources.py`, 큐 기반 로깅, 모델 Mixin, `BaseRepository` 823→185줄, `RawRepositoryBase`, 참조 예제 `catalog`·`reports`, MySQL 8.4 통합 환경, OpenAPI 규칙 테스트 |
| 2026-08-20 | Raw 쓰기 예제(스냅샷 적재, ADR-010~013), 세션 옛 이름 제거, 게이트 요구 ID·INV-10 검사 |
| 2026-08-25 | 종료 조립을 `AsyncExitStack` → 평문 `try/finally`(ADR-016) — 이후 취소 안전성 손실이 확인됨 |
| 2026-08-27 | 종료 신뢰성(REQ-010): 중첩 `async with`(ADR-017), listener 프로세스 소유(ADR-018), `run_server(log_config=…)`(ADR-020), dictConfig 네이티브 큐(ADR-021), 신호 핸들러(ADR-022), lifespan 끝 flush(ADR-023), 실제 uvicorn 통합 테스트, `--mysql-required` |
| 2026-09-17 | Redis startup 검증과 종료 순서 확장(`_redis`), 가이드를 `docs/guides/` 로 이동, 착수 명세를 `docs/specs/` 로 추적, CI 에 Redis·MySQL job(ADR-024) |
| 2026-09-17 | 문서 재구성(ADR-025): README·ARCHITECTURE·DEVELOPMENT 3종으로 통합. QUICKSTART → README, LOGGING-AND-SHUTDOWN·서버 수명 HTML → 이 문서, ORM-RAW-WORKFLOW·개발 HTML·명세의 workflow-guide → DEVELOPMENT |
| 2026-09-17 | 문서 일관성(ADR-026): HTML 안내서 두 편(`server-lifecycle-guide.html`·`feature-development-guide.html`)과 명세 `workflow-guide.md` 복원, 통일 문서 배치. HTML 은 요약, 상세 표는 Markdown. `API_DESCRIPTION`·미사용 설정 설명·`requires-python>=3.13` 정합 |

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
| `ADMIN` | bool | `true` |
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
| `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` | 없음 | §9.3 |
| `LOG_SQL_ECHO_ENABLED` | `false` | §9.4 |
| `LOG_CONSOLE_ENABLED` | `true` | 코드가 읽지 않음 |
| `LOG_CONSOLE_FORMAT` | `[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}` | 코드가 읽지 않음 — 실제 포맷은 §9.2 |
| `LOG_DATE_FORMAT` | `%Y-%m-%d %H:%M:%S` | 코드가 읽지 않음 |

**MiddlewareSettings** — §10 표

**RedisSettings** — `REDIS_HOST`=`localhost`, `REDIS_PORT`=`6379`, `REDIS_DB`=`0`, `REDIS_PASSWORD`=없음
(`REDIS_URL` = `redis://[:비밀번호@]호스트:포트/DB`)

**JWTSettings** — §11 표

**ApiSettings** — `API_VERSION`=`v1` (소비 코드 없음)

**SessionSettings** — `SESSION_COOKIE_NAME`=`session`, `SESSION_SECRET_KEY`=(placeholder), `SESSION_EXPIRE_SECONDS`=`86400` (소비 코드 없음)

**SMTPSettings** — `SMTP_SERVER`=`localhost`, `SMTP_PORT`=`25`, `SMTP_USERNAME`=빈 값, `SMTP_PASSWORD`=빈 값,
`SMTP_FROM_EMAIL`·`SMTP_FROM_NAME`=없음, `SMTP_TLS`·`SMTP_SSL`=`false`(동시 true 거부) (소비 코드 없음)

**UploadSettings** — `UPLOAD_DIR`=`uploads`, `UPLOAD_IMAGE_SIZE_LIMIT`=`20`(MB), `UPLOAD_IMAGE_RESIZE`=`false`,
`UPLOAD_IMAGE_RESIZE_WIDTH`=`1200`, `UPLOAD_IMAGE_RESIZE_HEIGHT`=`2800`, `UPLOAD_IMAGE_QUALITY`=`85`(0~100),
`UPLOAD_ALLOWED_EXTENSIONS`=`[".jpg", ".jpeg", ".png", ".gif", ".webp"]` (소비 코드 없음)

파생 값(`MYSQL_URL`·`ALEMBIC_URL`·`MYSQL_REPLICA_URLS`·`replication_active`·`routing_mode`·`REDIS_URL`·유효 로그
레벨)은 필드가 아니라 `config.py` 의 property/메서드입니다.
