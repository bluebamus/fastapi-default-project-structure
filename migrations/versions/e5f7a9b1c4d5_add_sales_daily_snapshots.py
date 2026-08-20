"""add sales_daily_snapshots

Raw **쓰기** workflow 참조 예제(app/features/reports)가 적재하는 집계 스냅샷 테이블.

``sales_orders`` 는 불변 원장이라 고칠 수 없다. 그래서 Raw 쓰기 예제는 원장을
UPDATE 하지 않고, 집계 결과를 이 테이블에 ``INSERT ... SELECT`` 로 싣는다.

기본키가 ``sales_date`` 인 이유: 행 하나가 하루이므로 하루가 곧 유일한 키다.
대리키를 얹으면 "같은 날짜 두 줄" 이 스키마상 가능해져 리포트가 두 배로 보인다.

Revision ID: e5f7a9b1c4d5
Revises: d4e6f8a0b2c3
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7a9b1c4d5"
down_revision: str | None = "d4e6f8a0b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sales_daily_snapshots",
        sa.Column("sales_date", sa.Date(), nullable=False, comment="매출 일자 (자연 기본키)"),
        sa.Column("order_count", sa.Integer(), nullable=False, comment="그날의 주문 수"),
        sa.Column(
            "gross_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            comment="그날의 총 매출",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="적재 시각 — Raw DML 이 바인드 파라미터로 채운다",
        ),
        sa.PrimaryKeyConstraint("sales_date"),
    )
    # 신선도 조회("마지막 적재가 언제인가")가 전체 스캔이 되지 않게 한다.
    op.create_index(
        op.f("ix_sales_daily_snapshots_generated_at"),
        "sales_daily_snapshots",
        ["generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sales_daily_snapshots_generated_at"),
        table_name="sales_daily_snapshots",
    )
    op.drop_table("sales_daily_snapshots")
