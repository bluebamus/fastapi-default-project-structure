# ORM/Raw Repository 고도화 설계 및 개발 작업 계획서

## 1. 목적

이 문서는 현재 프로젝트의 FastAPI 워크플로우를 유지하면서 다음 두 데이터 접근 방식을
동등한 품질로 지원하기 위한 설계와 실행 순서를 정의한다.

- SQLAlchemy ORM 모델을 사용하는 일반 CRUD
- SQL 문자열과 바인드 파라미터를 사용하는 Raw SQL 조회/변경

두 방식은 데이터 접근 구현만 달라야 한다. 라우터 취합, Dependency Injection, Service
유스케이스, 트랜잭션 경계, Pydantic 응답, OpenAPI/Scalar 문서화와 테스트 기준은 동일하다.

## 2. 현재 코드 기준 검토 결과

### 2.1 이미 충족하는 원칙

| 원칙 | 현재 상태 | 근거 |
|---|---|---|
| 공통 인프라는 `app/core`에 둔다 | 충족 | `db`, `middlewares`, `models`, `repositories`, `services` |
| ORM 저장소가 공통 Base를 사용한다 | 충족 | 모델 보유 기능의 Repository 5개가 모두 `BaseRepository` 상속 |
| 기능별 Dependency에서 세션과 Service를 조립한다 | 충족 | `get_<feature>_service`, `get_<feature>_service_readonly` |
| 버전별 View를 그룹 라우터가 취합한다 | 충족 | `api/routers/v1/*.py` → `api/routers/router.py` |
| 기능 라우터를 `main.py`가 최종 취합한다 | 충족 | 명시적 `app.include_router(..., prefix="/api")` |
| 쓰기 커밋은 응답 전 View에서 완료한다 | 충족 | `await service.commit()` 및 회귀 테스트 |
| 조회는 reader 세션을 사용한다 | 충족 | 현재 `get_read_session` 및 라우트 배선 테스트 |
| 공개 API View는 비동기 함수다 | 충족 | 검사한 path operation 31개가 모두 `async def` |
| DB I/O는 비동기 driver/session을 사용한다 | 충족 | `AsyncEngine`, `AsyncSession`, aiomysql |
| 고비용 비밀번호 해싱은 event loop 밖에서 실행한다 | 충족 | bcrypt 전체 호출을 `asyncio.to_thread()`로 격리 |

### 2.2 보강해야 하는 항목

1. `repository_base.py`가 1,012줄이며 서로 다른 책임이 한 클래스에 집중되어 있다.
   기본 CRUD, eager loading, 부분 컬럼, join, batch, bulk, upsert를 분류하고 공개 계약을
   줄여야 한다.
2. `crud_base.py`는 네 개의 protected 메서드만 제공한다. 이름은 CRUD Base이지만 실제
   공개 CRUD 계약은 대부분 `BaseRepository`에 있어 책임 경계가 불명확하다.
3. `BaseRepository.create()`가 전달받은 `dict`에 `id`를 직접 추가한다. 호출자 데이터의
   변경을 피하고 모델 기본값에 ID 생성을 맡겨야 한다.
4. 제네릭 Base가 모든 모델에 문자열 `id`가 있다고 가정한다. 이 불변식을 타입과 모델
   상속 정책으로 명확히 강제하거나, PK 추상화를 도입해야 한다.
5. 관계와 컬럼을 문자열로 받는 고급 API는 오타를 실행 시점에만 발견한다. 기능별
   Repository가 SQLAlchemy 속성을 사용하도록 공개 API를 좁히는 편이 안전하다.
6. `exists`가 `COUNT(*)`를 사용한다. 존재 확인에는 SQL `EXISTS`가 의도와 성능에 더 맞다.
7. Bulk/update/delete의 DB 예외 변환 정책이 메서드마다 일관되지 않다.
8. 모든 기능 모델이 `Base`를 상속하지만 `UUIDMixin`, `TimestampMixin`을 실제로 사용하지
   않고 `id`, `created_at`을 반복 정의한다. `models_base.py`가 공통 모델 정책의 SSOT가
   되지 못하고 있다.
9. Raw SQL용 공통 실행 계층, 결과 타입, 예외 변환, 파라미터 바인딩 규칙과 테스트가 없다.
10. `tags_metadata.py`에는 구현 완료 기능이 여전히 “미구현/예정”으로 설명되고 `Auth`
    태그가 없다. 실제 라우터 태그와의 정합성 테스트가 필요하다.
11. 다수 Pydantic 필드에 설명은 있으나 요청/응답 예시와 상태 코드 문서 기준은 일관되지
    않다.
12. production/staging 파일 로그가 `RotatingFileHandler`에서 요청 event loop thread의
    동기 파일 write/flush/rotation으로 실행된다. console 출력도 동일한 동기 handler다.
