"""add sales_orders

Raw SQL workflow 참조 예제(app/features/reports)가 집계하는 **원본** 주문 테이블.
집계 결과용 테이블이 아니다 — 결과는 SQL 이 계산해 RowMapping 으로 나간다.

생성 후 변하지 않는 원장이라 ``updated_at`` 이 없다(UUIDCreatedModel).

Revision ID: d4e6f8a0b2c3
Revises: c3d5e7f9a1b2
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a0b2c3"
down_revision: str | None = "c3d5e7f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer", sa.String(length=100), nullable=False, comment="주문 고객 식별자"),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            comment="주문 총액",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sales_orders_customer"),
        "sales_orders",
        ["customer"],
        unique=False,
    )
    # 일별 매출 집계는 created_at 범위로 스캔한다. 인덱스가 없으면 전체 스캔이다.
    op.create_index(
        op.f("ix_sales_orders_created_at"),
        "sales_orders",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sales_orders_created_at"), table_name="sales_orders")
    op.drop_index(op.f("ix_sales_orders_customer"), table_name="sales_orders")
    op.drop_table("sales_orders")
