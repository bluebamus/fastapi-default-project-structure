# 개발 가이드

새 엔드포인트·테이블을 만들 때 따라가는 문서입니다. 두 참조 예제를 기준으로 삼습니다 —
`app/features/catalog/`(ORM, 상품 CRUD)와 `app/features/reports/`(Raw SQL, 일별 매출 집계·스냅샷 적재).
구조와 런타임의 **왜**는 [ARCHITECTURE](./ARCHITECTURE.md), 설치·실행은 [README](../../README.md)에 있습니다.
상품 생성 한 요청을 도식과 함께 따라가는 요약은 [신규 뷰·테이블 개발 안내서](./feature-development-guide.html)
이고, 절차·체크리스트의 원본은 이 문서입니다. 한쪽을 고치면 다른 쪽도 함께 고칩니다.

아래 코드 조각은 실제 파일을 줄인 것이거나(파일 경로를 적음) 설명용 가상 예시(`inventory`)입니다.
공개 계약을 바꿀 때는 조각이 아니라 실제 파일과 테스트를 기준으로 합니다.

## 목차

1. [계층 원칙](#1-계층-원칙)
2. [새 기능·테이블 추가 절차](#2-새-기능테이블-추가-절차)
3. [세션과 의존성 선택](#3-세션과-의존성-선택)
4. [트랜잭션 규칙](#4-트랜잭션-규칙)
5. [ORM 워크플로 — catalog](#5-orm-워크플로--catalog)
6. [Raw SQL 워크플로 — reports](#6-raw-sql-워크플로--reports)
7. [Raw SQL 보안 규칙](#7-raw-sql-보안-규칙)
8. [마이그레이션](#8-마이그레이션)
9. [OpenAPI·Scalar 문서 체크리스트](#9-openapiscalar-문서-체크리스트)
10. [비동기·background·Celery](#10-비동기backgroundcelery)
11. [로깅 사용법](#11-로깅-사용법)
12. [테스트](#12-테스트)
13. [코드 리뷰 체크리스트](#13-코드-리뷰-체크리스트)

---

## 1. 계층 원칙

```text
View → Dependency → Service → Repository → AsyncSession
```

ORM 과 Raw SQL 은 **Repository 구현에서만** 갈라집니다. 나머지(조립·유스케이스·트랜잭션·응답 검증·
라우터·문서·테스트 기준)는 같습니다.

| 개념 | 이 프로젝트의 자리 | 두지 않는 것 |
|---|---|---|
| Model | `models/models.py` — 테이블·컬럼·제약 | HTTP 응답 계약 |
| 입출력 계약 | `schemas/` — Pydantic 입력 검증·응답 공개 필드·문서 | 테이블 생성, DB 접근 |
| Controller(View) | `api/routers/v1/*.py` — 경로·파라미터·Service 호출·응답·**쓰기 커밋** | SQL, 도메인 분기 |
| Composition root | `dependencies/` — 세션 선택 + `Service(db_session)` 반환 | 유스케이스 실행, 커밋, `yield` 후 커밋 |
| Service | `services/` — `BaseService` 상속, 업무 규칙·오케스트레이션 | HTTP 객체, SQL 문자열, 임의 커밋 |
| Repository | `repositories/` — `BaseRepository` 또는 `RawRepositoryBase` 상속 | 커밋, HTTP, 업무 규칙 |
| 관리 UI | `admin.py` — SQLAdmin ModelView | API 권한 계약과 공유되는 보안 장치 아님 |

"뷰" 는 이 저장소에서 path operation 함수를 뜻합니다(SQLAdmin ModelView·DB 의 SQL VIEW 와 다릅니다).
Service 를 FastAPI 밖(background·Celery·테스트)에서도 생성자 주입으로 쓸 수 있는 것이 계층을 나누는
이유입니다. 요구가 없는데 UnitOfWork·Factory·Strategy 같은 추상을 새로 들이지 않습니다.

## 2. 새 기능·테이블 추가 절차

먼저 정합니다 — method·path, 입력, 공개 응답 필드, 인증·권한, 읽기/쓰기 의도, 데이터 소유, 동시성,
실패 응답. 기존 기능에 엔드포인트만 더하면 되는 일이면 새 기능을 만들지 않습니다.
뼈대는 `app/features/catalog/` 를 그대로 본뜹니다(생성 스크립트는 없습니다).

### 2.1 만들 파일

| 파일 | 책임 |
|---|---|
| `models/models.py` (+ 빈 `models/__init__.py`) | Base/Mixin 상속, `__tablename__`, PK·nullable·unique·index·FK·default (§5.1) |
| `schemas/<x>_schema.py` | Create/Update/Response/List DTO (§5.2) |
| `repositories/<x>_repository.py` | `BaseRepository[Model, str]` 또는 `RawRepositoryBase` 상속 |
| `services/<x>_service.py` | `BaseService` 상속, 같은 세션으로 Repository 조립 |
| `dependencies/<x>_dependencies.py` | `get_<x>_service`(writer) / `get_<x>_service_readonly`(read-only) |
| `api/routers/v1/<view>.py` | `router = APIRouter()` + path operation. 업무 단위로 파일을 나눠도 된다 |
| `api/routers/router.py` | `<name>_router` 가 v1 파일들을 `prefix="/v1/<name>"`, `tags=[...]` 로 취합 |
| `__init__.py` | `router` 공개 + `models` import. `admin_views` 는 재노출하지 않는다 |
| `exceptions.py` | 기능 예외(`NotFoundException` 등 `app/core/exception.py` 하위) |
| `admin.py` | 모델이 있으면 ModelView + `admin_views` |
| `tests/` | §12 |

```python
# app/features/inventory/__init__.py   (가상 예시)
from app.features.inventory.api.routers.router import inventory_router as router
from app.features.inventory.models import models as _models  # noqa: F401 (Base.metadata 등록)

__all__ = ["router"]
```

### 2.2 기능 밖에서 손댈 곳

| 파일 | 할 일 | 빠뜨리면 |
|---|---|---|
| `main.py` | `from app.features import …, inventory` + `app.include_router(inventory.router, prefix="/api")` | 라우트가 없다(404). `tests/test_router_registration.py` 가 잡는다 |
| `app/features/admin.py` | `from app.features.inventory.admin import admin_views as inventory_admin_views` + `ADMIN_VIEWS` 에 사전순으로 한 줄 | `/admin` 에서 조용히 빠진다. `tests/test_admin_wiring.py` 가 잡는다 |
| `app/core/tags_metadata.py` | 라우터 tag 와 같은 이름의 설명 | `tests/test_openapi_contract.py` 가 잡는다 |
| `tests/test_route_inventory.py` | 새 경로·메서드를 골든 목록에 추가 | 인벤토리 테스트 실패 |
| `tests/test_admin_wiring.py` | 관리 대상 모델 고정 목록에 추가 | 같은 파일의 검사 실패 |
| `migrations/versions/` | revision 추가 (§8) | 운영 DB 에 테이블이 없다 |
| README API 표 | 경로 추가 | 문서 드리프트 |

모델 등록은 따로 할 일이 없습니다 — `models_registry` 가 `models/models.py` 를 찾습니다.
**기능명 = URL 세그먼트**(`/api/v1/inventory/…`)여야 등록 테스트가 통과합니다.
새 공용 설정이 필요하면 `config.py` 에 필드를 추가하고 `.env.example` 에도 적습니다
(`tests/core/test_settings_contract.py`). 환경 변수는 `config.py` 밖에서 읽지 않습니다.
새 비밀 키·비밀번호를 추가하면 `validate_deployment_safety()` 의 검사 대상에도 넣습니다
(staging/production 에서 예시 값 거부, `tests/core/test_deployment_safety.py`). **반드시 있어야 하는
값**이면 기존 `secrets` 딕셔너리에 넣어 빈 값도 위반으로 보고, **안 쓰는 것이 정당한 값**이면
비어 있을 때 건너뛰는 쪽(`REDIS_PASSWORD`·`SMTP_PASSWORD`)에 넣습니다.

### 2.3 작업 순서 요약

1. HTTP 계약·데이터 소유·권한·세션 의도·동시성·실패 응답을 정한다.
2. Model → Schema → Repository → Service → Dependency → View 를 기존 예제대로 작성한다.
3. 기능 `router.py`·`__init__.py`, `main.py`, (필요시) `admin.py`·`tags_metadata.py` 를 연결한다.
4. migration 후보를 만들고 검토·적용한다(§8).
5. DTO 검증 → 커밋 순서, 롤백·취소·background 세션 경계를 점검한다(§4).
6. 단위·엔드포인트·트랜잭션·등록 테스트와 필요한 MySQL 테스트를 쓰고, `uv run python -m scripts.review_gate` 로 확인한다.
7. README API 표와 관련 문서를 함께 고친다.

## 3. 세션과 의존성 선택

```text
유스케이스가 쓰기인가 / 조회 후 쓰기인가 / 잠금이 필요한가?
  ├─ 예  → get_writer_db_session → 같은 세션으로 작업 → View 에서 응답 전 커밋 1회
  └─ 아니오 → 복제 지연을 허용하는가?
        ├─ 예  → get_read_only_db_session → 커밋 없음
        └─ 아니오 → get_writer_db_session 으로 조회만 (커밋 없음)
```

HTTP 메서드 이름이 아니라 **하는 일**이 세션을 정합니다. Raw SQL 이라고 쓰기 세션을 쓰지 않고,
조회 후 쓰기의 첫 SELECT 가 replica 로 새지 않도록 writer 를 씁니다. 이름 규칙과 동작은
[ARCHITECTURE §4.2](./ARCHITECTURE.md#42-세션-의존성).

```python
# app/features/catalog/dependencies/catalog_dependencies.py
async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(db_session)


async def get_catalog_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    return CatalogService(db_session)
```

- 인자·속성 이름은 `db_session`/`self.db_session` 입니다.
- 한 요청에서 여러 Service 가 하나의 원자적 쓰기에 참여하면 **같은 writer 세션**을 넘기고, 커밋 주체는
  View 하나로 둡니다. Service 를 전역 싱글턴으로 두지 않습니다(세션이 요청을 넘나듭니다).
- 읽기 세션의 쓰기 차단은 `DB_ROUTER_ENABLED` 와 무관하게 동작합니다(기본값 `false` 포함). 그래도
  쓰기는 처음부터 writer 의존성으로 고정하고, 운영에서는 DB 권한(읽기 전용 계정)을 함께 씁니다 —
  `session.info` 표시는 보안 경계가 아닙니다.
- 장기 자원(예: Redis client)이 필요하면 모듈 전역을 새로 만들지 말고 `app/core/resources.py` 에 자원
  컨텍스트를 추가하고 `app.state` 에서 꺼내는 작은 의존성을 둡니다(현재 `app.state.redis` 를 주입하는
  공용 의존성은 없습니다). 새 자원은 정리 순서(자원을 쓰는 주체 → 자원)와 개별 timeout 을 함께 정합니다.

## 4. 트랜잭션 규칙

```text
조회: GET View → get_<x>_service_readonly → get_read_only_db_session → Repository 조회 → 커밋 없음
쓰기: POST/PATCH/DELETE View → get_<x>_service → get_writer_db_session
      → Repository flush/execute → View 에서 응답 DTO 검증 → await service.commit() → 응답
```

- 커밋은 **View 본문에서 응답 전 정확히 1회**. 예외 경로는 커밋 0회이고 세션 의존성이 롤백합니다.
- `flush` 는 트랜잭션 안에서 SQL 을 보내 기본값·제약을 확인할 뿐 확정이 아닙니다. Repository·Service
  중간에서 커밋하면 뒤의 실패가 앞 변경을 되돌리지 못합니다.
- **응답 DTO 검증 → 커밋 → 반환** 이 모든 쓰기 핸들러의 단일 규칙입니다. 커밋 뒤에 검증하면 직렬화가
  실패했을 때 저장은 됐는데 클라이언트는 500 을 받습니다. `tests/test_write_dto_before_commit.py` 가 전
  기능의 생성·수정 핸들러에서 "DTO 실패 → 500 · 커밋 0회 · DB 불변" 을 확인하므로 쓰기 핸들러를 추가하면
  그 `CASES` 에 한 줄을 더합니다. 응답에 필요한 필드(관계 포함)는 Repository 에서 미리 로드합니다.

```python
async def create_item(payload: ItemCreate, service: InventoryService = Depends(get_inventory_service)):
    item = await service.create_item(payload)
    response = ItemResponse.model_validate(item)   # 먼저 검증
    await service.commit()                         # 그다음 확정
    return response
```

- `BaseService.commit()` 은 세션 커밋을 그대로 await 합니다 — Repository 의 예외 변환은 커밋 단계 오류를
  포함하지 않으므로, 새 오류 계약은 커밋 실패도 점검합니다. 사용자 응답에 SQL·바인드 값·DSN 을 싣지 않습니다.
- 커밋 성공 뒤의 연결 단절은 롤백으로 되돌릴 수 없습니다. 중복 생성이 치명적인 업무는 idempotency 키나
  유일 제약을 요구사항으로 정합니다. 상태 전환·재고 차감은 조회 후 UPDATE 만으로 안전하지 않으니 조건부
  UPDATE·잠금·제약을 설계합니다.
- PATCH: `model_dump(exclude_unset=True)` 는 **보내지 않은** 필드만 빼고 명시적 `null` 은 남깁니다.
  non-nullable 컬럼에 null 을 허용할지 거부할지 정하고 테스트합니다. 바뀔 값이 없으면 UPDATE 를 보내지
  않고(불필요한 `updated_at` 갱신 방지), `update_by_id` 가 `None` 을 돌려줘도 존재는 이미 확인했다면 404 가
  아닙니다(`CatalogService.update_product` 참고).

금지:

- 의존성 teardown·Repository 에서 커밋
- 응답 반환 후 background task 로 핵심 데이터 커밋
- 조회 View 에서 쓰기 의존성 재사용, Raw DML 을 읽기 세션으로 실행
- 같은 `AsyncSession` 으로 `asyncio.gather` — 한 트랜잭션의 SQL 은 순차 await

## 5. ORM 워크플로 — catalog

### 5.1 모델

```python
# app/features/catalog/models/models.py (축약)
class Product(UUIDTimestampModel):
    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True, comment="상품명")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="판매가")  # float 금지
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

- 변경 가능한 엔티티는 `UUIDTimestampModel`, 불변 기록은 `UUIDCreatedModel`, 외부·자연키는 `Base` +
  필요한 Mixin(ARCHITECTURE §5.1). `DeclarativeBase` 를 기능에 새로 만들지 않습니다.
- DB 제약과 `Mapped` 타입을 일치시킵니다. 컬럼 `comment` 는 선택이며 API 설명을 대신하지 않습니다.
- 금액은 `Numeric` + `Decimal`. 동시성 상황의 최종 무결성은 스키마 검증이 아니라 DB 제약이 지킵니다.
- 선언되지 않은 FK·relationship 을 추측해 만들지 않습니다. 기능 간 참조는 FK 없는 식별자로 둡니다.
- `Base.to_dict()` 결과를 그대로 응답하지 않습니다 — 해시·내부 컬럼이 샙니다. 공개 필드는 Schema 가 정합니다.

### 5.2 Schema

```python
# app/features/catalog/schemas/catalog_schema.py (축약)
class ProductCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Mechanical Keyboard", "price": "129.00"}]})
    name: str = Field(min_length=1, max_length=200, description="상품명")
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="판매가")


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(description="상품 UUID")
    ...
```

입력·출력 모델을 분리하고, 외부 노출 필드마다 `description`, 주요 DTO 에 `json_schema_extra.examples` 를
둡니다. 스키마 클래스 이름은 프로젝트 전체에서 고유해야 합니다(OpenAPI 에 그대로 노출).
Path 파라미터가 `str` 이면 UUID 형식을 자동 검증하지 않으니 필요하면 타입이나 검증을 명시합니다.

### 5.3 Repository

```python
# app/features/catalog/repositories/product_repository.py (축약)
class ProductRepository(BaseRepository[Product, str]):
    model = Product

    async def list_active(self, *, skip: int = 0, limit: int = 100) -> Sequence[Product]:
        statement = (
            select(Product)
            .where(Product.is_active.is_(True))       # 문자열 컬럼명이 아니라 속성으로
            .order_by(Product.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return (await self.db_session.execute(statement)).scalars().all()
```

- Base 의 8개(ARCHITECTURE §5.2)로 안 되는 조회만 명시적 메서드로 추가합니다. 같은 필터로 `count` 도
  함께 둡니다(`count_active`).
- 목록은 고정 정렬(동률이면 PK)을 명시합니다 — Base 의 `list()` 에는 정렬이 없습니다.
- **N+1**: 응답이 관계를 읽는다면 Repository 가 미리 적재합니다. 현재 모델에는 relationship 이 없으므로
  아래는 관계를 추가했을 때의 형태입니다.

```python
statement = select(Author).options(selectinload(Author.posts)).offset(skip).limit(limit)
```

| 전략 | 쿼리 | 적합 |
|---|---|---|
| `selectinload` | `SELECT … WHERE id IN (…)` | 1:N — 대부분 |
| `joinedload` | `LEFT OUTER JOIN` | 1:1, 항상 함께 쓰는 소수 행 |
| `subqueryload` | 서브쿼리 | 깊은 중첩 |

async 에서는 lazy 로딩이 DTO 검증 중 암묵 I/O 를 일으키지 않게 해야 합니다. `expire_on_commit=False` 가
관계 로딩 문제를 해결하지는 않습니다.

### 5.4 Service

```python
# app/features/catalog/services/catalog_service.py (축약)
class CatalogService(BaseService):
    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = ProductRepository(db_session)

    async def create_product(self, payload: ProductCreate) -> Product:
        return await self.repository.create(payload.model_dump())

    async def get_product(self, product_id: str) -> Product:
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundException(detail={"id": product_id})
        return product
```

부재·중복·상태 전환·가격 정책 같은 규칙은 여기에 둡니다. 부재를 기능 예외로 바꾸는 것도 Service 입니다.

### 5.5 View

```python
# app/features/catalog/api/routers/v1/products.py (축약)
router = APIRouter()


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED,
             summary="상품 생성", description="…", operation_id="createProduct", responses={…})
async def create_product(payload: ProductCreate, service: CatalogService = Depends(get_catalog_service)) -> ProductResponse:
    product = await service.create_product(payload)
    response = ProductResponse.model_validate(product)   # 검증 → 커밋 → 반환
    await service.commit()
    return response


@router.get("/products", response_model=ProductListResponse, operation_id="listProducts", …)
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),          # 무제한 조회 금지 (NFR-002)
    active_only: bool = Query(False),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductListResponse:
    items, total = await service.list_products(skip=skip, limit=limit, active_only=active_only)
    return ProductListResponse(items=[ProductResponse.model_validate(i) for i in items], total=total, skip=skip, limit=limit)
```

라우터 취합은 [ARCHITECTURE §2.1](./ARCHITECTURE.md#21-라우터) 의 세 단계입니다.

## 6. Raw SQL 워크플로 — reports

### 6.1 언제 Raw 를 쓰나, 모델은 어떻게 두나

기본은 ORM 입니다. Raw 는 복잡한 집계·윈도 함수·CTE, 실행 계획으로 관리해야 하는 조회, 서버 안에서 끝나는
집합 연산(`INSERT … SELECT`)처럼 SQL 이 더 명확한 경우에 씁니다. "Raw 는 항상 빠르다" 거나
"Schema·Service 가 필요 없다" 는 뜻이 아닙니다.

- 집계 **결과**용 ORM 모델은 만들지 않습니다 — 결과 한 줄은 테이블의 행이 아닙니다.
- 단, 이 프로젝트가 생명주기를 소유하는 **원본 테이블**은 ORM 모델과 migration 을 둡니다. 모델이 없으면
  Alembic 이 그 테이블을 지워야 할 것으로 봅니다(`SalesOrder`). 결과를 영속 적재하는 테이블도 실제 테이블이므로
  모델이 있습니다(`SalesDailySnapshot`).
- SQL VIEW 가 필요하면 방언에 맞는 `CREATE/DROP VIEW` 를 migration 으로 직접 관리합니다. Table 모델만으로
  Alembic 이 VIEW 정의를 추적하지 않습니다(현재 reports 는 VIEW 를 만들지 않습니다).

### 6.2 Base 사용 계약

`fetch_one`/`fetch_all`/`fetch_scalar`/`execute` + keyword-only `query_name`
([ARCHITECTURE §5.3](./ARCHITECTURE.md#53-raw-sql--rawrepositorybase)). 문자열을 받는 만능 실행 메서드는 없습니다.

### 6.3 결과 Schema

```python
# app/features/reports/schemas/report_schema.py (축약)
class DailySalesItem(BaseModel):
    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])
```

Raw 결과는 ORM 객체가 아니므로 `from_attributes` 에 기대지 않고 `dict(row)` 를 검증합니다. SQL alias 와
DTO 필드명이 같아야 합니다. `Decimal`·날짜 타입은 대상 DB 에서 확인합니다.

### 6.4 Repository

```python
# app/features/reports/repositories/sales_report_repository.py (축약)
QUERY_DAILY_SALES = "sales_report.daily_sales"          # 로그의 안정 식별자 — 바꾸면 대시보드가 끊긴다
SORTABLE_COLUMNS = {"sales_date": "sales_date", "order_count": "order_count", "gross_amount": "gross_amount"}

_DAILY_SALES_SQL_TEMPLATE = """
    SELECT DATE(o.created_at) AS sales_date,
           COUNT(*)           AS order_count,
           COALESCE(SUM(o.total_amount), 0) AS gross_amount
      FROM sales_orders AS o
     WHERE o.created_at >= :start_at
       AND o.created_at <  :end_at
     GROUP BY DATE(o.created_at)
     ORDER BY {order_by} {direction}
"""


class SalesReportRawRepository(RawRepositoryBase):
    async def daily_sales(self, *, start_at, end_at, sort_by="sales_date", sort_direction="ASC"):
        order_by = resolve_identifier(sort_by, SORTABLE_COLUMNS)   # 요청값은 키로만
        direction = resolve_sort_direction(sort_direction)
        return await self.fetch_all(
            text(_DAILY_SALES_SQL_TEMPLATE.format(order_by=order_by, direction=direction)),
            {"start_at": start_at, "end_at": end_at},
            query_name=QUERY_DAILY_SALES,
        )
```

- 기간은 이미 계산된 **반열린 구간** `[start_at, end_at)` 으로 받습니다. 그래서 `DATE_ADD` 같은 방언 함수가
  SQL 에 없고 규칙이 SQL 에 숨지 않습니다.
- allowlist 는 Repository 가 소유합니다(ADR-013) — View 의 enum 은 UX 일 뿐이고, Celery·스크립트가 Repository
  를 직접 불러도 같은 제약이 걸려야 합니다. 허용 밖이면 `ValueError` 를 던지고 Service 가 422 로 바꿉니다.
- 표준 SQL 만 써서 SQLite 단위 테스트와 MySQL 통합 테스트가 같은 문장을 검증합니다. 그래도 방언 승인은
  MySQL 통합 테스트(`-m mysql`)가 합니다.

### 6.5 Service — 기간 규칙은 여기

```python
# app/features/reports/services/report_service.py (축약)
MAX_REPORT_DAYS = 366

async def get_daily_sales(self, *, start_date, end_date, sort_by=..., sort_direction=...):
    self._validate_range(start_date, end_date)          # 종료일 < 시작일, 366일 초과 → InvalidDateRangeException(422)
    start_at = datetime.combine(start_date, time.min)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min)   # "종료일 포함" → 다음날 00:00 미만
    try:
        rows = await self.repository.daily_sales(start_at=start_at, end_at=end_at, sort_by=sort_by, sort_direction=sort_direction)
    except ValueError as error:
        raise InvalidSortException(detail={...}) from error
    return [DailySalesItem.model_validate(dict(row)) for row in rows]
```

"종료일 포함"·최대 기간은 비즈니스 규칙이라 Service 가 해석하고, SQL 과 alias 는 Repository 가 가집니다.
`23:59:59` 를 끝으로 쓰면 마이크로초 단위 주문을 놓칩니다.

### 6.6 Dependency 와 View

```python
# app/features/reports/dependencies/report_dependencies.py
async def get_report_service_readonly(db_session=Depends(get_read_only_db_session)) -> ReportService: ...
async def get_report_service(db_session=Depends(get_writer_db_session)) -> ReportService: ...   # 적재용

# app/features/reports/api/routers/v1/sales_reports.py (축약)
@router.get("/sales/daily", response_model=DailySalesReportResponse, operation_id="getDailySalesReport", …)
async def get_daily_sales_report(
    start_date: date = Query(...), end_date: date = Query(...),     # 필수
    sort_by: str = Query("sales_date"), sort_direction: str = Query("asc"),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(start_date=start_date, end_date=end_date, sort_by=sort_by, sort_direction=sort_direction)
    return DailySalesReportResponse(start_date=start_date, end_date=end_date, items=items)   # 조회 — 커밋 없음
```

### 6.7 Raw 쓰기 — 스냅샷 적재

`POST /api/v1/reports/sales/daily/snapshots` 는 같은 writer 세션에서
`DELETE FROM sales_daily_snapshots …` → `INSERT INTO sales_daily_snapshots … SELECT … FROM sales_orders …` 를
실행하고 **View 가 한 번 커밋**합니다(ADR-011).

- 두 문장은 한 트랜잭션이어야 합니다 — DELETE 만 커밋되면 그 기간 리포트가 사라집니다.
- 표준 SQL `DELETE` + `INSERT … SELECT` 로 멱등을 만들고 방언 UPSERT 를 쓰지 않습니다.
- `generated_at` 은 바인드 파라미터로 넣습니다 — Raw DML 은 Mixin 의 Python 기본값을 우회해 NULL 이 됩니다.
  시각을 Python(`timezone_settings.now()`)이 정하면 테스트가 DB 시계에 묶이지 않습니다.
- `execute` 는 영향 행 수만 돌려줍니다. 원장(`sales_orders`)은 읽기만 합니다.
- 동시 실행의 직렬화는 보장하지 않습니다. 같은 기간을 동시에 적재할 수 있는 운영이라면 잠금·중복 실행
  정책을 따로 정합니다.

## 7. Raw SQL 보안 규칙

```python
# 허용 — 값은 named bind
statement = text("SELECT * FROM orders WHERE user_id = :user_id")
await self.fetch_all(statement, {"user_id": user_id}, query_name="orders.by_user")

# 금지 — 문자열로 값·식별자를 만든다
text(f"SELECT * FROM orders WHERE user_id = '{user_id}'")
text("SELECT * FROM " + table_name)

# 식별자가 필요하면 — 코드가 가진 allowlist 에서 꺼낸 값만 f-string 에
SORT_COLUMNS = {"date": "o.created_at", "amount": "o.total_amount"}
column = resolve_identifier(requested_sort, SORT_COLUMNS)
statement = text(f"SELECT … ORDER BY {column} DESC")
```

- allowlist 는 DB 의 전체 컬럼이 아니라 **그 쿼리가 허용한 키**만 담습니다.
- `query_name` 을 항상 넘기고, SQL 본문과 params 를 직접 로그에 남기지 않습니다.
- 읽기 세션에서 Raw DML 을 실행하면 `DB_ROUTER_ENABLED` 와 무관하게 `ReadOnlyRoutingError` 입니다.
  `WITH … UPDATE/DELETE` 같은 CTE DML 도 거부됩니다(§7.2). 다만 **라우팅** 방향 판별은 선두 키워드
  기준이라 CTE DML 을 replica 로 보낼 수 있습니다(ARCHITECTURE §4.3).
- 안전 검사·테스트 통과가 DB 권한·방언·실행 계획 검토를 대신하지 않습니다.

### 7.1 쓰기 판별 키워드를 고칠 때

고치는 곳은 `app/core/db/router.py` 의 `_TEXT_WRITE_KEYWORDS` 한 곳입니다. 이 집합은
`_text_is_write` → `_is_write` → `RoutingSession.get_bind()` 경로에서만 쓰이므로, 단어를 넣고 빼는 것이
곧 라우팅 판정을 바꿉니다.

| 상황 | 판단 |
|---|---|
| Raw `text()` 로 쓰거나 서버 상태를 바꾸는 구문인데 집합에 없다 | **추가한다** |
| 그 단어로 **시작하는 읽기 구문이 없다** | 추가 비용이 0 — 읽기가 writer 로 새는 오탐이 생길 수 없다 |
| 그 단어로 시작하는 읽기 구문이 있다 | 오탐 범위를 먼저 보고 정한다 |
| `BEGIN`·`START`·`COMMIT`·`ROLLBACK`·`SAVEPOINT` 류 | **넣지 않는다** — 아래 참조 |

- **애매하면 넣습니다.** 쓰기를 읽기로 오판하면 DML 이 replica 로 새어 데이터가 사라집니다. 읽기를
  쓰기로 오판하면 SELECT 하나가 writer 로 갈 뿐입니다. 비대칭이 큽니다.
- **트랜잭션 제어어는 죽은 항목입니다.** DBAPI 커넥션이 `get_bind()` **아래 레이어**에서 내보내므로
  집합에 넣어도 평가되지 않습니다(덤프 실측 250만 건 전부 드라이버 발신).
- **`SET` 을 정규식으로 세분화하지 않습니다.** 덤프의 23.96%(2억 4,496만 건)가 `SET` 이지만 전부
  `SET NAMES`·`SET SESSION sql_mode`·`SET AUTOCOMMIT` 같은 세션 스코프이고 드라이버가 핸드셰이크에
  내보내 `get_bind()` 를 타지 않습니다(`SET GLOBAL`·`SET @변수` 는 0건). 지금 세분화는 측정된 비용이
  0 인 상태의 조기 최적화입니다. 앱 코드가 `text("SET ...")` 을 부르는 것이 관측되면 그때 다시 봅니다.
- **파서(`sqlparse`)를 도입하지 않습니다.** 선두 키워드 방식이 못 잡는 구조 — CTE 로 감싼
  DML(`WITH … INSERT/UPDATE/DELETE`), 힌트 주석으로 시작하는 문장, 다중문장 DML,
  `SELECT … FOR UPDATE` — 가 10억 건(1,022,185,501건 실행 / 고유 지문 1,735개) 덤프에서 **0건**이었습니다.
  실측이 0 에 가까우면 의존성을 늘리지 않습니다.
- **바꿀 때 반드시**: `tests/core/test_router_raw_dml.py` 에 케이스를 추가하고, 근거를 CRP
  `orm-raw-repository` 그룹의 ADR(`docs/crp/groups/orm-raw-repository/design-baseline.md`)로 남깁니다.
- 덤프 근거의 한계: 수집 IP 69개 중 일부가 TLS 라 암호화 구간은 수집되지 않았고, 덤프는 기존 프로덕션
  트래픽이지 이 저장소의 `text()` 호출 기록이 아닙니다. 그래서 실측 0 건이어도 안전 측으로 기웁니다.

### 7.2 읽기 전용 판정을 확장·변경할 때

§7.1 이 **라우팅 방향**(writer 로 보낼까)을 정한다면, 여기는 **읽기 전용 세션의 거부 여부**를 정합니다.
방향이 반대인 별개의 판정이라 한 함수로 합치지 않습니다. 판정은 괄호 깊이 0 의 단어만 봅니다 — CTE
정의는 전부 괄호 안이므로 깊이 0 에 남는 단어가 곧 최상위 구문입니다. 그래서 `WITH … SELECT` 는
통과하고 `WITH … UPDATE/DELETE` 는 거부됩니다.

| 단계 | 위치 (`app/core/db/router.py`) |
|---|---|
| 집행 지점 | `_block_read_only_execute`(`do_orm_execute` 이벤트) · `_block_read_only_flush`(`before_flush` 이벤트) — `Session` 기반 클래스에 전역 등록되므로 sessionmaker 종류·`DB_ROUTER_ENABLED` 와 무관합니다 |
| 구문 분류 | `_statement_is_readable` — Core `UpdateBase` 거부, `Select` 허용, `TextClause` 는 아래로 |
| Raw SQL 판정 | `_text_is_readable` — 주석 제거 → multi-statement 거부 → 잠금 조회 거부 → 깊이 0 스캔 |
| 깊이 0 스캔 | `_depth0_words` — 따옴표·역따옴표 안을 건너뛰고, 스캔이 무너지면 `None` |

| 하고 싶은 것 | 건드릴 곳 |
|---|---|
| 새 읽기 구문을 허용 (예: `TABLE`, `VALUES`) | `_READABLE_LEAD` — `words[0]` 의 허용 시작 키워드 집합 |
| 새 쓰기 구문을 차단 | `_TOP_LEVEL_WRITE` 에 소문자 한 단어 추가 |
| 잠금 획득 패턴을 추가 | `_LOCKING_READ` 정규식 |

**판정 원칙**

- default-deny 입니다. 확실히 읽기라고 판단되지 않으면 거부합니다.
- 스캔이 무너지면(따옴표 미종료, 괄호 불일치) 거부로 떨어집니다(fail-closed).
- **애매하면 막습니다.** 잘못 허용하면 DML 이 replica 로 새어 조용히 데이터가 어긋나고, 잘못 막으면
  개발자가 즉시 알아챕니다. 비대칭이 한쪽으로만 위험합니다.
- 읽기가 막혔다면 판정을 고칠 일이지 writer 세션으로 바꿀 일이 아닙니다.

**바꿀 때 반드시**: `tests/core/test_read_only_guard.py` 의 `_READABLE`/`_UNREADABLE` 적대적 케이스
표에 새 케이스를 추가하고(문자열 안의 키워드, `''` 이스케이프, 역따옴표 식별자, 중첩 서브쿼리, 미종료
따옴표, 괄호 불일치가 이미 들어 있습니다), 근거를 CRP ADR
(`docs/crp/groups/orm-raw-repository/design-baseline.md` §3)로 남깁니다.

**한계.** 이건 파서가 아닙니다 — 방언별 신종 구문은 못 잡을 수 있습니다.

## 8. 마이그레이션

```bash
uv run alembic revision --autogenerate -m "add inventory items"
# 생성된 파일의 upgrade/downgrade · drop · nullable · index · FK · default · 데이터 이동을 사람이 검토
uv run alembic upgrade head
uv run alembic current
uv run alembic heads          # head 는 하나여야 한다 (CI 확인)
```

1. 모델을 만들고 기능 `__init__.py` 에서 import 한다(등록은 자동).
2. autogenerate 로 **후보**를 만든다. rename 은 감지되지 않고 drop 으로 나올 수 있다.
3. upgrade·downgrade 를 모두 구현하고, 빈 DB·기존 DB·MySQL 에서 확인한다
   (`tests/core/test_migration_chain.py` 는 빈 SQLite 에서 head 까지와 모델 일치를,
   `tests/integration/test_mysql_raw_sql.py` 는 MySQL 에서 upgrade → downgrade → 재-upgrade 를 본다).
4. 운영은 writer 에 `upgrade head` 를 **앱 배포 전에** 적용한다. 서버 기동은 upgrade 를 하지 않는다.

- `DEBUG=true` 의 `create_all` 로 만든 개발 DB 와 migration 을 섞을 때, 데이터가 있는 DB 에서 검증 없이
  drop/recreate 하거나 `alembic stamp head` 하지 않습니다 — `stamp` 는 테이블을 만들지 않고 이력만 맞춰
  스키마 차이를 숨깁니다.
- 호환 배포(컬럼 추가 → 코드 전환 → 옛 컬럼 제거)는 무중단 요구가 있을 때 단계를 나눕니다.
- `ALEMBIC_DATABASE_URL` 로 로컬에서 다른 DSN(SQLite 등)을 쓸 수 있습니다.

## 9. OpenAPI·Scalar 문서 체크리스트

Scalar 문서의 계약은 ORM 모델이 아니라 View 와 Pydantic DTO 입니다. `tests/test_openapi_contract.py` 가
대부분을 규칙으로 검사합니다.

- [ ] View: `summary`, `description`, 프로젝트 전체에서 고유한 `operation_id`(기존 예제는 camelCase — SDK 생성기의 함수명이 된다)
- [ ] 성공 `response_model` 과 상태 코드. **204 는 본문·`response_model` 없음**
- [ ] 알려진 오류를 `responses` 로(404·409·422 등, 오류 모델은 `ErrorResponse`)
- [ ] Path·Query 의 설명·실제 제약·대표 예시(`examples=`)
- [ ] 라우터 tag 가 `app/core/tags_metadata.py` 에 있고, 쓰지 않는 tag 가 남지 않음
- [ ] 구현된 기능을 "예정·미구현" 으로 설명하지 않음
- [ ] DTO: 입력/출력 분리, 외부 필드마다 `description`, 주요 DTO 에 `json_schema_extra.examples`,
      민감 필드(해시·토큰) 제외, 스키마 이름 전역 고유
- [ ] ORM 응답만 `from_attributes=True`, Raw 는 명시 변환 — `RowMapping`·ORM 객체가 계약에 노출되지 않음

## 10. 비동기·background·Celery

### 10.1 무엇을 async 로 하나

`async def` 는 기다리는 동안 다른 요청을 진행시킬 뿐, 동기 호출을 비동기로 바꾸거나 CPU 작업을 병렬화하지
않습니다. 모든 path operation 은 `async def` 입니다(게이트 INV-10).

| 작업 | 기준 |
|---|---|
| DB·HTTP I/O | async client + `await` |
| 로그 출력 | 큐 핸들러가 listener 스레드로 위임(직접 파일 쓰기 금지) |
| bcrypt 같은 비싼 CPU | `asyncio.to_thread()` 또는 worker |
| 짧은 JWT·Pydantic·User-Agent 처리 | 이벤트 루프에서 동기 실행 허용 |
| SQLAlchemy metadata DDL | `AsyncConnection.run_sync()` 허용 |
| Celery 태스크 진입점 | 동기 유지, 안에서 `run_async()` |

요청 경로에서 금지 — 게이트가 일부를 AST 로 찾습니다(`open`, `input`, `time.sleep`, `shutil.copy*`,
`subprocess.run`):

```python
async def handler():
    requests.get(url)           # 동기 HTTP
    time.sleep(1)               # 이벤트 루프 정지
    open(path).write(data)      # 동기 파일 I/O
    subprocess.run(command)     # 동기 프로세스 대기
```

동기 라이브러리밖에 없으면 `asyncio.to_thread()` 로 격리하거나 Celery 로 보냅니다. 아주 짧은 CPU 연산은
스레드 전환 비용을 재 보고 정합니다.

### 10.2 요청 밖 작업

```python
async with background_db_session() as db_session:     # 별도 풀, 예외 시 rollback, 종료 시 close
    service = SomeService(db_session)
    await service.do_write()
    await db_session.commit()                         # 커밋은 호출자
```

- `Depends` 는 요청 밖에서 자동으로 풀리지 않습니다 — 컨텍스트를 열고 Service 를 직접 조립합니다.
- 요청의 세션·Service·`Request` 를 background·Celery 로 넘기지 않습니다. id 같은 값만 넘깁니다.
- `access_log_tasks`(`BackgroundTaskRunner`)는 넘치면 버리는 비핵심 로그 전용입니다. 중요한 업무는 여기에
  넣지 않습니다. Celery 도 정확히 한 번 처리를 보장하지 않으니 재시도·중복·"커밋과 enqueue 사이 실패"를
  테스트하고, 필요하면 outbox 같은 구조를 그때 고릅니다.
- background drain 은 timeout 후 남은 태스크를 `cancel()` 하고 **다시 await** 해야 태스크의 `finally`
  (세션 rollback·close)가 실행됩니다 — 현재 구현이 그렇게 합니다(ARCHITECTURE §8).

### 10.3 Celery 태스크

```python
# app/celery/tasks.py
@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        async with background_db_session() as db_session:
            stats = await UserAccessLogService(db_session).get_stats()
            return {"total": stats.total_count}

    return run_async(_run())
```

태스크는 이 파일에 모으고 이름은 `<기능>.<동작>` 으로 붙입니다. worker 수명은 ARCHITECTURE §13.

## 11. 로깅 사용법

```python
from app.utils.logs import get_logger

logger = get_logger(__name__)
logger.info("상품 생성: %s", product.id)                  # % 포맷 인자 — f-string 보다 필터링 비용이 적다
logger.error("외부 호출 실패", extra={"service": "pg", "status": 502})
try:
    ...
except Exception:
    logger.exception("작업 실패")                          # traceback 포함
```

- `BaseService` 하위 클래스는 `self.log` 를 씁니다(`LoggerMixin` — 로그에 클래스명이 들어갑니다).
- 로거 이름은 출처를 나타내는 문자열이면 됩니다. `[app=…]` 라벨은 이름이 아니라 소스 경로가 정하므로
  이름을 잘못 줘도 라벨은 맞습니다. 로깅 설정(dictConfig)에 기능별 항목을 추가하지 않습니다.
- 비밀번호·토큰·SQL 파라미터·DSN 을 로그에 넣지 않습니다. `LOG_SQL_ECHO_ENABLED` 는 로컬에서만 잠깐 켭니다.
- 포맷·레벨·출력 대상·종료 시 동작은 ARCHITECTURE §9.

## 12. 테스트

### 12.1 위치와 실행

- 기능 테스트: `app/features/<name>/tests/test_*.py`. core 계약·배선·교차 기능: `tests/`.
  실제 프로세스·DB: `tests/integration/`.
- 실행 명령·마커·CI 는 [README](../../README.md#테스트검수ci).
- 엔드포인트 테스트는 in-memory SQLite(`aiosqlite`, `StaticPool`)로 `get_writer_db_session`·
  `get_read_only_db_session` 을 **둘 다** `app.dependency_overrides` 로 바꾸고 커밋 횟수를 셉니다
  (`app/features/catalog/tests/test_endpoint.py`). 한쪽만 바꾸면 다른 경로가 실제 MySQL 로 새어 나갑니다.
  오버라이드는 테스트 끝에 복원합니다.
- `httpx.ASGITransport` 요청만으로는 lifespan 이 실행되지 않습니다. lifespan 을 검증하려면 컨텍스트에 실제로
  진입하거나(`app.router.lifespan_context`) 실제 프로세스를 띄웁니다.
- 라우트 목록은 `app.openapi()["paths"]` 로 얻습니다 — `app.routes` 는 하위 라우터를 평탄화하지 않습니다.
- SQLite 통과는 MySQL 방언·Decimal 정밀도·시간대·잠금의 근거가 아닙니다. MySQL 전용 동작은
  `@pytest.mark.mysql` 로 `tests/integration/` 에 두고, `mysql_session_maker` fixture 가 테스트마다
  스키마를 다시 만듭니다.

### 12.2 무엇을 검증하나

| 범위 | 시나리오 |
|---|---|
| Schema | 필수값·길이·범위·음수·null vs 미전달·공개 필드 |
| Service | 업무 분기·부재·기간·상태 전환 (Repository 를 fake 로) · Raw row → DTO 변환 |
| ORM Repository | create/get/list/count/exists/update/delete, 입력 dict 불변, 중복·FK·DB 오류 변환, N+1 |
| Raw Repository | bind 가 실제로 바인딩됨, one/all/scalar/rowcount, 빈 결과, 오류 변환, 사용자 값이 SQL 에 끼지 않음, 허용 밖 정렬 거부 |
| Endpoint | 성공 코드·응답 스키마, 404·409·422, `operation_id`, 권한 |
| 트랜잭션 | 조회 커밋 0회, 쓰기 성공 커밋 1회, 예외·커밋 실패가 2xx 가 아님, 읽기/쓰기 세션 선택 |
| 등록 | 라우터 마운트, 모델 metadata, Admin 뷰, 라우트 인벤토리, tag |
| 수명 | 취소·timeout·Redis 불가·정리 순서 — 건드렸다면 `tests/core/test_resources.py` 와 실제 uvicorn 테스트를 Redis 를 띄워 skip 없이 |
| 실제 DB | MySQL Decimal·날짜 경계·제약·동시 갱신·Raw 방언·migration 왕복 |

## 13. 코드 리뷰 체크리스트

- [ ] View 에 SQL·세션 주입·복잡한 도메인 분기가 없다
- [ ] Dependency 는 조립만 하고, Repository·Dependency 에 커밋이 없다
- [ ] 쓰기 View 는 응답 DTO 검증 → 커밋 1회 → 반환, 조회 View 는 읽기 의존성·커밋 0회
- [ ] Service 는 HTTP 객체를 모르고, 여러 Service 가 참여하면 같은 writer 세션을 쓴다
- [ ] ORM Repository 는 `BaseRepository`, Raw Repository 는 `RawRepositoryBase` 를 상속한다
- [ ] Raw SQL 은 named bind + 식별자 allowlist + `query_name`
- [ ] 모든 외부 응답이 Pydantic DTO 를 거친다(민감 필드 제외)
- [ ] 라우터가 v1 → 기능 `router.py` → `__init__.py` → `main.py` 로 명시 취합되고 기능명 = URL 세그먼트
- [ ] 목록 API 에 limit 상한과 고정 정렬이 있다
- [ ] 새 엔드포인트의 인증·권한을 명시했다(기본은 인증 없음)
- [ ] path operation 이 `async def` 이고 요청 경로에 동기 I/O 가 없다
- [ ] migration 을 추가·검토했고 head 가 하나다
- [ ] OpenAPI 메타데이터·tag·예시가 실제 구현과 맞다
- [ ] 단위·엔드포인트·트랜잭션·등록 테스트를 추가했고, 계약 테스트(인벤토리·Admin 목록)를 갱신했다
- [ ] README API 표와 관련 문서를 갱신했다