13. `BackgroundTaskRunner.drain()`은 timeout 후 pending task를 취소하거나 다시 await하지
    않아 DB engine dispose 이후에도 task가 실행될 수 있다.
14. Celery worker의 영속 event loop와 background DB engine pool은 worker 종료 signal에서
    dispose/close되지 않는다. FastAPI lifespan은 Celery worker에서 실행되지 않는다.

## 3. 워크플로우 해석 보정

요청 원칙 8번의 “비즈니스 코드는 View에서 실행한다”는 다음과 같이 해석한다.

> View가 주입받은 Service의 비즈니스 유스케이스를 호출해 실행한다. 비즈니스 규칙 자체는
> Service에 작성하고, SQL은 Repository에만 작성한다.

비즈니스 규칙을 View 본문에 직접 작성하면 현재 프로젝트의 계층 계약과 테스트 가능성이
무너진다. View의 책임은 아래로 제한한다.

- HTTP 입력 수신 및 FastAPI 파라미터 선언
- 주입된 Service 유스케이스 호출
- 쓰기 성공 시 응답 전 `await service.commit()`
- ORM 또는 Raw 결과를 Pydantic 응답으로 변환
- HTTP 상태, 응답 모델, 오류 응답 및 OpenAPI 메타데이터 선언

## 4. 목표 아키텍처

```text
HTTP Request
  -> versioned View
  -> FastAPI Dependency
       -> 현재 get_session/get_read_session
       -> 목표 get_writer_db_session/get_read_only_db_session
       -> ORM Service 또는 Raw Service 구성
  -> Service: 비즈니스 유스케이스
  -> Repository: 데이터 접근
       -> BaseRepository -> CRUDBase              (ORM)
       -> RawRepositoryBase -> RawCRUDBase         (Raw SQL)
  -> AsyncSession / DatabaseRouter
  -> Pydantic Response DTO
  -> OpenAPI JSON
  -> Scalar
```

JWT는 프로젝트의 향후 기본 인증 방식이지만 이번 작업에서는 신규 적용하거나 확장하지
않는다. 기존 인증 동작의 회귀만 보호하며 token rotation, revoke/logout과 권한 정책은 별도
후속 작업으로 분리한다.

### 4.1 공통 불변식

- View는 `AsyncSession`을 직접 받거나 SQL을 실행하지 않는다.
- Service는 SQL을 작성하지 않는다.
- Repository는 HTTP 객체와 Pydantic 응답 모델을 알지 않는다.
- Base Repository는 `commit()`하지 않고 필요한 경우 `flush()`만 수행한다.
- GET/HEAD 조회는 `get_read_only_db_session`, 쓰기 또는 조회 후 쓰기는
  `get_writer_db_session`을 사용한다.
- 쿼리 종류에 따른 동적 라우팅이 반드시 필요한 승인된 경로에서만
  `get_routed_db_session`을 사용한다.
- SQLAlchemy 세션을 나타내는 Dependency 인자와 애플리케이션 계층 속성은
  `db_session`으로 명명한다.
- 쓰기 View는 성공 응답을 만들기 전에 정확히 한 번 커밋한다.
- Raw SQL은 반드시 `sqlalchemy.text()`와 named bind parameter를 사용한다.
- 테이블명, 컬럼명, 정렬 방향처럼 바인딩할 수 없는 식별자는 사용자 입력을 직접
  보간하지 않고 코드 allowlist로 선택한다.
- Raw 결과는 `RowMapping`을 Service에서 Pydantic DTO로 검증해 반환한다.

## 5. ORM Base 재설계

### 5.1 `models_base.py`

확정 공통 모델 계층은 다음과 같다.

```python
class Base(DeclarativeBase): ...

class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(...)

class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(...)

class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(...)

class UUIDTimestampModel(
    Base,
    UUIDPrimaryKeyMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
):
    __abstract__ = True

class UUIDCreatedModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __abstract__ = True
```

정책은 작은 Mixin 분리로 확정한다. 변경 가능한 엔티티는 `UUIDTimestampModel`, 접속 로그
같은 불변 모델은 `UUIDCreatedModel`을 사용한다. 외부 PK 모델은 시간 Mixin만 조합한다.
Mixin 전환 후 기존 schema diff가 없어야 한다.

### 5.2 `crud_base.py`

ORM 인스턴스의 최소 영속성 primitive만 담당한다.

```text
CRUDBase[ModelT]
  session
  model
  _get(pk)
  _add(entity)
  _delete(entity)
  _flush()
  _refresh(entity)
```

`_update()`가 `_add()`를 그대로 호출하는 현재 구조는 의미가 불명확하므로 제거하거나
명시적인 `flush/refresh`로 바꾼다. `commit/rollback`은 두지 않는다.

### 5.3 `repository_base.py`

일반 ORM Repository가 공통으로 쓸 안정적인 공개 API만 둔다.

