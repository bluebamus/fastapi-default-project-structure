"""add catalog_products

ORM workflow 참조 예제(app/features/catalog)의 상품 테이블.

컬럼 순서는 모델의 ``sort_order`` 와 같다 — id 가 맨 앞, 시각 컬럼이 맨 뒤.
``create_all`` 로 만든 개발 DB 와 migration 으로 만든 운영 DB 의 물리 구조를
일치시키기 위한 것이다.

Revision ID: c3d5e7f9a1b2
Revises: b2f1a9c0d3e4
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: str | None = "b2f1a9c0d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="상품명"),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False, comment="판매가"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="판매 활성 여부"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_catalog_products_name"),
        "catalog_products",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_catalog_products_name"), table_name="catalog_products")
    op.drop_table("catalog_products")
