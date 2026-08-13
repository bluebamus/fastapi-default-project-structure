"""Reports 도메인 데이터베이스 모델 — Raw SQL 의 **원본 테이블**만 정의한다.

집계 결과용 ORM 모델은 만들지 않는다(SCN-RAW-001). 일별 매출 집계는 행 하나가
테이블의 행이 아니라 계산 결과이므로, ``RowMapping`` → Pydantic DTO 로 나간다.

그렇다면 왜 ``SalesOrder`` 는 있는가:
    이 테이블의 **생명주기를 이 프로젝트가 소유**하기 때문이다. migration 으로
    만들고 지우는 테이블이라면 metadata 에 있어야 Alembic 이 드리프트를 볼 수 있다
    (지침서 §2 의 단서). 모델이 없으면 ``compare_metadata`` 가 이 테이블을
    "지워야 할 것"으로 판정한다.

    쓰기는 이 예제 범위가 아니다 — 읽기는 Raw 집계로, 데이터는 migration/fixture 로
    넣는다.
"""

from decimal import Decimal

from sqlalchemy import Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDCreatedModel


class SalesOrder(UUIDCreatedModel):
    """주문 원장 — 일별 매출 집계의 원본.

    생성 후 변하지 않는 기록이라 ``updated_at`` 을 두지 않는다(UUIDCreatedModel).

    Attributes:
        id: UUID 기본키 (UUIDPrimaryKeyMixin)
        customer: 주문 고객 식별자
        total_amount: 주문 총액
        created_at: 주문 시각 — 집계의 기준 (CreatedAtMixin)
    """

    __tablename__ = "sales_orders"

    # 일별 집계는 created_at 범위로 스캔한다. 인덱스가 없으면 전체 스캔이 된다(NFR-002).
    # created_at 은 Mixin 이 제공하므로 컬럼 인자가 아니라 __table_args__ 로 건다.
    __table_args__ = (Index("ix_sales_orders_created_at", "created_at"),)

    customer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="주문 고객 식별자",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="주문 총액",
    )

    def __repr__(self) -> str:
        return f"<SalesOrder(id={self.id}, customer={self.customer!r})>"
