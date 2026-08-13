"""
User 도메인 데이터베이스 모델

사용자(User) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDTimestampModel


class User(UUIDTimestampModel):
    """사용자.

    Attributes:
        id: UUID 기본키 (UUIDPrimaryKeyMixin)
        username: 사용자명(고유)
        email: 이메일
        is_active: 활성 여부
        created_at: 생성 시각 (CreatedAtMixin)
        updated_at: 수정 시각 (UpdatedAtMixin)
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # 인증(auth 도메인)용 bcrypt 해시. 비밀번호 없이 생성된 기존 사용자를 위해 nullable.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r})>"
