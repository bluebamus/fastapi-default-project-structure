"""User 도메인 스키마 — 사용자 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# 간단한 이메일 형식 검증(외부 email-validator 의존 없이 최소 검증).
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserBase(BaseModel):
    """사용자 공통 필드."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=_EMAIL_PATTERN, description="이메일")


class UserCreate(UserBase):
    """사용자 생성 요청."""


class UserUpdate(BaseModel):
    """사용자 수정 요청 — 전달된 필드만 부분 수정한다."""

    email: str | None = Field(None, max_length=255, pattern=_EMAIL_PATTERN, description="이메일")
    is_active: bool | None = Field(None, description="활성 여부")


class UserResponse(UserBase):
    """사용자 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """사용자 목록 응답(페이지네이션)."""

    items: list[UserResponse]
    total: int
    skip: int
    limit: int
