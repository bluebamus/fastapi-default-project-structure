"""User 도메인 스키마 — 사용자 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema
from app.utils.validators import EMAIL_PATTERN


class UserBase(BaseModel):
    """사용자 공통 필드."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")


class UserCreate(UserBase):
    """사용자 생성 요청(슈퍼유저 전용).

    비밀번호는 필수다 — 로그인할 수 없는 계정을 만들지 않는다(service-hardening ADR-020).
    저장은 Argon2 해시로만 한다.
    """

    password: str = Field(..., min_length=8, max_length=128, description="비밀번호(8자 이상)")
    is_superuser: bool = Field(False, description="슈퍼유저로 만들지 여부")


class UserUpdate(PatchSchema):
    """사용자 수정 요청 — 전달된 필드만 부분 수정한다.

    모든 컬럼이 NOT NULL 이라 명시적 ``null`` 은 422 다(``PatchSchema``). ``is_active``·``is_superuser``
    는 슈퍼유저만 바꿀 수 있다(본인 수정이라도 403).
    """

    # 슈퍼유저만 보낼 수 있는 필드 — 서비스가 이 집합으로 판정한다.
    superuser_only_fields: ClassVar[frozenset[str]] = frozenset({"is_active", "is_superuser"})

    email: str | None = Field(None, max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    is_active: bool | None = Field(
        None,
        description="활성 여부(슈퍼유저 전용). false 면 그 사용자의 refresh 토큰을 모두 폐기한다",
    )
    is_superuser: bool | None = Field(None, description="슈퍼유저 여부(슈퍼유저 전용)")


class UserResponse(UserBase):
    """사용자 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="사용자 ID(UUID)")
    is_active: bool = Field(..., description="활성 여부")
    is_superuser: bool = Field(..., description="슈퍼유저 여부")
    created_at: datetime = Field(..., description="생성 시각(UTC)")
    updated_at: datetime = Field(..., description="마지막 수정 시각(UTC)")


class UserListResponse(BaseModel):
    """사용자 목록 응답(페이지네이션)."""

    items: list[UserResponse] = Field(..., description="현재 페이지의 사용자 목록")
    total: int = Field(..., description="조건에 해당하는 전체 사용자 수")
    skip: int = Field(..., description="건너뛴 개수(요청한 `skip`)")
    limit: int = Field(..., description="페이지 크기(요청한 `limit`)")
