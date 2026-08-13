"""Catalog 도메인 데이터베이스 모델.

ORM workflow 의 참조 예제다 — 데이터 접근을 ORM Repository 가 담당한다.
Raw SQL 예제는 ``app/features/reports`` 와 나란히 비교하면 된다.
"""

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDTimestampModel


class Product(UUIDTimestampModel):
    """판매 상품.

    Attributes:
        id: UUID 기본키 (UUIDPrimaryKeyMixin)
        name: 상품명
        price: 판매가
        is_active: 판매 활성 여부
        created_at: 생성 시각 (CreatedAtMixin)
        updated_at: 수정 시각 (UpdatedAtMixin)
    """

    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="상품명",
    )
    # 금액은 float 를 쓰지 않는다 — 이진 부동소수는 0.1 을 정확히 담지 못해
    # 합계에서 오차가 누적된다. Numeric(12, 2) 는 Python 쪽에서 Decimal 로 온다.
    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="판매가",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="판매 활성 여부",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name!r})>"
