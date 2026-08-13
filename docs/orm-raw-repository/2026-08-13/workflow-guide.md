# ORM/Raw 공통 워크플로우 개발 지침서

## 1. 적용 원칙

ORM과 Raw SQL은 Repository 구현에서만 갈라진다.

```text
View -> Dependency -> Service -> Repository -> AsyncSession
```

| 계층 | 해야 하는 일 | 하지 않는 일 |
|---|---|---|
| View | HTTP 계약, Service 호출, 응답 변환, 쓰기 commit | SQL, 도메인 규칙 |
| Dependency | session 선택, 객체 조립 | 비즈니스 실행, commit |
| Service | 유스케이스와 비즈니스 규칙 | HTTP 객체, SQL 문자열 |
| Repository | ORM/Raw 데이터 접근 | commit, HTTP 응답 생성 |
| Schema | 입력 검증과 출력 계약 | DB 세션 접근 |

## 2. 공통 디렉터리 구조

```text
app/
├── core/
│   ├── db/
│   ├── middlewares/
│   ├── models/models_base.py
│   ├── repositories/
│   │   ├── crud_base.py
│   │   ├── repository_base.py
│   │   ├── raw_crud_base.py
│   │   └── raw_repository_base.py
│   ├── services/services_base.py
│   └── tags_metadata.py
└── features/<feature>/
    ├── api/routers/
    │   ├── router.py
    │   └── v1/<view>.py
    ├── dependencies/<feature>_dependencies.py
    ├── models/models.py                  # ORM 기능만
    ├── repositories/<name>_repository.py
    ├── schemas/<feature>_schema.py
    ├── services/<feature>_service.py
    └── tests/
```

Raw 조회 전용 기능은 결과용 ORM 모델을 만들지 않는다. DB 테이블의 생명주기를 이
프로젝트가 관리한다면 테이블 ORM 모델과 Alembic migration은 별개로 필요할 수 있다.

### 2.1 DB Session 명명 규칙

애플리케이션 계층에서는 SQLAlchemy 세션임을 이름으로 명확히 표현한다.

| 용도 | 정식 Dependency | 사용 기준 |
|---|---|---|
| 순수 조회 | `get_read_only_db_session` | GET/HEAD 및 변경 없는 조회 |
| 쓰기·조회 후 쓰기 | `get_writer_db_session` | 첫 쿼리부터 primary writer 고정 |
| 동적 라우팅 | `get_routed_db_session` | 명시적으로 승인된 특수 경로만 사용 |
| Background DI | `get_background_db_session` | background 전용 pool 사용 |
| 요청 밖 context | `background_db_session` | Celery 및 fire-and-forget 작업 |

Dependency 인자와 Service/Repository 생성자 및 속성은 `db_session`과
`self.db_session`을 사용한다. 기존 `get_session`, `get_read_session`,
`get_write_session`, `get_background_session`, `background_session`은 마이그레이션 기간의
deprecated alias이며 신규 코드에서는 사용하지 않는다.

JWT는 향후 기본 인증 방식으로 적용하지만 이 지침의 현재 구현 범위에는 포함하지 않는다.
기존 인증 회귀만 보호하며 token lifecycle과 권한 정책은 별도 후속 명세로 관리한다.

## 3. ORM 시나리오: 상품 CRUD

아래 코드는 확정된 목표 Base 시그니처를 기준으로 한 예시다.

### 3.1 ORM 모델

