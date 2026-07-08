"""
SQLAlchemy Base 클래스

모든 ORM 모델의 기반이 되는 Base 클래스를 정의합니다.
이 파일은 모든 도메인 모듈에서 공통으로 사용됩니다.

사용법:
    from app.core.models.models_base import Base, TimestampMixin, UUIDMixin

    class MyModel(Base, TimestampMixin):
        __tablename__ = "my_table"
        ...
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import timezone_settings


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base

    모든 모델이 상속받는 기본 클래스입니다.
    공통 필드와 메서드를 제공합니다.
    """

    if TYPE_CHECKING:
        # 저장소(BaseRepository)가 관리하는 모든 모델은 UUIDMixin 을 통해 문자열 ``id``
        # 기본키를 갖는다는 것이 이 프로젝트의 불변식이다. 런타임에는 각 모델/믹스인이
        # 실제 컬럼을 정의하므로, 여기서는 제네릭 코드(self.model.id)의 타입 체크를 위한
        # 선언만 둔다(TYPE_CHECKING 가드로 런타임 매핑에는 영향을 주지 않음).
        id: Mapped[str]

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }

    def to_dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TimestampMixin:
    """
    타임스탬프 믹스인

    created_at 필드를 자동으로 추가합니다.
    설정된 타임존(기본값: Asia/Seoul)이 적용됩니다.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    UUID 기본키 믹스인

    String(36) 타입의 UUID id 필드를 자동으로 추가합니다.
    MySQL, PostgreSQL 모두 호환됩니다.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
