"""store datetimes as UTC DATETIME(6)

⚠️ 배포 전 확인 — 이 리비전은 기존 MySQL 시각 값이 모두 **+09:00(Asia/Seoul)** 으로 저장됐다고
가정하고 UTC 로 옮긴다. 다른 시간대로 운영하던 DB 라면 **적용 전에** 아래 ``_LEGACY_OFFSET`` 을 그
지역의 오프셋으로 바꾼다. 값을 고쳐 쓰는 리비전이므로 적용 전에 반드시 백업한다
(README 「운영 배포 체크리스트」, service-hardening residual-risk R-011).

시각 정책 변경(service-hardening ADR-010): DB 의 모든 시각 컬럼은 **UTC 벽시계**를
**마이크로초**까지 담는다. 이전에는 Asia/Seoul 벽시계가 오프셋 없이 ``DATETIME``(fsp 0)에
들어가 소수 초가 반올림됐다(자정 직전 값이 다음 날로 넘어간다).

MySQL:
    1. 컬럼을 ``DATETIME(6)`` 으로 넓힌다(NOT NULL·comment 유지). 넓히는 쪽은 값을 바꾸지 않는다.
    2. 기존 값을 ``CONVERT_TZ(col, '+09:00', '+00:00')`` 로 UTC 로 옮긴다.
       **가정:** 기존 값은 모두 Asia/Seoul 로 적혔고, Asia/Seoul 은 DST 가 없어 항상 +09:00 이다.
       숫자 오프셋을 쓰므로 MySQL 시간대 테이블이 필요 없다. 다른 TIME_ZONE 으로 운영하던 DB 는
       이 리비전을 그대로 적용하면 안 된다 — 오프셋을 그 지역 값으로 바꿔야 한다.
SQLite:
    no-op. SQLite 는 시각을 마이크로초까지 문자열로 저장하고 타입 자릿수가 없다. 개발·테스트용
    DB 라 기존 값 변환은 하지 않는다(필요하면 DB 를 다시 만든다).

downgrade 는 역순이다 — UTC → +09:00 으로 되돌린 뒤 ``DATETIME``(fsp 0)으로 줄인다.
줄일 때 MySQL 은 소수 초를 반올림한다(이전 상태와 같은 정밀도로 돌아간다).

Revision ID: a7c9e1f3b5d6
Revises: e5f7a9b1c4d5
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "a7c9e1f3b5d6"
down_revision: str | None = "e5f7a9b1c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (테이블, 컬럼, comment) — 이 리비전 시점의 모든 시각 컬럼. 전부 NOT NULL 이다.
# 모델을 import 하지 않는다: 리비전은 작성 시점의 스키마를 고정해야 한다.
_DATETIME_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    ("user_access_logs", "created_at", None),
    ("users", "created_at", None),
    ("users", "updated_at", None),
    ("blog_posts", "created_at", None),
    ("blog_posts", "updated_at", None),
    ("replies", "created_at", None),
    ("replies", "updated_at", None),
    ("sns_posts", "created_at", None),
    ("sns_posts", "updated_at", None),
    ("catalog_products", "created_at", None),
    ("catalog_products", "updated_at", None),
    ("sales_orders", "created_at", None),
    ("sales_daily_snapshots", "generated_at", "적재 시각 — Raw DML 이 바인드 파라미터로 채운다"),
)

# Asia/Seoul 은 DST 가 없어 항상 +09:00 이다(위 docstring 의 가정).
_LEGACY_OFFSET = "+09:00"
_UTC_OFFSET = "+00:00"


def _alter(table: str, column: str, comment: str | None, *, to_type: sa.types.TypeEngine) -> None:
    op.alter_column(
        table,
        column,
        type_=to_type,
        existing_nullable=False,
        existing_comment=comment,
        # MySQL 의 MODIFY 는 comment 를 다시 적지 않으면 지운다.
        comment=comment,
    )


def _convert(table: str, column: str, *, from_offset: str, to_offset: str) -> None:
    # 식별자는 위 상수에서만 온다(요청값이 아니다). 오프셋 두 개도 코드 상수다.
    op.execute(
        sa.text(f"UPDATE `{table}` SET `{column}` = CONVERT_TZ(`{column}`, :src, :dst)").bindparams(
            src=from_offset, dst=to_offset
        )
    )


def upgrade() -> None:
    if op.get_context().dialect.name != "mysql":
        return
    for table, column, comment in _DATETIME_COLUMNS:
        _alter(table, column, comment, to_type=mysql.DATETIME(fsp=6))
        _convert(table, column, from_offset=_LEGACY_OFFSET, to_offset=_UTC_OFFSET)


def downgrade() -> None:
    if op.get_context().dialect.name != "mysql":
        return
    for table, column, comment in _DATETIME_COLUMNS:
        _convert(table, column, from_offset=_UTC_OFFSET, to_offset=_LEGACY_OFFSET)
        _alter(table, column, comment, to_type=mysql.DATETIME())
