"""add users.is_superuser and author_id ownership columns

인가 도입(service-hardening ADR-018):

- ``users.is_superuser`` — 슈퍼유저/일반 2단계. NOT NULL, 서버 기본값 false — 기존 사용자는 모두
  일반 사용자가 된다. 첫 슈퍼유저는 ``python -m scripts.create_superuser`` 로 만든다.
- ``blog_posts``·``sns_posts``·``replies`` 의 ``author_id`` — 작성자 사용자 ID(String(36), NULL 허용,
  인덱스). 기존 행은 NULL 로 남는다 — 자유 문자열 ``author`` 로 사용자를 역추적하지 않는다. 소유자가
  없는 행은 슈퍼유저만 수정·삭제할 수 있다(residual-risk R-006). FK 는 두지 않는다 — 기능 모델끼리
  참조하지 않는 계층 규칙(C-2)과 같다.

downgrade 는 인덱스를 먼저 지우고 컬럼을 지운다(SQLite 는 인덱스가 걸린 컬럼을 지우지 못한다).

Revision ID: c9e1a3b5d7f0
Revises: a7c9e1f3b5d6
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1a3b5d7f0"
down_revision: str | None = "a7c9e1f3b5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNED_TABLES = ("blog_posts", "sns_posts", "replies")


def upgrade() -> None:
    """Upgrade schema — 슈퍼유저 플래그와 작성자 ID 를 추가한다."""
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for table in _OWNED_TABLES:
        op.add_column(table, sa.Column("author_id", sa.String(length=36), nullable=True))
        op.create_index(op.f(f"ix_{table}_author_id"), table, ["author_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema — 추가한 인덱스·컬럼을 역순으로 지운다."""
    for table in reversed(_OWNED_TABLES):
        op.drop_index(op.f(f"ix_{table}_author_id"), table_name=table)
        op.drop_column(table, "author_id")
    op.drop_column("users", "is_superuser")