```text
BaseRepository[ModelT, PrimaryKeyT]
  create(data)
  get_by_id(pk)
  get_by_id_or_raise(pk)
  list(offset, limit)
  count(filters)
  exists(filters)
  update_by_id(pk, changes)
  delete_by_id(pk)
```

PK 제네릭은 정식 계약으로 도입한다. 현재 문자열 UUID Repository도
`BaseRepository[ModelT, str]`을 명시하며 정수·외부 PK 모델을 허용한다.

공개 Base API는 위의 최소 CRUD로 확정한다. eager loading, join, partial column, batch와
aggregation은 기능별 Repository로 이동하고, 두 개 이상의 실제 기능에서 같은 구현이
확인된 경우에만 별도 Mixin으로 추출한다.

호환성을 위해 기존 공개 메서드를 즉시 삭제하지 않는다. 사용처와 테스트를 먼저 조사하고
deprecated wrapper → 호출부 전환 → 제거 순서로 진행한다.

## 6. Raw SQL Base 설계

### 6.1 `raw_crud_base.py`

SQL 실행 primitive와 결과 형태 변환만 담당한다.

```python
class RawCRUDBase:
    def __init__(self, db_session: AsyncSession) -> None: ...

    async def _fetch_one(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> RowMapping | None: ...

    async def _fetch_all(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Sequence[RowMapping]: ...

    async def _fetch_scalar(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Any: ...

    async def _execute(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> int: ...
```

설계 제약:

- 입력은 문자열이 아니라 사전에 만든 `TextClause`를 기본으로 한다.
- 반환은 ORM 객체가 아닌 `RowMapping`, scalar, affected row count다.
- SQL을 임의로 조합하는 public `execute(sql: str)` 만능 메서드는 제공하지 않는다.
- 예외를 삼키거나 커밋하지 않는다.

### 6.2 `raw_repository_base.py`

Raw Repository의 공통 정책을 담당한다.

```text
RawRepositoryBase -> RawCRUDBase
  fetch_one(..., *, query_name)
  fetch_all(..., *, query_name)
  fetch_scalar(..., *, query_name)
  execute(..., *, query_name)
  DatabaseException 변환
  공통 로깅(쿼리 이름, 소요 시간; 민감 파라미터 제외)
```

도메인 SQL은 Base 파일에 넣지 않는다. 기능별 Repository가 안정적인 상수 형태의 쿼리
이름과 SQL을 소유하고 Base에 `query_name`을 명시적으로 전달한다.

```python
class SalesReportRawRepository(RawRepositoryBase):
    async def daily_summary(self, start: date, end: date):
        stmt = text("""SELECT ... WHERE created_at >= :start AND created_at < :end""")
        return await self.fetch_all(
            stmt,
            {"start": start, "end": end},
            query_name="sales_report.daily_summary",
        )
```

## 7. 시나리오 기반 예제 범위

### 7.1 ORM 시나리오: 상품 카탈로그 CRUD

- `Product` ORM 모델
- 생성, 목록, 단건, 부분 수정, 삭제
- `ProductRepository(BaseRepository[Product, str])`
- `ProductService`
- read-only/writer DB session Dependency 분리
- `v1/products.py`와 그룹 `router.py`
- Scalar 요청/응답 및 오류 문서
- Repository 단위 테스트, Service 테스트, API 통합 테스트, 트랜잭션 테스트

### 7.2 Raw 시나리오: 일별 매출 리포트

- 기존 주문 테이블을 집계하되 결과용 ORM 모델은 만들지 않음
- `SalesReportRawRepository(RawRepositoryBase)`
- named parameter가 적용된 집계 SQL
- `SalesReportService`
- read-only Dependency
- `v1/sales_reports.py`와 동일한 그룹 `router.py`
- `DailySalesItem`, `DailySalesReportResponse` Pydantic DTO
- SQL injection 방지, mapping 변환, reader routing, API 계약 테스트

### 7.3 Raw 쓰기 보조 시나리오

Raw 조회만 구현하면 트랜잭션 규칙이 검증되지 않는다. 별도 테스트 fixture에서 Raw update를
한 건 포함해 다음을 검증한다.

- Repository는 flush/execute까지만 수행
- 쓰기 View가 정확히 한 번 커밋
- 예외 시 commit 없음
- read-only 세션에서 DML 실행 시 `ReadOnlyRoutingError`

## 8. Scalar/OpenAPI 문서 기준

ORM 모델은 DB 매핑 정보이며 Scalar의 직접 계약이 아니다. 문서 계약은 다음 순서로 관리한다.

1. View: `summary`, `description`, 고유 `operation_id`, `response_model`, `responses`, 상태 코드
2. Path/Query/Header: 설명, 제약, 예시
3. Pydantic 요청/응답: `Field` 설명·제약·예시, `json_schema_extra`
4. Router: 실제 `tags=[...]`
5. `tags_metadata.py`: 태그 설명과 표시 순서
6. 보안 적용 시 FastAPI `Security` 스키마

