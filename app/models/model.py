import uuid
from pydantic import BaseModel
from starlette.authentication import BaseUser
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Table,
    Index,
    UniqueConstraint,
    CheckConstraint,
    text,
    func,
    PrimaryKeyConstraint,
    Enum,
)
from app.utils.authentication import generate_password_hash, check_password_hash
from sqlalchemy.orm import Mapped, mapped_column, relationship, DynamicMapped, backref
from sqlalchemy.ext.mutable import MutableDict


class UUIDMixin:
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, nullable=False, autoincrement=True
    )
    username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(60), nullable=False)
    # age_level 컬럼을 Enum으로 정의
    age_level_choices = ["10", "20", "30", "40", "50", "60", "70", "80"]
    age_level: Mapped[str] = mapped_column(
        Enum(*age_level_choices, name="age_level_enum"),
        nullable=False,
        default="10",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # One-to-many relationship with Post (DynamicMapped + lazy="dynamic")
    posts_user: Mapped[list["Post"]] = relationship("Post", back_populates="user_posts")

    # # Many-to-many relationship with Group
    # user_groups: DynamicMapped["UserGroupAssociation"] = relationship(
    #     "UserGroupAssociation", back_populates="user", lazy="dynamic"
    # )
    # n:m 관계 (Group) – 최적의 lazy 옵션: selectin
    group_user: Mapped[list["Group"]] = relationship(
        "Group",
        secondary="user_group_association",
        back_populates="user_group",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"User(id={self.id}, username={self.username}, is_active={self.is_active})"
        )

    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def display_name(self) -> str:
        return self.username

    @property
    def identity(self) -> str:
        return self.username


# 1:1 Relationship - User Profile
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name = Column(String(255))
    bio = Column(String(1000))
    avatar_url = Column(String(255))
    phone_number = Column(String(20))
    address = Column(String(500))
    # preferences = Column(MutableDict.as_mutable(JSONB), default={}) //sqlite 지원 안함
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # One-to-one relationship with User
    user: Mapped["User"] = relationship(
        "User", backref=backref("profile", uselist=False, cascade="all, delete-orphan")
    )

    def __repr__(self) -> str:
        return f"UserProfile(id={self.id}, user_id={self.user_id}, full_name={self.full_name})"

    __table_args__ = (Index("idx_user_profiles_user_id", "user_id"),)


# 1:N Relationship - Posts
class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(10000), nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    # tags: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), default=[]) // sqlite 지원 안함
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    # Many-to-one relationship with User (using dynamic loading)
    user_posts: Mapped["User"] = relationship("User", back_populates="posts_user")

    def __repr__(self) -> str:
        return f"Post(id={self.id}, user_id={self.user_id}, title={self.title})"

    __table_args__ = (
        Index("idx_posts_user_id", "user_id"),
        Index("idx_posts_created_at", "created_at"),
        Index(
            "idx_posts_user_id_created_at", "user_id", "created_at"
        ),  # Composite index
    )


# N:M Relationship - Users and Groups
# Association table for many-to-many relationship
# N:M Association Table (중간 테이블)
class UserGroupAssociation(Base):
    __tablename__ = "user_group_association"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )

    # # 관계 정의
    # user: Mapped["User"] = relationship("User", back_populates="user_groups")
    # group: Mapped["Group"] = relationship("Group", back_populates="group_users")
    # # 복합 기본 키 설정

    # 기본 키 설정을 위한 __table_args__ 추가
    __table_args__ = (PrimaryKeyConstraint("user_id", "group_id"),)

    def __repr__(self) -> str:
        return f"UserGroupAssociation(user_id={self.user_id}, group_id={self.group_id})"


# Group 테이블
class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1000))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )

    user_group: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_group_association",
        back_populates="group_user",
        lazy="selectin",
    )

    # Group을 만든 사용자와 관계 (일반적인 1:N 관계)
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"Group(id={self.id}, name={self.name})"

    __table_args__ = (
        Index("idx_groups_created_by_id", "created_by_id"),
        Index("idx_groups_name", "name"),
        Index("idx_groups_is_public", "is_public"),
        Index("idx_groups_created_at", "created_at"),
        Index("idx_groups_composite", "is_public", "created_at"),
    )
