"""UTC 저장 시각 타입 — ``UTCDateTime`` (service-hardening ADR-010, C-5).

DB 에는 **UTC 벽시계를 오프셋 없이** 넣고, 꺼낼 때 UTC 를 붙여 aware 로 돌려준다.
MySQL 의 ``DATETIME`` 은 오프셋을 저장하지 않으므로 "무엇을 기준으로 적었는가" 는 코드가
정해야 한다 — 그 규칙을 이 타입 하나가 강제한다.

- bind: aware → UTC 로 바꾼 뒤 tzinfo 를 뗀다. **naive 는 ``ValueError``** — naive 값은
  KST 인지 UTC 인지 알 수 없어, 조용히 받으면 9시간 어긋난 값이 저장된다(검수 R-05 의 원인).
- result: DB 가 돌려준 naive 값에 UTC 를 붙인다. 응답 JSON 은 ``Z`` 오프셋을 갖는다.
- MySQL 은 ``DATETIME(6)`` — 기본 ``DATETIME`` 은 소수 초를 반올림해 자정 직전 값이 다음 날로
  넘어갈 수 있다. 다른 방언은 ``DateTime()``(SQLite 는 문자열로 마이크로초까지 보존한다).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class UTCDateTime(TypeDecorator[datetime]):
    """aware datetime 만 받아 UTC 로 저장하고, UTC aware 로 돌려주는 컬럼 타입."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "naive datetime 은 저장할 수 없습니다 — 기준 시간대가 없어 UTC 로 바꿀 수 없다. "
                "timezone_settings.utc_now() 또는 tzinfo 가 있는 값을 쓰세요."
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def compare_type(
    context: Any,
    inspected_column: Any,
    metadata_column: Any,
    inspected_type: TypeEngine[Any],
    metadata_type: TypeEngine[Any],
) -> bool | None:
    """Alembic 비교 훅 — MySQL 의 ``UTCDateTime`` 컬럼이 ``DATETIME(6)`` 인지 본다.

    Alembic 기본 비교는 반영된 쪽 인자가 비어 있으면 인자를 비교하지 않아, DB 가
    ``DATETIME``(fsp 0)인데 모델이 ``DATETIME(6)`` 이어도 드리프트로 보지 않는다. 리비전을
    빠뜨린 DB 를 ``alembic check`` 가 통과시키지 않도록 소수 초 자릿수를 직접 비교한다.
    그 밖의 경우는 ``None`` 으로 기본 비교에 맡긴다.
    """
    if isinstance(metadata_type, UTCDateTime) and context.dialect.name == "mysql":
        return getattr(inspected_type, "fsp", None) != 6
    return None


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Alembic autogenerate 가 ``UTCDateTime`` 을 앱 import 없는 표현으로 쓰게 한다.

    기본 렌더링은 ``app.core.models.types.UTCDateTime()`` 인데 import 를 붙이지 않아, 생성된
    리비전이 실행 시 NameError 로 깨진다. 마이그레이션은 앱 코드에 기대지 않아야 하므로
    같은 DDL 을 내는 ``sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")`` 로 쓴다.
    다른 항목은 ``False`` 를 돌려 Alembic 기본 렌더링에 맡긴다.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return 'sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")'
    return False