ORM 컬럼의 comment/info는 DB와 내부 개발 문서에는 유용하지만 Pydantic 응답 문서를
대체하지 않는다. Raw 결과도 Pydantic DTO가 없으면 안정적인 OpenAPI 계약을 만들 수 없다.

추가 자동 검증:

- 모든 API operation에 고유 `operationId`가 있는지 검사
- 라우터 태그와 `tags_metadata` 집합 비교
- 모든 2xx 응답에 `response_model`이 있는지 검사(204 제외)
- 주요 요청/응답 스키마에 예시가 있는지 검사
- 규칙 기반 OpenAPI contract 검사와 상품·매출 핵심 schema snapshot

## 9. Lifespan 및 애플리케이션 자원 관리 설계

### 9.1 현재 상태와 보강 필요성

현재 `main.py`의 `lifespan`이 다음 작업을 직접 수행한다.

- `DEBUG=True`일 때 `create_db_tables()` 실행
- 종료 시 `access_log_tasks.drain()`
- writer, reader, background DB engine dispose

DB 엔진은 `app/core/db/session.py` import 시 생성되며 실제 연결은 pool이 처음 사용될 때
열린다. FastAPI API 프로세스가 소유한 Redis client는 현재 없다. Redis API client/cache와
readiness 연계는 JWT와 함께 후속 작업으로 분리한다. 현재 Celery broker/backend에 사용되는
Redis 설정은 기존 동작으로 유지하며 Celery worker 프로세스가 관리한다.

보강할 문제는 다음과 같다.

1. 모델이 하나도 없어도 `create_all()` 경로가 DB 연결을 시도할 수 있다.
2. startup 중간 실패 시 이미 생성된 자원의 정리가 하나의 경로로 보장되지 않는다.
3. 백그라운드 태스크 drain과 DB/logging 종료 순서를 하나의 계약으로 관리해야 한다.

### 9.2 단순한 목표 구조

일반적인 FastAPI `asynccontextmanager` 패턴을 사용하고 범용 플러그인 registry는 만들지
않는다.

```text
main.lifespan
  -> async with manage_application_resources(app)
       startup
         1. logging queue/listener 시작 및 app.state.resources에 저장
         2. 모델 모듈 import
         3. Base.metadata의 실제 테이블 수 확인
         4. 개발 자동 생성 정책 ON + 테이블 1개 이상이면 create_all
       yield
       shutdown/failure cleanup
         1. 신규 요청 종료 후 in-flight background task drain
         2. DB writer/reader/background engine dispose
         3. logging queue flush 및 listener stop
```

권장 파일은 하나만 추가한다.

```text
app/core/resources.py
  ApplicationResources
  manage_application_resources(app)
```

목표 인터페이스:

```python
@dataclass(slots=True)
class ApplicationResources:
    log_listener: QueueListener | None = None


@asynccontextmanager
async def manage_application_resources(
    app: FastAPI,
) -> AsyncIterator[ApplicationResources]:
    resources = ApplicationResources()
    app.state.resources = resources
    try:
        async with AsyncExitStack() as cleanup:
            resources.log_listener = build_queue_listener()
            resources.log_listener.start()
            # 먼저 등록하므로 shutdown에서 가장 마지막에 실행한다.
            cleanup.push_async_callback(
                stop_log_listener_async,
                resources.log_listener,
            )

            cleanup.push_async_callback(dispose_engine)

            imported = import_all_models()
            table_count = len(Base.metadata.tables)
            if app_settings.DEBUG and table_count > 0:
                await create_db_tables(import_models=False)

            # 마지막 등록이므로 shutdown에서 DB보다 먼저 drain된다.
            cleanup.push_async_callback(access_log_tasks.drain)
            yield resources
    finally:
        # 닫힌 client를 다음 lifespan/test가 재사용하지 않도록 참조도 제거한다.
        app.state.resources = None
```

`QueueListener.stop()`과 flush/join은 동기 작업이므로 `stop_log_listener_async()`는 이를
`await asyncio.to_thread(...)`로 실행한다. 이로써 shutdown 중 event loop를 직접 막지 않고,
DB dispose가 남기는 마지막 로그까지 listener가 처리한 뒤 종료한다.

`main.py`의 lifespan은 조립만 담당한다.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app):
        yield
```

실제 구현에서는 `create_db_tables()`가 모델을 다시 import하지 않도록 인자를 추가하거나,
`prepare_models()`와 `create_registered_tables()`로 책임을 나눈다. 같은 startup에서 모델
탐색을 두 번 수행하지 않는다.

### 9.3 테이블 생성 정책

모델 존재 여부는 파일 존재가 아니라 모델 import 후 `Base.metadata.tables`의 실제 개수로
판정한다. `models/models.py` 파일이 비어 있거나 추상 모델만 있으면 생성하지 않는다.

```text
table_count == 0
  -> DB 연결과 create_all을 시도하지 않음