```python
# app/features/catalog/models/models.py
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDTimestampModel


class Product(UUIDTimestampModel):
    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="상품명")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="판매가")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

모델 원칙:

- 공통 PK와 시간 필드는 프로젝트 믹스인을 사용한다.
- 변경 가능한 모델은 UUID/created/updated 조합 Base를 사용하고 불변 로그는 updated를 제외한다.
- DB 제약은 ORM 컬럼에 선언한다.
- API 설명은 Pydantic Schema에도 별도로 선언한다.
- `__tablename__`, nullability, index, unique, FK를 명시한다.

Alembic migration은 예제 구현과 함께 실제 revision으로 추가한다.

```text
migrations/versions/<revision>_add_catalog_products.py
migrations/versions/<revision>_add_sales_orders.py
```

`catalog_products`는 `Product` ORM 모델과 metadata가 일치해야 한다. `sales_orders`는 Raw SQL
원본 테이블이며 결과 전용 ORM 모델은 만들지 않는다. 두 revision은 upgrade와 downgrade를
모두 구현하고 기존 Alembic head부터 순차 적용·전체 rollback·재적용을 MySQL에서 검증한다.

### 3.2 Pydantic Schema

```python
# app/features/catalog/schemas/catalog_schema.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Mechanical Keyboard", "price": "129.00"}]
        }
    )

    name: str = Field(min_length=1, max_length=200, description="상품명")
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="판매가")


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="상품 UUID")
    name: str = Field(description="상품명")
    price: Decimal = Field(description="판매가")
    is_active: bool = Field(description="판매 활성 여부")


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int = Field(ge=0, description="전체 상품 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
```

### 3.3 ORM Repository

```python
# app/features/catalog/repositories/product_repository.py
from app.core.repositories.repository_base import BaseRepository
from app.features.catalog.models.models import Product


class ProductRepository(BaseRepository[Product, str]):
    model = Product
```

공통 CRUD로 표현할 수 없는 조회만 명시적인 도메인 메서드로 추가한다.

```python
async def list_active(self, *, skip: int, limit: int):
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return (await self.db_session.execute(stmt)).scalars().all()
```

### 3.4 Service

```python
# app/features/catalog/services/catalog_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate


class CatalogService(BaseService):
    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = ProductRepository(db_session)

    async def create_product(self, payload: ProductCreate):
        return await self.repository.create(payload.model_dump())

    async def list_products(self, *, skip: int, limit: int):
        items = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return items, total
```

가격 정책, 상태 전환, 중복 판정 등은 이 계층에 둔다.

### 3.5 Dependency

```python
# app/features/catalog/dependencies/catalog_dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.catalog.services.catalog_service import CatalogService


async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(db_session)


async def get_catalog_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    return CatalogService(db_session)
```

Dependency는 조립만 한다. `yield` 이후 commit하거나 Service 메서드를 미리 실행하지 않는다.

### 3.6 Versioned View

```python
# app/features/catalog/api/routers/v1/products.py
from fastapi import APIRouter, Depends, Query, status

from app.features.catalog.dependencies.catalog_dependencies import (
    get_catalog_service,
    get_catalog_service_readonly,
)
from app.features.catalog.schemas.catalog_schema import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
)
from app.features.catalog.services.catalog_service import CatalogService

