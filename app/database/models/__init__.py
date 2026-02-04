"""
데이터베이스 모델 공통 모듈

모든 도메인 모듈에서 사용하는 Base 클래스와 Mixin을 제공합니다.
"""

from app.database.models.base import Base, TimestampMixin, UUIDMixin

__all__ = ["Base", "TimestampMixin", "UUIDMixin"]
