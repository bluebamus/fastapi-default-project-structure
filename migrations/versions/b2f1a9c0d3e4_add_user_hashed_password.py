"""add users.hashed_password for auth

Revision ID: b2f1a9c0d3e4
Revises: f4adf0ae24ea
Create Date: 2026-07-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2f1a9c0d3e4'
down_revision: str | Sequence[str] | None = 'f4adf0ae24ea'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — add nullable bcrypt hash column for auth."""
    op.add_column(
        'users',
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'hashed_password')