table_count > 0 and DEBUG == true
  -> 개발 편의를 위해 create_all 시도

table_count > 0 and DEBUG == false
  -> create_all 금지, Alembic migration 사용
```

운영에서 무조건 `create_all()`을 실행하지 않는다. `create_all()`은 기존 컬럼 변경과 삭제를
마이그레이션하지 못하며 migration history를 대체하지 못한다. 향후 `DEBUG`와 문서 활성화의
결합을 해제할 경우 `DB_CREATE_TABLES_ON_STARTUP` 같은 명시 설정으로 분리하되 운영 기본값은
`false`로 한다.

### 9.4 자원 소유권과 종료 의미

Resource Manager는 FastAPI API 프로세스가 만든 장기 수명 자원만 관리한다.

| 자원 | 소유자 | lifespan 책임 |
|---|---|---|
| writer/read/background DB engine | FastAPI process | 모든 pool dispose |
| in-flight access log task | FastAPI process | 외부 연결 종료 전에 drain |
| logging queue/listener | FastAPI process | queue drain 및 listener flush/stop |
| 요청별 AsyncSession | Dependency | 요청 종료 시 close/rollback |
| Celery broker/backend connection | Celery worker | FastAPI에서 관리하지 않음 |
| SQLAdmin | FastAPI app | 별도 네트워크 client가 없으면 close 없음 |

DB engine 객체와 sessionmaker 정의는 기존 Dependency 및 SQLAdmin 호환을 위해
`app/core/db/session.py`에 유지할 수 있다. 단, engine pool의 shutdown 소유자는 Resource
Manager 하나로 고정하고 다른 모듈이 별도 lifespan cleanup을 등록하지 않는다.

“자원 삭제”는 연결, pool, task 및 listener reference를 해제한다는 뜻이다. shutdown에서
DB table을 drop하지 않는다.

### 9.5 실패와 종료 정책

- 필수 자원 초기화 실패는 startup 실패로 처리한다.
- 선택 자원은 명시적 설정과 기능 요구가 있을 때만 생성한다.
- startup 중간 실패도 `finally` cleanup을 반드시 실행한다.
- background task를 먼저 drain하고 DB를 dispose한 후 logging queue/listener를 마지막에
  flush/stop한다.
- `AsyncExitStack`에 cleanup을 원하는 종료 순서의 역순으로 등록한다.
- 각 cleanup 실패는 로깅하되 ExitStack의 뒤 callback cleanup을 건너뛰지 않도록 구현한다.
- FastAPI shutdown은 background task 5초, DB dispose 10초, logging drain 5초, 전체 20초
  timeout을 사용한다. Celery worker cleanup은 별도 프로세스에서 10초를 사용한다.
- 같은 프로세스에서 lifespan은 1회 실행을 기본으로 하되 테스트에서 startup/shutdown
  재진입 후 누수가 없는지 확인한다.
- cleanup 후 `app.state.resources`의 닫힌 client 참조를 제거한다.
- multi-worker 배포에서는 worker마다 독립적인 pool/client가 생성·해제됨을 문서화한다.

### 9.6 추가 보강 워크플로우

1. **Liveness와 readiness 분리**: `/health`는 외부 연결을 검사하지 않는다. `/ready`는
   writer DB에서 `SELECT 1`을 최대 2초 안에 실행하며 성공 시 200, 오류·timeout 시 내부
   정보를 숨긴 503을 반환한다. Redis는 후속 도입 시 별도 정책으로 추가한다.
2. **선택 자원 명시화**: 설정만 존재한다는 이유로 연결하지 않는다. API 코드가 실제로
   사용하는 자원만 startup에서 생성한다.
3. **자원 접근 방식 통일**: 장기 수명 client는 `app.state.resources`에 두고 Dependency로
   제공한다. 기능 모듈에서 새 전역 client를 만들지 않는다.
4. **startup에서 장시간 업무 금지**: migration, 대량 seed, 캐시 warm-up은 배포 job으로
   분리한다. lifespan에는 짧고 결정적인 초기화만 둔다.
5. **설정 검증 선행**: URL, pool 수, 필수 secret과 환경 조합은 네트워크 연결 전에
   Pydantic Settings에서 fail-fast한다.
6. **자원 예산 검수**: worker 수 × writer/read/background pool 크기를 계산해 DB 최대
   연결 수를 넘지 않도록 배포 문서에 명시한다.
7. **관측성**: startup/shutdown 단계, 모델/테이블 수, 자원별 성공·실패·소요 시간을
   구조화 로그로 남기고 secret/DSN password는 기록하지 않는다.

### 9.7 비동기 실행 모델 검수 및 보강

비동기 적용 기준은 “모든 함수를 `async def`로 만든다”가 아니다. 다음과 같이 분류한다.

| 작업 | 현재 판정 | 목표 |
|---|---|---|
| FastAPI View/Dependency/Service | async 충족 | 유지 |
| ORM DB I/O | async 충족 | 유지 |
| bcrypt | thread offload 충족 | 유지 |
| User-Agent 파싱 | 짧은 CPU 작업 | 동기 유지, 성능 회귀 시 재측정 |
| JWT/Pydantic/모델 변환 | 짧은 CPU 작업 | 동기 유지 |
| `run_sync(create_all)` | SQLAlchemy async bridge | 유지 |
| API/uvicorn 로그 출력 | 동기 I/O | queue worker로 분리 |
| access log background task | async이나 timeout cleanup 불완전 | cancel + await 보강 |
| Celery task | worker 계약은 sync, 내부 DB는 async | worker shutdown cleanup 추가 |

#### Queue 기반 non-blocking logging

Python 표준 logging handler에는 await 기반 파일 API가 없다. `aiofiles`로 custom handler를
만들기보다 일반적으로 사용하는 `QueueHandler`/`QueueListener` 패턴을 적용한다.

```text
request event loop
  -> QueueHandler.emit(record)       # 메모리 queue 적재
  -> QueueListener thread
       -> stdout/stderr StreamHandler
       -> container/runtime log collector
