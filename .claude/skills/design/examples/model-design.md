# 데이터 모델 설계 예시

## E-Commerce 도메인 모델

### ER 다이어그램

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│    User      │       │    Order     │       │   Product    │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ PK id        │──┐    │ PK id        │    ┌──│ PK id        │
│ email        │  │    │ FK user_id   │────┘  │ name         │
│ password_hash│  └────│ status       │       │ price        │
│ name         │       │ total_amount │       │ stock        │
│ status       │       │ created_at   │       │ FK category_id│
│ created_at   │       └──────────────┘       └──────────────┘
│ updated_at   │              │                      │
└──────────────┘              │                      │
                              ▼                      │
                       ┌──────────────┐              │
                       │  OrderItem   │              │
                       ├──────────────┤              │
                       │ PK id        │              │
                       │ FK order_id  │◄─────────────┘
                       │ FK product_id│
                       │ quantity     │
                       │ unit_price   │
                       └──────────────┘
```

### SQLAlchemy 모델 구현

```python
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from app.order.models import Order


class UserStatus(str, Enum):
    """사용자 상태"""
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base, TimestampMixin, SoftDeleteMixin):
    """
    사용자 엔티티

    Attributes:
        id: 고유 식별자
        email: 이메일 (unique)
        password_hash: 해시된 비밀번호
        name: 사용자 이름
        status: 계정 상태
    """
    __tablename__ = "users"

    # Columns
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        default=UserStatus.PENDING,
        server_default=UserStatus.PENDING.value
    )

    # Relationships
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
        lazy="selectin"  # N+1 방지: 기본적으로 함께 로드
    )

    # Indexes
    __table_args__ = (
        Index("ix_users_email_status", "email", "status"),
        Index("ix_users_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class OrderStatus(str, Enum):
    """주문 상태"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(Base, TimestampMixin):
    """
    주문 엔티티 (Aggregate Root)

    비즈니스 규칙:
    - 주문 생성 시 재고 차감
    - 취소 시 재고 복구
    - 상태 전이 규칙 적용
    """
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=0
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",  # 주문 삭제 시 아이템도 삭제
        lazy="selectin"
    )

    # Indexes
    __table_args__ = (
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
    )

    def calculate_total(self) -> None:
        """주문 총액 계산"""
        self.total_amount = sum(
            item.quantity * item.unit_price for item in self.items
        )

    def can_cancel(self) -> bool:
        """취소 가능 여부 확인"""
        return self.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)
```

### Mixin 패턴

```python
from datetime import datetime
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class TimestampMixin:
    """생성/수정 시간 자동 관리"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class SoftDeleteMixin:
    """소프트 삭제 지원"""
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(default=False)

    def soft_delete(self) -> None:
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
```

### 인덱스 전략

| 테이블 | 인덱스 | 컬럼 | 용도 |
|--------|--------|------|------|
| users | ix_users_email_status | (email, status) | 로그인 시 활성 사용자 조회 |
| users | ix_users_created_at | (created_at) | 최근 가입자 목록 |
| orders | ix_orders_user_id | (user_id) | 사용자별 주문 조회 |
| orders | ix_orders_status | (status) | 상태별 주문 필터링 |
| orders | ix_orders_created_at | (created_at) | 기간별 주문 조회 |

### 마이그레이션 스크립트 예시

```python
"""create users and orders tables

Revision ID: abc123
"""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_users_email_status", "users", ["email", "status"])


def downgrade() -> None:
    op.drop_index("ix_users_email_status")
    op.drop_table("users")
```
