"""
User v1 API 엔드포인트 — 사용자 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직과 트랜잭션 경계는 services / dependencies 가 담당한다(UnitOfWork 제거).
"""

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.domains.user.dependencies.user_dependencies import get_user_service
from app.domains.user.schemas.user_schema import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.domains.user.services.user_service import UserService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "사용자를 찾을 수 없음"}}
_CONFLICT = {409: {"model": ErrorResponse, "description": "사용자명 중복"}}


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
    summary="사용자 생성",
    description="새 사용자를 생성합니다. 사용자명은 고유해야 합니다.",
    operation_id="createUser",
)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.create_user(payload)
    return UserResponse.model_validate(user)


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="사용자 목록 조회",
    description="사용자 목록을 페이지네이션하여 조회합니다.",
    operation_id="listUsers",
)
async def list_users(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserService = Depends(get_user_service),
) -> UserListResponse:
    users, total = await service.list_users(skip=skip, limit=limit)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses=_NOT_FOUND,
    summary="사용자 단건 조회",
    description="ID로 사용자를 조회합니다.",
    operation_id="getUser",
)
async def get_user(
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.get_user(user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    responses=_NOT_FOUND,
    summary="사용자 수정",
    description="사용자를 부분 수정합니다(전달한 필드만).",
    operation_id="updateUser",
)
async def update_user(
    payload: UserUpdate,
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.update_user(user_id, payload)
    return UserResponse.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="사용자 삭제",
    description="사용자를 삭제합니다.",
    operation_id="deleteUser",
)
async def delete_user(
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service),
) -> None:
    await service.delete_user(user_id)