```

구현 원칙:

- 애플리케이션의 root logger에는 `QueueHandler`만 연결한다.
- stdout/stderr handler는 `QueueListener`가 소유한다.
- 가능한 범위에서 uvicorn logger도 같은 queue 기반 출력 경로를 사용한다.
- listener는 Resource Manager startup에서 시작하고 shutdown에서 stop/flush한다.
- listener stop은 background task drain과 DB dispose가 끝난 후 마지막에 수행한다.
- listener의 flush/join은 `asyncio.to_thread()`로 event loop 밖에서 실행한다.
- worker별 queue 크기는 10,000건이며 `put_nowait()`만 사용한다.
- 포화 시 DEBUG/INFO/WARNING은 drop하고 counter와 rate-limited 관측 신호를 남긴다.
- 포화 시 ERROR/CRITICAL은 logging API를 재호출하지 않는 최소 stderr fallback을 사용한다.
- 정상 shutdown queue drain timeout은 5초다.
- logging thread 실패가 API 요청 실패로 전파되지 않도록 별도 오류 보고 경로를 둔다.

#### Logging queue 포화 정책

bounded queue가 가득 찼을 때의 선택지는 다음과 같다.

| 정책 | 장점 | 위험 |
|---|---|---|
| producer block | 로그 유실 최소화 | 요청 event loop가 멈춰 API latency와 가용성 저하 |
| 전 레벨 drop | 가장 단순하고 non-blocking | 장애 시 ERROR/CRITICAL까지 유실 |
| 레벨별 처리 | 일반 로그는 non-blocking, 오류 로그 보존 | fallback과 metric 구현 필요 |

적용 정책은 `put_nowait()` 기반 레벨별 처리로 확정한다. queue 포화 시
DEBUG/INFO/WARNING은 drop하고 누적 counter와 rate-limited metric을 남긴다.
ERROR/CRITICAL은 logging API를 다시
호출하지 않는 최소 포맷의 제한된 stderr fallback으로 기록해 재귀 logging을 방지한다.
fallback도 무기한 block해서는 안 된다.

운영 출력은 stdout/stderr와 외부 collector 방식으로 확정한다. production/staging의
애플리케이션 `RotatingFileHandler`와 파일 rotation 설정은 제거하고 Docker, Kubernetes 또는
운영 agent가 저장·검색·rotation을 담당한다. 각 worker는 독립 queue/listener를 가진다.

#### Background task timeout 처리

`drain()`은 timeout 후 남은 task를 그대로 두지 않는다.

```python
done, pending = await asyncio.wait(tasks, timeout=timeout)
for task in pending:
    task.cancel()
await asyncio.gather(*pending, return_exceptions=True)
```

완료 후 `_tasks`가 비어 있어야 하며, cancellation 중 session context가 rollback/close될
기회를 갖도록 취소한 task를 반드시 await한다. 그 다음 DB engine을 dispose한다.

#### Celery worker async bridge 종료

Celery task 함수가 동기인 것은 framework 실행 계약이므로 유지한다. 대신 process별 영속
event loop와 해당 loop에서 사용한 DB pool을 Celery worker signal로 정리한다.

```text
worker process init
  -> event loop는 첫 async task에서 lazy 생성

worker process shutdown
  -> loop.run_until_complete(dispose background worker resources)
  -> loop.run_until_complete(loop.shutdown_asyncgens())
  -> loop.close()
  -> global loop reference = None
