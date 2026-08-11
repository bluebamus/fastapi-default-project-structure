"""
Blog 도메인 데이터베이스 모델

게시글(Post) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from config import timezone_settings


class Post(Base):
    """블로그 게시글.

    Attributes:
        id: UUID 기본키
        title: 제목
        content: 본문
        author: 작성자(선택)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "blog_posts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
        return f"<Post(id={self.id}, title={self.title!r})>"
