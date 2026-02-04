# FastAPI Default Project Structure

Repository 패턴과 Unit of Work 패턴을 적용한 FastAPI 프로젝트 템플릿입니다.

## 목차

- [개요](#개요)
- [기술 스택](#기술-스택)
- [아키텍처](#아키텍처)
- [프로젝트 구조](#프로젝트-구조)
- [데이터 흐름](#데이터-흐름)
- [핵심 패턴](#핵심-패턴)
- [시작하기](#시작하기)
- [환경 설정](#환경-설정)
- [신규 모듈 개발 가이드](#신규-모듈-개발-가이드)
- [API 문서](#api-문서)

---

## 개요

이 프로젝트는 FastAPI 기반의 확장 가능한 백엔드 애플리케이션 템플릿입니다.

### 주요 특징

- **계층 분리 아키텍처**: Router → Service → Repository → Database
- **트랜잭션 관리**: Unit of Work 패턴으로 일관된 트랜잭션 처리
- **N+1 문제 해결**: Eager Loading 전략 내장 (selectin, joined, subquery)
- **유연한 설정**: Pydantic Settings 기반 환경 변수 관리
- **구조화된 로깅**: 콘솔/파일 로그 분리, 자동 로그 로테이션
- **API 문서**: Scalar UI 기반 인터랙티브 문서
- **관리자 페이지**: SQLAdmin 통합

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 (async) |
| Database | MySQL (aiomysql) |
| Validation | Pydantic v2 |
| Migration | Alembic |
| Cache | Redis |
| Admin | SQLAdmin |
| API Docs | Scalar |
| Task Queue | Celery (예정) |

---

## 아키텍처

### 3계층 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Request                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Router (API Layer)                        │
│  - 요청/응답 처리                                              │
│  - 입력 유효성 검사 (Pydantic)                                  │
│  - 의존성 주입 (Depends)                                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 Service (Business Logic)                     │
│  - 비즈니스 로직 처리                                          │
│  - 데이터 변환 및 검증                                         │
│  - 트랜잭션 조율                                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                Repository (Data Access)                      │
│  - 데이터베이스 CRUD                                          │
│  - 쿼리 캡슐화                                                │
│  - N+1 문제 해결                                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Database (MySQL)                          │
└─────────────────────────────────────────────────────────────┘
```

### Unit of Work 패턴

```
┌───────────────────────────────────────────────────────────────┐
│                        UnitOfWork                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐   │
│  │   Repository A  │  │   Repository B  │  │  Repository C │   │
│  └─────────────────┘  └─────────────────┘  └──────────────┘   │
│                              ↑                                 │
│                         AsyncSession                           │
│                      (트랜잭션 경계 관리)                         │
└───────────────────────────────────────────────────────────────┘
```

---

## 프로젝트 구조

```
fastapi-default-project-structure/
├── main.py                      # FastAPI 앱 진입점
├── config.py                    # 환경 설정 (Pydantic Settings)
├── .env.example                 # 환경 변수 템플릿
├── pyproject.toml               # 의존성 및 도구 설정
│
├── app/
│   ├── core/                    # 핵심 인프라
│   │   ├── exception.py         # 커스텀 예외 클래스
│   │   ├── tags_metadata.py     # OpenAPI 태그 메타데이터
│   │   └── middlewares/         # 미들웨어
│   │       ├── cors_middleware.py
│   │       └── user_info_middleware.py
│   │
│   ├── database/                # 데이터베이스 인프라
│   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀
│   │   ├── unit_of_work.py      # Unit of Work 패턴
│   │   ├── redis.py             # Redis 연결
│   │   └── repositories/
│   │       └── base.py          # 제네릭 기본 Repository (40+ 메서드)
│   │
│   ├── dependencies/            # FastAPI 의존성
│   │   └── auth.py              # 인증 의존성
│   │
│   ├── utils/                   # 유틸리티
│   │   ├── logger.py            # 로깅 시스템
│   │   ├── cors.py              # CORS 유틸리티
│   │   └── pagination.py        # 페이지네이션 유틸리티
│   │
│   └── [module]/                # 기능 모듈 (home, user, blog 등)
│       ├── models/              # SQLAlchemy ORM 모델
│       │   ├── base.py          # 모듈 베이스 모델
│       │   └── models.py        # 엔티티 모델
│       │
│       ├── repositories/        # 데이터 접근 계층
│       │   └── *_repository.py  # Repository 클래스
│       │
│       ├── services/            # 비즈니스 로직 계층
│       │   ├── base.py          # 베이스 서비스
│       │   └── *_service.py     # Service 클래스
│       │
│       ├── schemas/             # Pydantic 스키마
│       │   └── *_schema.py      # 요청/응답 스키마
│       │
│       ├── api/                 # API 엔드포인트
│       │   ├── routers/
│       │   │   ├── router.py    # 버전별 라우터 집합
│       │   │   └── v1/          # v1 API
│       │   │       └── *.py     # 엔드포인트 정의
│       │   └── *_admin.py       # SQLAdmin 뷰
│       │
│       ├── worker/              # 백그라운드 태스크
│       │   └── *_task.py        # Celery 태스크
│       │
│       ├── tests/               # 테스트
│       │   └── conftest.py      # pytest 픽스처
│       │
│       └── dependency.py        # 모듈 의존성
│
├── migrations/                  # Alembic 마이그레이션
├── logs/                        # 로그 파일
├── static/                      # 정적 파일
└── docs/                        # 문서
```

### 핵심 파일 설명

| 파일 | 설명 |
|------|------|
| `config.py` | Pydantic Settings 기반 환경 설정 관리 |
| `main.py` | FastAPI 앱 생성, 미들웨어, 예외 핸들러, 라우터 등록 |
| `app/database/session.py` | SQLAlchemy 엔진, 세션 팩토리, 커넥션 풀 설정 |
| `app/database/unit_of_work.py` | 트랜잭션 경계 관리, Repository 통합 |
| `app/database/repositories/base.py` | 제네릭 CRUD 및 N+1 해결 메서드 제공 |
| `app/core/exception.py` | 커스텀 예외 계층 (4xx, 5xx, 비즈니스 예외) |
| `app/utils/logger.py` | 구조화된 로깅 시스템 (콘솔, 파일, 로테이션) |

---

## 데이터 흐름

### 요청 처리 흐름

```
1. HTTP 요청 수신
       ↓
2. 미들웨어 처리
   - CORS 검증
   - User-Agent 파싱
   - 접속 로그 수집
       ↓
3. Router 진입
   - 요청 파라미터 파싱 (Query, Path, Body)
   - Pydantic 스키마 유효성 검사
   - 세션 의존성 주입 (Depends(get_session))
       ↓
4. UnitOfWork 생성
   - 트랜잭션 경계 시작
   - Repository 인스턴스 초기화
       ↓
5. Service 호출
   - 비즈니스 로직 실행
   - 데이터 변환 및 검증
       ↓
6. Repository 호출
   - 데이터베이스 쿼리 실행
   - ORM 객체 반환
       ↓
7. 응답 반환
   - Pydantic 스키마로 직렬화
   - UnitOfWork 커밋 또는 롤백
   - HTTP 응답 전송
```

### 코드 예시

```python
# Router (API Layer)
@router.get("/access-logs")
async def get_access_logs(
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    # 1. UnitOfWork 생성 (트랜잭션 시작)
    async with UnitOfWork(session) as uow:
        # 2. Service 생성 (Repository 주입)
        service = UserAccessLogService(uow.user_access_logs)

        # 3. 비즈니스 로직 실행
        logs, total = await service.get_access_logs(skip, limit)

        # 4. 응답 반환
        return UserAccessLogListResponse(
            items=logs,
            total=total,
            skip=skip,
            limit=limit,
        )
```

### 트랜잭션 관리

```python
# 단일 트랜잭션 내 여러 작업
async with UnitOfWork() as uow:
    # 작업 1
    user = await uow.users.create({"name": "John"})

    # 작업 2
    profile = await uow.profiles.create({"user_id": user.id})

    # 작업 3
    log = await uow.access_logs.create({"user_id": user.id})

    # 모든 작업 커밋 (원자적)
    await uow.commit()
```

### 예외 발생 시 자동 롤백

```python
async with UnitOfWork() as uow:
    await uow.users.create({"name": "John"})

    # 예외 발생 시 자동 롤백
    raise BusinessException("처리 실패")

    # 이 코드는 실행되지 않음
    await uow.commit()
```

---

## 핵심 패턴

### 1. Repository 패턴

데이터 접근 로직을 캡슐화하여 비즈니스 로직과 분리합니다.

```python
# app/database/repositories/base.py
class BaseRepository(Generic[ModelType]):
    """제네릭 기본 Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # CRUD 기본 메서드
    async def create(self, data: dict) -> ModelType: ...
    async def get_by_id(self, id: str) -> ModelType | None: ...
    async def get_all(self, skip: int, limit: int) -> Sequence[ModelType]: ...
    async def update(self, id: str, data: dict) -> ModelType | None: ...
    async def delete(self, id: str) -> bool: ...

    # N+1 문제 해결 메서드
    async def get_by_id_with(self, id: str, relations: list[str]) -> ModelType | None: ...
    async def get_all_with(self, relations: list[str], strategy: str) -> Sequence[ModelType]: ...

    # 고급 쿼리
    async def get_or_create(self, filters: dict, defaults: dict) -> tuple[ModelType, bool]: ...
    async def update_or_create(self, filters: dict, data: dict) -> tuple[ModelType, bool]: ...
    async def bulk_create(self, items: list[dict]) -> list[ModelType]: ...
```

```python
# 모듈별 Repository 확장
class UserAccessLogRepository(BaseRepository[UserAccessLog]):
    """접속 로그 Repository"""

    async def get_by_ip(self, ip_address: str) -> Sequence[UserAccessLog]:
        """IP 주소로 조회"""
        stmt = select(UserAccessLog).where(
            UserAccessLog.ip_address == ip_address
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_device_type(self) -> dict[str, int]:
        """장치 유형별 통계"""
        stmt = select(
            UserAccessLog.device_type,
            func.count().label("count")
        ).group_by(UserAccessLog.device_type)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
```

### 2. Unit of Work 패턴

트랜잭션 경계를 관리하고 여러 Repository를 통합합니다.

```python
class UnitOfWork:
    """트랜잭션 경계 관리"""

    def __init__(self, session: AsyncSession | None = None):
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        if self._owns_session:
            self._session = AsyncSessionLocal()
        self._init_repositories()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()  # 예외 시 자동 롤백
        if self._owns_session:
            await self._session.close()

    def _init_repositories(self) -> None:
        """Repository 인스턴스 초기화"""
        self.user_access_logs = UserAccessLogRepository(self._session)
        self.users = UserRepository(self._session)
        # 새 모듈 추가 시 여기에 Repository 등록

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
```

### 3. Service 패턴

비즈니스 로직을 캡슐화하고 Repository를 조율합니다.

```python
class BaseService(Generic[R]):
    """제네릭 기본 Service"""

    def __init__(self, repository: R):
        self.repository = repository


class UserAccessLogService(BaseService[UserAccessLogRepository]):
    """접속 로그 비즈니스 로직"""

    async def get_access_logs(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[UserAccessLog], int]:
        """접속 로그 목록 조회"""
        logs = await self.repository.get_many(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total

    async def get_stats(self) -> AccessLogStats:
        """접속 통계 조회"""
        total = await self.repository.count()
        device_stats = await self.repository.count_by_device_type()
        os_stats = await self.repository.count_by_os()
        browser_stats = await self.repository.count_by_browser()

        return AccessLogStats(
            total_count=total,
            device_types=[...],
            os_list=[...],
            browser_list=[...],
        )
```

### 4. N+1 문제 해결

```python
# 문제: N+1 쿼리 발생
for user in users:
    print(user.posts)  # 각 사용자마다 추가 쿼리 발생

# 해결: Eager Loading
users = await repo.get_all_with(
    relations=["posts", "profile"],
    strategy="selectin"  # SELECT IN 전략
)

# Eager Loading 전략
# - selectin: SELECT ... WHERE id IN (...) - 대부분의 경우 권장
# - joined: LEFT OUTER JOIN - 1:1 관계에 적합
# - subquery: 서브쿼리 사용 - 복잡한 관계에 적합
```

---

## 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/your-repo/fastapi-default-project-structure.git
cd fastapi-default-project-structure
```

### 2. 가상환경 설정

```bash
# Poetry 사용
poetry install

# 또는 pip 사용
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일 수정
```

### 4. 데이터베이스 설정

```bash
# MySQL 데이터베이스 생성
mysql -u root -p
CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 서버 실행

```bash
# 개발 서버
python main.py

# 또는 uvicorn 직접 실행
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 접속

- API 서버: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 관리자 페이지: http://localhost:8000/admin
- 헬스체크: http://localhost:8000/health

---

## 환경 설정

### 주요 설정 항목

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `DEBUG` | `true` | 디버그 모드 (로그 레벨, 테이블 자동 생성, API 문서) |
| `ADMIN` | `true` | 관리자 페이지 활성화 (DEBUG와 독립적) |
| `ENV` | `development` | 환경 (development, staging, production) |
| `MYSQL_HOST` | `localhost` | MySQL 호스트 |
| `MYSQL_PORT` | `3306` | MySQL 포트 |
| `MYSQL_DATABASE` | `fastapi_db` | 데이터베이스 이름 |
| `REDIS_HOST` | `localhost` | Redis 호스트 |
| `LOG_FILE_ENABLED` | `true` | 파일 로그 활성화 |

### DEBUG 모드에 따른 동작

| 기능 | DEBUG=true | DEBUG=false |
|------|------------|-------------|
| 로그 레벨 | DEBUG | INFO |
| 테이블 자동 생성 | 활성화 | 비활성화 (Alembic 사용) |
| API 문서 (/docs) | 활성화 | 비활성화 |
| OpenAPI 스키마 | 활성화 | 비활성화 |
| Uvicorn reload | 활성화 | 비활성화 |

---

## 신규 모듈 개발 가이드

이 섹션에서는 새로운 기능 모듈을 추가하는 방법을 단계별로 설명합니다.

### 예시: Product 모듈 추가

#### 1단계: 디렉토리 구조 생성

```bash
mkdir -p app/product/{models,repositories,services,schemas,api/routers/v1,worker,tests}
touch app/product/__init__.py
touch app/product/models/__init__.py
touch app/product/repositories/__init__.py
touch app/product/services/__init__.py
touch app/product/schemas/__init__.py
touch app/product/api/__init__.py
touch app/product/api/routers/__init__.py
touch app/product/api/routers/v1/__init__.py
```

#### 2단계: 모델 정의

```python
# app/product/models/models.py
"""Product 모듈 데이터베이스 모델"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Integer, Numeric, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from config import timezone_settings


class Product(Base):
    """상품 모델"""

    __tablename__ = "products"

    # 기본키
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # 상품 정보
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 카테고리 (외래키 관계 예시)
    category_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("categories.id"),
        nullable=True,
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: timezone_settings.now(),
    )

    # 관계 정의 (Lazy Loading 기본)
    # category: Mapped["Category"] = relationship(back_populates="products")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name})>"
```

#### 3단계: Repository 정의

```python
# app/product/repositories/product_repository.py
"""Product Repository"""

from decimal import Decimal
from typing import Sequence

from sqlalchemy import select, func

from app.database.repositories.base import BaseRepository
from app.product.models.models import Product


class ProductRepository(BaseRepository[Product]):
    """상품 데이터 접근 Repository"""

    # 모델 클래스 지정 (BaseRepository에서 사용)
    model = Product

    async def get_active_products(
        self, skip: int = 0, limit: int = 50
    ) -> Sequence[Product]:
        """활성 상품 조회"""
        stmt = (
            select(Product)
            .where(Product.is_active == True)
            .offset(skip)
            .limit(limit)
            .order_by(Product.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_category(
        self, category_id: str
    ) -> Sequence[Product]:
        """카테고리별 상품 조회"""
        stmt = select(Product).where(Product.category_id == category_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_price_range(
        self, min_price: Decimal, max_price: Decimal
    ) -> Sequence[Product]:
        """가격 범위로 상품 조회"""
        stmt = select(Product).where(
            Product.price >= min_price,
            Product.price <= max_price,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_stock(self, product_id: str, quantity: int) -> bool:
        """재고 수량 업데이트"""
        product = await self.get_by_id(product_id)
        if not product:
            return False
        product.stock += quantity
        return True
```

#### 4단계: Service 정의

```python
# app/product/services/product_service.py
"""Product 비즈니스 로직"""

from decimal import Decimal
from typing import Sequence

from app.core.exception import NotFoundException, BadRequestException
from app.product.models.models import Product
from app.product.repositories.product_repository import ProductRepository
from app.product.schemas.product_schema import ProductCreate, ProductUpdate
from app.utils.logger import get_logger

logger = get_logger("product")


class ProductService:
    """상품 비즈니스 로직 서비스"""

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def create_product(self, data: ProductCreate) -> Product:
        """상품 생성"""
        # 비즈니스 규칙 검증
        if data.price < 0:
            raise BadRequestException("가격은 0 이상이어야 합니다.")

        product = await self.repository.create(data.model_dump())
        logger.info(f"상품 생성 완료: {product.id}")
        return product

    async def get_product(self, product_id: str) -> Product:
        """상품 조회"""
        product = await self.repository.get_by_id(product_id)
        if not product:
            raise NotFoundException(f"상품을 찾을 수 없습니다: {product_id}")
        return product

    async def get_products(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[Product], int]:
        """상품 목록 조회"""
        products = await self.repository.get_active_products(skip, limit)
        total = await self.repository.count()
        return products, total

    async def update_product(
        self, product_id: str, data: ProductUpdate
    ) -> Product:
        """상품 수정"""
        product = await self.repository.update(
            product_id,
            data.model_dump(exclude_unset=True)
        )
        if not product:
            raise NotFoundException(f"상품을 찾을 수 없습니다: {product_id}")
        logger.info(f"상품 수정 완료: {product_id}")
        return product

    async def delete_product(self, product_id: str) -> bool:
        """상품 삭제"""
        success = await self.repository.delete(product_id)
        if not success:
            raise NotFoundException(f"상품을 찾을 수 없습니다: {product_id}")
        logger.info(f"상품 삭제 완료: {product_id}")
        return True

    async def update_stock(
        self, product_id: str, quantity: int
    ) -> Product:
        """재고 수정"""
        product = await self.get_product(product_id)

        new_stock = product.stock + quantity
        if new_stock < 0:
            raise BadRequestException("재고가 부족합니다.")

        await self.repository.update_stock(product_id, quantity)
        logger.info(f"재고 수정: {product_id}, 변경량: {quantity}")
        return product
```

#### 5단계: Schema 정의

```python
# app/product/schemas/product_schema.py
"""Product Pydantic 스키마"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductBase(BaseModel):
    """상품 공통 필드"""
    name: str = Field(..., max_length=200, description="상품명")
    description: Optional[str] = Field(None, description="상품 설명")
    price: Decimal = Field(..., ge=0, description="가격")
    stock: int = Field(default=0, ge=0, description="재고 수량")
    is_active: bool = Field(default=True, description="활성화 여부")
    category_id: Optional[str] = Field(None, description="카테고리 ID")


class ProductCreate(ProductBase):
    """상품 생성 요청"""
    pass


class ProductUpdate(BaseModel):
    """상품 수정 요청 (부분 업데이트)"""
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    stock: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    category_id: Optional[str] = None


class ProductResponse(ProductBase):
    """상품 응답"""
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    """상품 목록 응답"""
    items: list[ProductResponse]
    total: int
    skip: int
    limit: int
```

#### 6단계: Router 정의

```python
# app/product/api/routers/v1/product.py
"""Product API 엔드포인트"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import ErrorResponse
from app.database.session import get_session
from app.database.unit_of_work import UnitOfWork
from app.product.schemas.product_schema import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
)
from app.product.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Product"])


@router.get(
    "",
    response_model=ProductListResponse,
    summary="상품 목록 조회",
)
async def get_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """상품 목록을 페이지네이션하여 조회합니다."""
    async with UnitOfWork(session) as uow:
        service = ProductService(uow.products)
        products, total = await service.get_products(skip, limit)
        return ProductListResponse(
            items=products,
            total=total,
            skip=skip,
            limit=limit,
        )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=201,
    summary="상품 생성",
)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
):
    """새 상품을 생성합니다."""
    async with UnitOfWork(session) as uow:
        service = ProductService(uow.products)
        product = await service.create_product(data)
        await uow.commit()
        return product


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
    summary="상품 상세 조회",
)
async def get_product(
    product_id: str = Path(..., description="상품 ID"),
    session: AsyncSession = Depends(get_session),
):
    """상품 상세 정보를 조회합니다."""
    async with UnitOfWork(session) as uow:
        service = ProductService(uow.products)
        return await service.get_product(product_id)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorResponse}},
    summary="상품 수정",
)
async def update_product(
    product_id: str,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
):
    """상품 정보를 수정합니다."""
    async with UnitOfWork(session) as uow:
        service = ProductService(uow.products)
        product = await service.update_product(product_id, data)
        await uow.commit()
        return product


@router.delete(
    "/{product_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
    summary="상품 삭제",
)
async def delete_product(
    product_id: str,
    session: AsyncSession = Depends(get_session),
):
    """상품을 삭제합니다."""
    async with UnitOfWork(session) as uow:
        service = ProductService(uow.products)
        await service.delete_product(product_id)
        await uow.commit()
```

#### 7단계: UnitOfWork에 Repository 등록

```python
# app/database/unit_of_work.py
def _init_repositories(self) -> None:
    """Repository 인스턴스 초기화"""
    from app.home.repositories.user_access_log_repository import (
        UserAccessLogRepository,
    )
    from app.product.repositories.product_repository import (
        ProductRepository,  # 추가
    )

    self.user_access_logs = UserAccessLogRepository(self._session)
    self.products = ProductRepository(self._session)  # 추가
```

#### 8단계: 라우터 등록

```python
# app/product/api/routers/router.py
from fastapi import APIRouter

from app.product.api.routers.v1 import product

product_router = APIRouter()
product_router.include_router(product.router, prefix="/v1")
```

```python
# main.py
from app.product.api.routers.router import product_router

app.include_router(product_router, prefix="/api")
```

#### 9단계: 테이블 생성 등록

```python
# app/database/session.py - create_db_tables() 함수
from app.product.models.models import Product  # noqa: F401

tables_to_create = [
    UserAccessLog.__table__,
    Product.__table__,  # 추가
]
```

#### 10단계: Admin 뷰 추가 (선택)

```python
# app/product/api/product_admin.py
from sqladmin import ModelView
from app.product.models.models import Product


class ProductAdmin(ModelView, model=Product):
    name = "상품"
    name_plural = "상품"
    icon = "fa-solid fa-box"

    column_list = [
        Product.id,
        Product.name,
        Product.price,
        Product.stock,
        Product.is_active,
        Product.created_at,
    ]

    column_searchable_list = [Product.name]
    column_filters = [Product.is_active, Product.price]

    can_create = True
    can_edit = True
    can_delete = True
```

```python
# main.py
from app.product.api.product_admin import ProductAdmin

admin.add_view(ProductAdmin)
```

### 개발 체크리스트

새 모듈 개발 시 확인해야 할 항목:

- [ ] 모델 정의 (`models/models.py`)
- [ ] Repository 구현 (`repositories/*_repository.py`)
- [ ] Service 구현 (`services/*_service.py`)
- [ ] Schema 정의 (`schemas/*_schema.py`)
- [ ] Router 구현 (`api/routers/v1/*.py`)
- [ ] UnitOfWork에 Repository 등록 (`database/unit_of_work.py`)
- [ ] 메인 라우터에 등록 (`main.py`)
- [ ] 테이블 생성 등록 (`database/session.py`)
- [ ] Admin 뷰 추가 (선택)
- [ ] 테스트 작성 (`tests/`)
- [ ] API 문서 확인 (`/docs`)

---

## API 문서

### 접근 URL

| 문서 | URL | 조건 |
|------|-----|------|
| Scalar API 문서 | http://localhost:8000/docs | DEBUG=true |
| OpenAPI JSON | http://localhost:8000/openapi.json | DEBUG=true |
| 관리자 페이지 | http://localhost:8000/admin | ADMIN=true |
| 헬스체크 | http://localhost:8000/health | 항상 |

### 현재 구현된 API

#### Home 모듈 (접속 로그)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/access-logs` | 접속 로그 목록 (페이지네이션) |
| GET | `/api/v1/access-logs/recent` | 최근 접속 로그 |
| GET | `/api/v1/access-logs/by-ip/{ip}` | IP별 접속 로그 |
| GET | `/api/v1/access-logs/by-user/{user_id}` | 사용자별 접속 로그 |
| GET | `/api/v1/access-logs/stats` | 접속 통계 |

---

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 문서](https://docs.sqlalchemy.org/en/20/)
- [Pydantic v2 문서](https://docs.pydantic.dev/latest/)
- [How to structure your FastAPI projects](https://medium.com/@amirm.lavasani/how-to-structure-your-fastapi-projects-0219a6600a8f)

---

## 라이선스

MIT License