```

FastAPI Resource Manager와 Celery worker cleanup은 서로 다른 프로세스 소유권이다. 공통
cleanup primitive는 재사용할 수 있지만 FastAPI lifespan에서 Celery 자원을 직접 닫지 않는다.

### 9.8 DB Session Dependency 명명 규칙

SQLAlchemy `AsyncSession`을 제공하는 함수는 일반적인 사용자 세션이나 HTTP 세션과
구분되도록 이름에 `db_session`을 포함한다.

| 현재 이름 | 목표 이름 | 계약 |
|---|---|---|
| `get_read_session` | `get_read_only_db_session` | 조회 전용 의도, router 활성 시 쓰기 차단 및 reader 선택 |
| `get_write_session` | `get_writer_db_session` | 첫 쿼리부터 primary writer에 고정 |
| `get_session` | `get_routed_db_session` | 구문에 따른 동적 reader/writer 선택이 필요한 예외 경로 |
| `get_background_session` | `get_background_db_session` | FastAPI DI에서 background 전용 pool 제공 |

요청 밖 async context manager인 `background_session()`도
`background_db_session()`으로 맞춘다. Dependency 인자, Service 및 Repository 생성자와
속성은 `session` 대신 `db_session`/`self.db_session`을 사용한다. SQLAlchemy 내부처럼
문맥이 완전히 명확한 짧은 지역 변수만 `session`을 허용한다.

기존 함수명은 즉시 삭제하지 않는다. 새 이름을 정식 API로 추가한 뒤 기존 이름을 deprecated
alias로 유지하고, 전체 호출부와 테스트 전환 후 별도 호환성 제거 단계에서 삭제한다.

## 10. 개발 단계

### Phase 0. 계약 고정

- 현재 Base Repository 공개 메서드 사용처 목록 작성
- 현재 API/OpenAPI snapshot과 201개 테스트를 기준선으로 저장
- ORM/Raw 공통 트랜잭션 규칙을 ADR 또는 아키텍처 문서에 확정
- DB session Dependency 정식 이름과 deprecated alias 제거 시점을 확정

완료 조건: 기존 동작을 바꾸는 항목과 호환 유지 항목이 명시된다.

### Phase 1. 비동기 Runtime 및 Lifespan Resource Manager

- `app/core/resources.py`와 `ApplicationResources` 추가
- 모델 import 후 실제 metadata table count 판정
- 모델 0개일 때 DB 접속/create_all 미시도 테스트
- startup 실패와 정상 shutdown의 동일 cleanup 경로 구현
- access log drain → DB engine dispose → logging listener flush/stop 순서 테스트
- production/staging logging을 bounded `QueueHandler`/`QueueListener` 구조로 전환
- worker별 queue 10,000건, 레벨별 drop/fallback과 drop counter 구현
- production/staging 애플리케이션 파일 handler 제거 및 stdout/stderr 출력 통일
- QueueListener를 Resource Manager에서 시작·flush·종료
- drain timeout 후 pending task cancel + gather + 추적 집합 비우기
- Celery worker shutdown signal에서 async generator, DB engine, event loop 종료
- 동기 유지 허용 작업(User-Agent/JWT/Pydantic/run_sync)의 근거를 회귀 문서에 고정
- `main.py` lifespan을 manager 호출만 남도록 단순화
- API Redis client/cache/readiness는 후속 작업으로 제외하고 기존 Celery Redis 설정만 유지
- DB session Dependency에 새 이름을 추가하고 기존 이름은 deprecated alias로 유지
- 쓰기 Dependency를 `get_writer_db_session`, 조회 Dependency를
  `get_read_only_db_session`으로 전환

완료 조건: lifecycle 조립이 한 함수로 집중되고 요청 event loop에서 동기 파일 로그 I/O가
제거되며, FastAPI와 Celery가 각자 소유한 task/loop/pool을 실패 경로에서도 해제한다.

### Phase 2. ORM 모델 기반 정리

- UUID/created/updated 책임이 분리된 Mixin과 조합 Base 구현
- 기존 모델을 작은 단위로 공통 믹스인으로 전환
- Alembic metadata/schema diff가 없어야 함
- 기존 API 응답이 변하지 않는지 검증

완료 조건: 반복 필드는 공통 정책으로 관리되고 DB 스키마 변경은 없다.

### Phase 3. ORM Repository 고도화

- `CRUDBase` primitive 책임 정리
- `BaseRepository[ModelT, PrimaryKeyT]`와 최소 공개 CRUD 계약 구현
- 입력 dict 불변, `exists`, PK typing, 예외 변환 개선
- 고급 메서드 사용처를 기능별 Repository로 이동
- 호환 wrapper를 통한 점진적 전환

완료 조건: 모든 기존 ORM Repository와 API 테스트가 통과하고 공개 계약 테스트가 추가된다.

### Phase 4. Raw 기반 클래스 구현

- `raw_crud_base.py`, `raw_repository_base.py` 추가
- `RowMapping` 반환, named binding, rowcount, 예외 변환 구현
- commit 금지와 read-only DML 차단 테스트
- 민감정보 없는 구조화 로그 기준 추가

완료 조건: Raw Base 단위 테스트가 DB별 차이에 독립적으로 통과한다.

### Phase 5. 두 예제 기능 구현

- ORM 상품 전체 CRUD(create/list/get/update/delete) 예제 추가
- Raw 일별 매출 리포트와 테스트용 Raw DML workflow 추가
- `catalog_products`와 Raw 원본 `sales_orders`를 실제 Alembic migration 두 개로 추가
- 각 migration에 명시적인 upgrade/downgrade와 migration chain 테스트 추가
- `compose.test.yaml`의 MySQL 구성을 로컬과 CI에서 동일하게 사용
- SQLite 단위 테스트와 별도로 MySQL Raw SQL 및 migration 통합 테스트 실행
- 동일한 라우터/Dependency/Service/트랜잭션 구조 적용
- 기능별 테스트와 라우터 등록 누락 테스트 확장

완료 조건: 사용자는 두 예제를 나란히 비교해 데이터 접근 방식만 교체할 수 있다.

### Phase 6. Scalar 문서 정비

- 오래된 `tags_metadata.py` 설명 수정 및 `Auth`/신규 예제 태그 추가
- Pydantic 예시와 오류 응답 보강
- 규칙 기반 OpenAPI 정합성 테스트와 핵심 schema snapshot 추가

완료 조건: Scalar에서 ORM/Raw 예제의 요청, 응답, 오류, 파라미터가 완결되어 보인다.

### Phase 7. 문서 및 최종 검수

- 개발 지침서와 실제 코드 경로·시그니처 대조
- README/ARCHITECTURE/QUICKSTART 업데이트
- 전체 품질 게이트 실행

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
```

