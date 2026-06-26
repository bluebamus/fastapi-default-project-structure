"""
SNS 도메인 데이터베이스 모델

소셜 피드 게시물(SnsPost) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from config import timezone_settings


class SnsPost(Base):
    """SNS 피드 게시물.

    Attributes:
        id: UUID 기본키
        content: 게시물 본문
        author: 작성자(선택)
        like_count: 좋아요 수
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "sns_posts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        onupdate=lambda: timezone_settings.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SnsPost(id={self.id}, author={self.author})>"