router = APIRouter()


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="상품 생성",
    description="판매할 상품을 생성합니다.",
    operation_id="createProduct",
)
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.create_product(payload)
    await service.commit()
    return ProductResponse.model_validate(product)


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="상품 목록 조회",
    description="상품을 페이지 단위로 조회합니다.",
    operation_id="listProducts",
)
async def list_products(
    skip: int = Query(0, ge=0, description="건너뛸 상품 수"),
    limit: int = Query(50, ge=1, le=100, description="조회할 상품 수"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductListResponse:
    items, total = await service.list_products(skip=skip, limit=limit)
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )
```

## 4. Raw 시나리오: 일별 매출 리포트

### 4.1 Raw Base 사용 계약

```python
# 목표 인터페이스 예시
class RawCRUDBase:
    async def _fetch_all(self, statement: TextClause, params=None): ...
    async def _fetch_one(self, statement: TextClause, params=None): ...
    async def _fetch_scalar(self, statement: TextClause, params=None): ...
    async def _execute(self, statement: TextClause, params=None) -> int: ...


class RawRepositoryBase(RawCRUDBase):
    async def fetch_all(self, statement: TextClause, params=None, *, query_name: str): ...
    async def fetch_one(self, statement: TextClause, params=None, *, query_name: str): ...
    async def fetch_scalar(self, statement: TextClause, params=None, *, query_name: str): ...
    async def execute(self, statement: TextClause, params=None, *, query_name: str) -> int: ...
```

### 4.2 Raw 결과 Schema

```python
# app/features/reports/schemas/report_schema.py
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date
    end_date: date
    items: list[DailySalesItem]
```

Raw 결과는 ORM 객체가 아니므로 `from_attributes=True`에 의존하지 않는다. `dict(row)`를
Pydantic으로 검증한다.

### 4.3 Raw Repository

```python
# app/features/reports/repositories/sales_report_repository.py
from datetime import date

from sqlalchemy import text

from app.core.repositories.raw_repository_base import RawRepositoryBase


class SalesReportRawRepository(RawRepositoryBase):
    async def daily_sales(self, *, start_date: date, end_date: date):
        statement = text(
            """
            SELECT
                DATE(o.created_at) AS sales_date,
                COUNT(*) AS order_count,
                COALESCE(SUM(o.total_amount), 0) AS gross_amount
            FROM orders AS o
            WHERE o.created_at >= :start_date
              AND o.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)
            GROUP BY DATE(o.created_at)
            ORDER BY sales_date ASC
            """
        )
        return await self.fetch_all(
            statement,
            {"start_date": start_date, "end_date": end_date},
            query_name="sales_report.daily_sales",
        )
```

주의: 위 SQL은 MySQL 방언 예시다. SQLite에서는 Base 계약만 빠르게 검증하고 실제 SQL과
Alembic migration은 로컬 및 CI가 공유하는 `compose.test.yaml` MySQL service에서 검증한다.
운영 SQL을 테스트 편의 때문에 문자열 치환하지 않는다.

### 4.4 Raw Service

```python
# app/features/reports/services/report_service.py
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import DailySalesItem


class ReportService(BaseService):
    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = SalesReportRawRepository(db_session)

    async def get_daily_sales(self, *, start_date: date, end_date: date):
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")

        rows = await self.repository.daily_sales(
            start_date=start_date,
            end_date=end_date,
        )
        return [DailySalesItem.model_validate(dict(row)) for row in rows]
```

날짜 범위 규칙은 비즈니스 규칙이므로 Service에 둔다. SQL과 컬럼 alias는 Repository가
소유한다.

### 4.5 Raw Dependency

```python
# app/features/reports/dependencies/report_dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    return ReportService(db_session)
```

### 4.6 Raw View

```python
# app/features/reports/api/routers/v1/sales_reports.py
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.features.reports.dependencies.report_dependencies import (
    get_report_service_readonly,
)
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/sales/daily",
    response_model=DailySalesReportResponse,
    summary="일별 매출 리포트",
    description="지정한 기간의 주문 수와 총 매출을 일별로 집계합니다.",
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(description="조회 시작일", examples=["2026-08-01"]),
    end_date: date = Query(description="조회 종료일", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(
        start_date=start_date,
        end_date=end_date,
    )
    return DailySalesReportResponse(
        start_date=start_date,
        end_date=end_date,
        items=items,
    )
```

조회이므로 commit하지 않는다. Raw SQL이라는 이유로 쓰기 세션을 사용하지 않는다.

## 5. 라우터 취합

버전 View를 기능 그룹 라우터에 등록한다.

```python
# app/features/reports/api/routers/router.py
from fastapi import APIRouter

from app.features.reports.api.routers.v1 import sales_reports

reports_router = APIRouter()
reports_router.include_router(
    sales_reports.router,
    prefix="/v1/reports",
    tags=["Reports"],
)
```

기능 패키지는 `router`만 공개한다.

```python
# app/features/reports/__init__.py
from app.features.reports.api.routers.router import reports_router as router

__all__ = ["router"]
```

`main.py`에서 명시적으로 최종 취합한다.

```python
from app.features import reports

app.include_router(reports.router, prefix="/api")
```

자동 탐색은 사용하지 않는다. 누락은 `test_router_registration.py` 계열 테스트로 찾는다.

## 6. Raw SQL 보안 규칙

### 허용

```python
statement = text("SELECT * FROM orders WHERE user_id = :user_id")
await self.fetch_all(statement, {"user_id": user_id})
```

### 금지

```python
text(f"SELECT * FROM orders WHERE user_id = '{user_id}'")
text("SELECT * FROM " + table_name)
```

정렬 컬럼처럼 식별자 선택이 필요하면 allowlist를 사용한다.

```python
SORT_COLUMNS = {
    "date": "o.created_at",
    "amount": "o.total_amount",
}
column = SORT_COLUMNS[requested_sort]
statement = text(f"SELECT ... ORDER BY {column} DESC")
```

이 경우 f-string 값은 외부 입력이 아니라 코드가 소유한 상수에서만 나온다.

## 7. 트랜잭션 지침

### 조회

```text
GET View
  -> get_<feature>_service_readonly
  -> get_read_only_db_session
  -> Repository 조회
  -> commit 없음
```

### 쓰기

```text
POST/PATCH/DELETE View
  -> get_<feature>_service
  -> get_writer_db_session
  -> Repository flush/execute
  -> View에서 await service.commit()
  -> 응답 반환
```

금지 항목:

- Dependency teardown에서 commit
- Repository에서 commit
- 응답 반환 후 background task로 핵심 DB commit
- 조회 View에서 쓰기 Dependency 재사용
- Raw DML을 `get_read_only_db_session`으로 실행

## 8. Scalar 문서 체크리스트

### View

- [ ] `summary`, `description`, 고유 `operation_id`
- [ ] 성공 `response_model`과 상태 코드
- [ ] 알려진 오류를 `responses`로 문서화
- [ ] Path/Query 제약과 설명 및 대표 예시
- [ ] 적절한 그룹 tag

### Pydantic

- [ ] 입력과 출력을 별도 모델로 구분
- [ ] 모든 외부 노출 필드에 의미 있는 `description`
- [ ] 길이, 범위, pattern 등 실제 검증 제약
- [ ] 민감 필드는 응답 모델에서 제외
- [ ] 대표 요청/응답은 `json_schema_extra.examples`로 제공
- [ ] ORM 응답만 `from_attributes=True`; Raw mapping은 명시적으로 검증

### ORM 모델

- [ ] DB nullability, unique, index, FK와 Python 타입 일치
- [ ] 공통 믹스인 정책 준수
- [ ] DB `comment`는 필요 시 제공하되 API 문서의 유일한 출처로 사용하지 않음

### 태그

- [ ] `tags_metadata.py`의 이름과 Router tag 일치
- [ ] 구현 완료 기능을 “예정”으로 설명하지 않음
- [ ] 태그 표시 순서가 의도와 일치

## 9. 테스트 지침

### ORM Repository

- create/get/list/count/exists/update/delete
- 입력 dict가 변경되지 않는지 검증
- duplicate/FK/DB 오류 변환
- eager loading이 필요한 기능 쿼리의 N+1 검증
- PK 타입이 `BaseRepository[ModelT, PrimaryKeyT]` 계약으로 검사되는지 검증

### Raw Repository

- named parameter가 실제로 바인딩되는지 검증
- one/all/scalar/rowcount 결과 형태
- 빈 결과 처리
- DB 오류가 공통 예외로 변환되는지 검증
- 사용자 값이 SQL 문자열에 직접 삽입되지 않는지 검토
- MySQL 전용 SQL은 MySQL 통합 테스트로 검증
- 모든 public 실행에 안정적인 `query_name`을 전달하고 SQL 본문과 params를 로그에 남기지 않음

### MySQL 통합 환경

- 프로젝트 루트의 `compose.test.yaml`에 MySQL test service를 정의한다.
- 로컬과 CI가 같은 compose 파일, healthcheck, migration 명령과 pytest marker를 사용한다.
- 테스트 시작 시 Alembic head까지 upgrade하고 Raw SQL/migration 테스트를 실행한다.
- migration chain은 현재 head → 신규 revision 순차 upgrade, downgrade, 재-upgrade를 검증한다.
- SQLite는 Base와 Service의 빠른 단위 테스트에만 사용하며 MySQL 방언 승인의 근거로 삼지 않는다.

### Service

- Repository mock/fake로 비즈니스 분기 검증
- Raw row가 Pydantic DTO로 변환되는지 검증
- 잘못된 기간과 상태 전환 검증

### API

- 성공 상태와 응답 schema
- validation 422 및 알려진 오류
- 조회 commit 0회
- 쓰기 성공 commit 1회
- 예외/commit 실패가 성공 응답으로 반환되지 않음
- read-only/writer DB session Dependency 선택

### OpenAPI

- operation ID 중복 없음
- 실제 Router tag와 metadata 일치
- ORM/Raw 응답 schema 모두 존재
- 문서에서 내부 ORM 객체나 `RowMapping`이 직접 노출되지 않음
- 규칙 기반 contract 검사를 기본으로 하고 상품·매출 핵심 schema만 snapshot

## 10. 코드 리뷰 체크리스트

- [ ] View에 SQL 또는 복잡한 도메인 분기가 없는가
- [ ] Dependency가 조립 외 작업을 하지 않는가
- [ ] Service가 HTTP 객체를 알지 않는가
- [ ] Repository가 commit하지 않는가
- [ ] ORM Repository는 ORM Base를 상속하는가
- [ ] Raw Repository는 Raw Base를 상속하는가
- [ ] Raw SQL은 named binding과 식별자 allowlist를 사용하는가
- [ ] read-only/writer DB session이 올바르게 분리됐는가
- [ ] Pydantic이 모든 외부 응답을 검증하는가
- [ ] 라우터가 버전 → 기능 → main 순서로 명시 취합되는가
- [ ] Scalar 메타데이터와 실제 구현이 일치하는가
- [ ] 단위, 통합, 트랜잭션, OpenAPI 테스트가 추가됐는가

## 11. Lifespan 자원 관리 지침

### 기본 구조

`main.py`에는 자원별 startup/shutdown 코드를 나열하지 않는다.

```python
from contextlib import asynccontextmanager

from app.core.resources import manage_application_resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app):
        yield
```

`app/core/resources.py`에서 순서를 명시적으로 관리한다.

```python
@dataclass(slots=True)
class ApplicationResources:
    log_listener: QueueListener | None = None


@asynccontextmanager
async def manage_application_resources(app: FastAPI):
    resources = ApplicationResources()
    app.state.resources = resources
    try:
        async with AsyncExitStack() as cleanup:
            resources.log_listener = build_queue_listener()
            resources.log_listener.start()
            cleanup.push_async_callback(
                stop_log_listener_async,
                resources.log_listener,
            )

            cleanup.push_async_callback(dispose_engine)

            import_all_models()
            if app_settings.DEBUG and Base.metadata.tables:
                await create_db_tables(import_models=False)

            cleanup.push_async_callback(access_log_tasks.drain)
            yield resources
    finally:
        app.state.resources = None
```

`AsyncExitStack`은 callback을 등록 역순으로 실행한다. listener stop, DB dispose,
background drain 순서로 등록하면 실제 종료는 background drain, DB dispose, listener
flush/stop 순서가 된다. listener의 동기 flush/join은 `asyncio.to_thread()`로 실행한다.
cleanup별 로깅과 timeout은 작은 wrapper 함수로 추가한다.

### 모델과 테이블 생성

- 모델 모듈을 먼저 import한다.
- `Base.metadata.tables`가 비었으면 DB 접속과 `create_all()`을 생략한다.
- 개발 자동 생성 정책이 활성화된 경우에만 `create_all()`을 실행한다.
- 운영은 Alembic migration을 사용한다.
- 모델 파일이 있다는 사실이 아니라 실제 metadata table 수로 판정한다.

### 장기 자원과 요청 자원

| 종류 | 관리 위치 |
|---|---|
| DB engine/pool | Resource Manager |
| logging queue/listener | Resource Manager에서 마지막 flush/stop |
| access log background tasks | Resource Manager에서 shutdown drain |
| 요청별 AsyncSession | `get_writer_db_session`/`get_read_only_db_session` Dependency |
| Celery broker/backend | Celery worker process |

DB engine/sessionmaker는 기존 DI와 SQLAdmin을 위해 `db/session.py`에 정의해도 된다. 다만
engine pool을 종료하는 주체는 Resource Manager 하나만 둔다.

### 종료 순서

```text
1. FastAPI가 신규 요청 수신 중단
2. in-flight background task drain
3. DB writer/read/background engine dispose
4. logging queue flush 및 listener stop
```

자원을 해제한다는 이유로 DB table을 drop하지 않는다.

### 자원 Dependency

장기 수명 자원이 필요하면 module global을 새로 만들지 않고 `app.state.resources`에서
Dependency로 제공한다.

```python
def get_application_resources(request: Request) -> ApplicationResources:
    resources = request.app.state.resources
    if resources is None:
        raise RuntimeError("Application resources are not available")
    return resources
```

### 추가 체크리스트

- [ ] startup 중간 실패에도 cleanup이 실행되는가
- [ ] 모델이 없으면 DB 연결을 시도하지 않는가
- [ ] 사용하지 않는 선택 자원을 생성하지 않는가
- [ ] background task가 사용하는 client보다 task를 먼저 종료하는가
- [ ] cleanup 실패가 다음 cleanup을 막지 않는가
- [ ] task 5초, DB 10초, logging 5초, 전체 20초 제한이 적용됐는가
- [ ] Celery worker cleanup에 별도 10초 제한이 적용됐는가
- [ ] multi-worker별 DB pool 연결 수가 DB 한도를 넘지 않는가
- [ ] `/health`와 `/ready`의 목적이 분리되어 있는가
- [ ] `/ready`가 writer DB `SELECT 1`을 2초 내 실행하고 실패 시 503을 반환하는가
- [ ] startup/shutdown 로그에 secret이 포함되지 않는가
- [ ] shutdown 후 `app.state.resources`에 닫힌 자원 참조가 남지 않는가

## 12. 비동기 구현 지침

### 비동기 적용 판단

`async def`는 비동기 I/O를 await할 때 의미가 있다. 모든 동기 함수를 무조건 async 또는
thread 작업으로 바꾸지 않는다.

| 유형 | 구현 기준 |
|---|---|
| DB/HTTP I/O | async client와 `await` 사용 |
| 파일 logging | QueueHandler로 event loop 밖 listener thread에 위임 |
| bcrypt 등 고비용 CPU | `asyncio.to_thread()` 또는 worker 사용 |
| 짧은 JWT/Pydantic/User-Agent 연산 | event loop에서 동기 실행 허용 |
| Celery task entrypoint | sync 유지, 내부 coroutine bridge 사용 |
| SQLAlchemy metadata DDL | `AsyncConnection.run_sync()` 사용 허용 |

### Queue 기반 logging

운영 파일 handler를 root logger에 직접 연결하지 않는다.

```text
root logger
  -> bounded QueueHandler
  -> QueueListener thread
       -> stdout/stderr
       -> container/runtime log collector
```

production/staging 애플리케이션 파일 handler는 사용하지 않는다. Docker, Kubernetes 또는
운영 agent가 파일 저장과 rotation을 담당하며 각 worker는 독립 queue/listener를 가진다.

Resource Manager는 listener의 lifecycle을 관리한다.

```python
listener = build_queue_listener()
listener.start()
resources.log_listener = listener
cleanup.push_async_callback(stop_log_listener_async, listener)
```

`stop_log_listener_async()`는 동기 `listener.stop()`과 flush/join을
`await asyncio.to_thread(...)`로 격리한다.

구현 체크리스트:

- [ ] worker별 queue 최대 크기가 10,000건인가
- [ ] 적재가 blocking `put()`이 아닌 `put_nowait()`인가
- [ ] DEBUG/INFO/WARNING drop counter와 rate-limited 관측 신호가 있는가
- [ ] ERROR/CRITICAL에 재귀 없는 최소 stderr fallback이 있는가
- [ ] 정상 shutdown에서 ERROR/CRITICAL 로그를 flush하는가
- [ ] production/staging에 애플리케이션 file handler가 없는가
- [ ] 외부 collector가 저장과 rotation을 담당하는가
- [ ] API request thread에 동기 output handler가 연결되지 않는가
- [ ] uvicorn logger의 중복 출력과 propagate 설정을 검증했는가

### Background task timeout

```python
done, pending = await asyncio.wait(tasks, timeout=timeout)
for task in pending:
    task.cancel()
await asyncio.gather(*pending, return_exceptions=True)
```

취소만 호출하고 반환하지 않는다. task를 await해야 `finally`, session rollback/close와
task cleanup callback이 실행된다. 종료 후 `runner.active == 0`을 검증한다.

### Celery worker 종료

Celery entrypoint는 동기 함수로 유지한다.

```python
@celery_app.task
def task_entrypoint():
    return run_async(async_use_case())
```

worker shutdown signal에서는 event loop가 살아 있는 동안 DB pool을 먼저 dispose한다.

```text
worker_process_shutdown
  -> run_async(dispose worker DB resources)
  -> loop.shutdown_asyncgens()
  -> loop.close()
  -> loop reference = None
```

FastAPI Resource Manager를 Celery에서 직접 실행하지 않는다. 공통 DB cleanup primitive만
재사용한다.

### 금지 패턴

```python
async def handler():
    requests.get(url)           # 동기 HTTP
    time.sleep(1)               # event loop 정지
    open(path).write(data)      # 동기 파일 I/O
    subprocess.run(command)     # 동기 프로세스 대기
```

동기 라이브러리만 사용할 수 있다면 `asyncio.to_thread()`로 격리하거나 Celery 같은 외부
worker로 이동한다. 단, 마이크로초 수준의 짧은 CPU 연산은 thread 전환 비용을 측정한 뒤
결정한다.