## 11. 테스트 매트릭스

| 계층 | ORM | Raw |
|---|---|---|
| Base 단위 | CRUD, PK, flush, 예외 | binding, one/all/scalar, rowcount, 예외 |
| Repository | 모델/관계 쿼리 | SQL 결과 mapping, injection 방지 |
| Service | 비즈니스 규칙 | 집계 규칙, DTO 검증 |
| Dependency | read-only/writer DB session 선택 | read-only/writer DB session 선택 |
| View | 요청/응답/오류/commit | 요청/응답/오류/commit |
| Router | 버전·그룹 prefix | 버전·그룹 prefix |
| OpenAPI | ORM DTO schema | Raw DTO schema |
| 회귀 | 기존 API/DB schema 불변 | reader routing, DML 차단 |
| Lifespan | 모델 유/무, startup 실패 cleanup | 자원 close 순서, 재진입 누수 |
| 비동기 runtime | Queue logging, task cancel/await | Celery loop/pool shutdown |

## 12. 비목표

- View에서 SQL 직접 실행
- Raw SQL 결과를 검증 없이 `dict`로 반환
- 자동 라우터/Repository 탐색
- Base 클래스에서 도메인 전용 쿼리 제공
- Repository 내부 commit
- 문자열 포매팅으로 SQL 값 또는 식별자 삽입
- ORM과 Raw Repository를 하나의 만능 클래스로 통합
- shutdown에서 DB table drop
- FastAPI process가 소유하지 않은 Celery worker 연결 종료
- API Redis client/cache/readiness 구현
- 짧은 CPU 연산까지 무조건 `to_thread()`로 전환
- Celery 동기 task wrapper를 근거 없이 async 함수로 변경
- JWT 인증 정책 및 access/refresh token lifecycle 구현

## 13. 최종 완료 기준

- ORM과 Raw 경로가 동일한 계층 및 트랜잭션 규칙을 따른다.
- 모든 ORM 기능 Repository가 ORM Base 계층을 사용한다.
- 모든 Raw 기능 Repository가 Raw Base 계층을 사용한다.
- ORM Base와 Raw Base 사이에 상속 관계는 없고 세션·예외 정책만 평행하게 유지한다.
- View/Service/Repository 책임을 위반하는 SQL 또는 비즈니스 규칙이 없다.
- lifespan이 manager 함수 하나로 자원을 초기화·해제하고 모델이 없으면 DB 테이블 생성을
  시도하지 않는다.
- startup 실패와 shutdown 모두 background task와 외부 연결을 누수 없이 정리한다.
- API logging이 event loop에서 직접 파일 write/rotation을 수행하지 않는다.
- drain timeout 후 남은 task가 취소·await되고 Celery worker loop/pool도 종료된다.
- Scalar 문서에서 두 예제의 계약이 완전하고 태그가 실제 라우터와 일치한다.
- 전체 테스트, Ruff, format check, mypy가 통과한다.
