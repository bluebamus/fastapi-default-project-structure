# 라우터 구현 예시

## UserRouter 전체 구현

```python
"""
사용자 API 라우터

사용자 관련 RESTful API 엔드포인트를 정의합니다.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.session import get_session
from app.auth.dependencies import get_current_user, get_current_admin
from app.user.models import User, UserStatus
from app.user.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    PaginationParams,
)
from app.user.services.user import UserService
from app.user.dependencies import get_user_service

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


# ==================== 공개 엔드포인트 ====================

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="사용자 생성",
    description="새로운 사용자 계정을 생성합니다.",
    responses={
        201: {"description": "사용자 생성 성공"},
        409: {"description": "이메일 중복"},
        422: {"description": "유효성 검사 실패"},
    },
)
async def create_user(
    data: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """
    새로운 사용자를 생성합니다.

    - **email**: 유일한 이메일 주소
    - **password**: 8자 이상, 대소문자/숫자 포함
    - **name**: 사용자 이름
    - **phone**: 연락처 (선택)
    """
    user = await service.create(data)
    return UserResponse.model_validate(user)


# ==================== 인증 필요 엔드포인트 ====================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="내 정보 조회",
    description="현재 로그인한 사용자의 정보를 조회합니다.",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """현재 사용자 정보를 반환합니다."""
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="내 정보 수정",
    description="현재 로그인한 사용자의 정보를 수정합니다.",
)
async def update_me(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """현재 사용자 정보를 수정합니다."""
    user = await service.update(current_user.id, data)
    return UserResponse.model_validate(user)


# ==================== 관리자 전용 엔드포인트 ====================

@router.get(
    "",
    response_model=UserListResponse,
    summary="사용자 목록 조회",
    description="모든 사용자 목록을 페이지네이션하여 조회합니다. (관리자 전용)",
    dependencies=[Depends(get_current_admin)],
)
async def get_users(
    service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int, Query(ge=1, description="페이지 번호")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="페이지 크기")] = 20,
    status: Annotated[UserStatus | None, Query(description="상태 필터")] = None,
    search: Annotated[str | None, Query(description="검색어 (이름/이메일)")] = None,
) -> UserListResponse:
    """
    사용자 목록을 조회합니다.

    페이지네이션, 상태 필터링, 검색 기능을 제공합니다.
    """
    params = PaginationParams(page=page, size=size)
    return await service.get_list(params, status=status, search=search)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 상세 조회",
    description="특정 사용자의 상세 정보를 조회합니다. (관리자 전용)",
    dependencies=[Depends(get_current_admin)],
    responses={
        200: {"description": "조회 성공"},
        404: {"description": "사용자를 찾을 수 없음"},
    },
)
async def get_user(
    user_id: Annotated[int, Path(description="사용자 ID", ge=1)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """ID로 사용자를 조회합니다."""
    user = await service.get_by_id(user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 정보 수정",
    description="특정 사용자의 정보를 수정합니다. (관리자 전용)",
    dependencies=[Depends(get_current_admin)],
    responses={
        200: {"description": "수정 성공"},
        404: {"description": "사용자를 찾을 수 없음"},
        409: {"description": "이메일 중복"},
    },
)
async def update_user(
    user_id: Annotated[int, Path(description="사용자 ID", ge=1)],
    data: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """사용자 정보를 수정합니다."""
    user = await service.update(user_id, data)
    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="사용자 삭제",
    description="사용자를 삭제합니다 (소프트 삭제). (관리자 전용)",
    dependencies=[Depends(get_current_admin)],
    responses={
        204: {"description": "삭제 성공"},
        404: {"description": "사용자를 찾을 수 없음"},
    },
)
async def delete_user(
    user_id: Annotated[int, Path(description="사용자 ID", ge=1)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    """사용자를 삭제합니다."""
    await service.delete(user_id)


@router.post(
    "/{user_id}/activate",
    response_model=UserResponse,
    summary="사용자 활성화",
    description="사용자 계정을 활성화합니다. (관리자 전용)",
    dependencies=[Depends(get_current_admin)],
    responses={
        200: {"description": "활성화 성공"},
        404: {"description": "사용자를 찾을 수 없음"},
    },
)
async def activate_user(
    user_id: Annotated[int, Path(description="사용자 ID", ge=1)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """사용자 계정을 활성화합니다."""
    user = await service.activate(user_id)
    return UserResponse.model_validate(user)
```

## 라우터 등록

```python
# app/api/routers/__init__.py
from fastapi import APIRouter

from app.api.routers.user import router as user_router
from app.api.routers.auth import router as auth_router
from app.api.routers.health import router as health_router

api_router = APIRouter(prefix="/api/v1")

# 라우터 등록
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
```

## Pydantic 스키마

```python
# app/user/schemas/user.py
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from app.user.models import UserStatus


class UserBase(BaseModel):
    """사용자 기본 스키마"""
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)


class UserCreate(UserBase):
    """사용자 생성 요청"""
    password: str = Field(min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """사용자 수정 요청"""
    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = None


class UserResponse(UserBase):
    """사용자 응답"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class PaginationParams(BaseModel):
    """페이지네이션 파라미터"""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class PaginationMeta(BaseModel):
    """페이지네이션 메타 정보"""
    page: int
    size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class UserListResponse(BaseModel):
    """사용자 목록 응답"""
    items: list[UserResponse]
    pagination: PaginationMeta

    @classmethod
    def from_query_result(
        cls,
        items: list,
        total_items: int,
        page: int,
        size: int,
    ) -> "UserListResponse":
        """쿼리 결과로부터 응답 생성"""
        total_pages = (total_items + size - 1) // size

        return cls(
            items=[UserResponse.model_validate(item) for item in items],
            pagination=PaginationMeta(
                page=page,
                size=size,
                total_items=total_items,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        )
```
