"""공통 ORM 모델 기반 — Declarative Base 와 공통 필드 Mixin (ORM-MDL-001/002).

모든 테이블에 같은 컬럼을 강제하지 않는다. 대신 **작은 Mixin 을 조합**한다.
접속 로그처럼 생성 후 변하지 않는 테이블에 ``updated_at`` 을 억지로 붙이면
"한 번도 갱신되지 않는 컬럼"이 생겨 의미가 없고, 인덱스·용량만 늘어난다.

조합 규칙::

    변경 가능한 엔티티   -> UUIDTimestampModel  (id + created_at + updated_at)
    생성 후 불변 로그    -> UUIDCreatedModel    (id + created_at)
    외부 시스템 PK 사용  -> 시간 Mixin 만 조합하고 PK 는 모델이 직접 선언

사용법::

    from app.core.models.models_base import UUIDTimestampModel

    class Product(UUIDTimestampModel):
        __tablename__ = "catalog_products"
        name: Mapped[str] = mapped_column(String(200), nullable=False)

컬럼 순서에 관하여:
    ``sort_order`` 로 **id 가 맨 앞, 시각 컬럼이 맨 뒤**가 되도록 고정한다.
    지정하지 않으면 Mixin 컬럼이 모델 자신의 컬럼보다 앞에 몰려, ``create_all``
    로 만든 개발 DB 와 migration 으로 만든 운영 DB 의 물리적 컬럼 순서가 갈린다.
    기존 테이블과 동일한 순서를 유지하는 것이 이 값들의 목적이다
    (검증: ``tests/core/test_schema_snapshot.py``).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import timezone_settings

# 컬럼 정렬 기준값. 모델 자신의 컬럼은 기본값 0 이므로 그 사이에 놓인다.
_PRIMARY_KEY_SORT_ORDER = -100
_CREATED_AT_SORT_ORDER = 100
_UPDATED_AT_SORT_ORDER = 101


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base

    모든 모델이 상속받는 기본 클래스입니다.
    """

    if TYPE_CHECKING:
        # 저장소(BaseRepository)가 관리하는 모든 모델은 UUIDPrimaryKeyMixin 을 통해
        # 문자열 ``id`` 기본키를 갖는다는 것이 이 프로젝트의 불변식이다. 런타임에는
        # 각 모델/믹스인이 실제 컬럼을 정의하므로, 여기서는 제네릭 코드(self.model.id)의
        # 타입 체크를 위한 선언만 둔다(TYPE_CHECKING 가드로 런타임 매핑에 영향 없음).
        id: Mapped[str]

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }

    def to_dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class UUIDPrimaryKeyMixin:
    """String(36) UUID 기본키.

    네이티브 UUID 타입 대신 문자열을 쓰는 이유는 MySQL·PostgreSQL·SQLite 에서
    같은 정의로 동작하고, 값을 눈으로 읽을 수 있기 때문이다.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        sort_order=_PRIMARY_KEY_SORT_ORDER,
    )


class CreatedAtMixin:
    """생성 시각. 설정된 타임존(기본 Asia/Seoul)이 적용된다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
        sort_order=_CREATED_AT_SORT_ORDER,
    )


class UpdatedAtMixin:
    """수정 시각. ORM 을 통한 UPDATE 마다 자동 갱신된다.

    ``onupdate`` 는 **ORM/Core 가 발행하는 UPDATE** 에서만 동작한다. Raw SQL 로
    직접 UPDATE 하면 갱신되지 않으므로, Raw DML 을 쓰는 곳은 이 컬럼을 SQL 에서
    명시적으로 다뤄야 한다.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        onupdate=lambda: timezone_settings.now(),
        nullable=False,
        sort_order=_UPDATED_AT_SORT_ORDER,
    )


class UUIDTimestampModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin):
    """변경 가능한 엔티티의 기반 — id + created_at + updated_at."""

    __abstract__ = True


class UUIDCreatedModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """생성 후 불변인 로그성 테이블의 기반 — id + created_at.

    ``updated_at`` 을 일부러 갖지 않는다. 갱신되지 않는 컬럼은 읽는 사람에게
    "언젠가 갱신될 수 있다"는 잘못된 신호를 준다.
    """

    __abstract__ = True
