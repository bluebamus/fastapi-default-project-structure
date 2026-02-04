"""
User 모듈 Base 클래스

공통 Base 모듈을 re-export합니다.
기존 import 호환성을 위해 유지됩니다.

사용법:
    from app.user.models.base import Base, TimestampMixin, UUIDMixin
    # 또는 직접 공통 모듈에서 import
    from app.database.models.base import Base, TimestampMixin, UUIDMixin
"""

from app.database.models.base import Base, TimestampMixin, UUIDMixin

__all__ = ["Base", "TimestampMixin", "UUIDMixin"]
