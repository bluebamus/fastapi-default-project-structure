"""
Blog 도메인 데이터베이스 모델

게시글(Post) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDTimestampModel


class Post(UUIDTimestampModel):
    """블로그 게시글.

    Attributes:
        id: UUID 기본키 (UUIDPrimaryKeyMixin)
        title: 제목
        content: 본문
        author: 작성자(선택)
        created_at: 생성 시각 (CreatedAtMixin)
        updated_at: 수정 시각 (UpdatedAtMixin)
    """

    __tablename__ = "blog_posts"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, title={self.title!r})>"
