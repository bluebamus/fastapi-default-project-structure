"""
User v1 API 엔드포인트 — 사용자 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직은 services 가, 세션 선택·Service 조립은 dependencies 가 맡는다.
트랜잭션 경계는 쓰기 핸들러 본문이 닫는다 — 응답 DTO 검증 → ``await service.commit()`` → 반환
(UnitOfWork 없음, docs/guides/ARCHITECTURE.md §3.2).

인가(service-hardening ADR-018): 목록·생성·삭제는 슈퍼유저(``SuperuserRequired``), 단건 조회·수정은
본인 또는 슈퍼유저(서비스의 ``OwnershipPolicy``), ``is_active``·``is_superuser`` 변경은 슈퍼유저만.
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.core.security.access import SuperuserRequired
from app.core.security.dependencies import FORBIDDEN_RESPONSES, CurrentPrincipal
from app.features.user.dependencies.user_dependencies import (
    get_user_service,
    get_user_service_readonly,
)
from app.features.user.schemas.user_schema import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.features.user.services.user_service import UserService

router = APIRouter()

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "사용자를 찾을 수 없음"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "사용자명 중복"}
}


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **FORBIDDEN_RESPONSES},
    summary="사용자 생성",
    description=(
        "새 사용자를 생성합니다(슈퍼유저 전용). 사용자명은 고유해야 하고 비밀번호는 필수입니다 — "
        "`is_superuser` 로 슈퍼유저를 만들 수 있습니다."
    ),
    operation_id="createUser",
    dependencies=[SuperuserRequired],
)
async def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.create_user(payload)
    # 응답 DTO 를 먼저 검증하고 그다음 한 번 커밋한다 — 검증이 실패하면 아무것도 확정되지 않는다.
    response = UserResponse.model_validate(user)
    await service.commit()
    return response


@router.get(
    "/users",
    response_model=UserListResponse,
    responses=FORBIDDEN_RESPONSES,
    summary="사용자 목록 조회",
    description="사용자 목록을 페이지네이션하여 조회합니다(슈퍼유저 전용).",
    operation_id="listUsers",
    dependencies=[SuperuserRequired],
)
async def list_users(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserService = Depends(get_user_service_readonly),
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
    responses={**_NOT_FOUND, **FORBIDDEN_RESPONSES},
    summary="사용자 단건 조회",
    description="ID로 사용자를 조회합니다. 본인 또는 슈퍼유저만 조회할 수 있습니다.",
    operation_id="getUser",
)
async def get_user(
    principal: CurrentPrincipal,
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service_readonly),
) -> UserResponse:
    user = await service.get_user(user_id, principal)
    return UserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={**_NOT_FOUND, **FORBIDDEN_RESPONSES},
    summary="사용자 수정",
    description=(
        "사용자를 부분 수정합니다(전달한 필드만). 본인 또는 슈퍼유저만 수정할 수 있고, "
        "`is_active`·`is_superuser` 는 슈퍼유저만 바꿀 수 있습니다. 비활성화하면 그 사용자의 "
        "Refresh Token 이 모두 폐기됩니다."
    ),
    operation_id="updateUser",
)
async def update_user(
    payload: UserUpdate,
    principal: CurrentPrincipal,
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = await service.update_user(user_id, payload, principal)
    # 응답 DTO 를 먼저 검증하고 그다음 한 번 커밋한다 — 검증이 실패하면 아무것도 확정되지 않는다.
    response = UserResponse.model_validate(user)
    await service.commit()
    return response


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_NOT_FOUND, **FORBIDDEN_RESPONSES},
    summary="사용자 삭제",
    description="사용자를 삭제하고 그 사용자의 Refresh Token 을 모두 폐기합니다(슈퍼유저 전용).",
    operation_id="deleteUser",
    dependencies=[SuperuserRequired],
)
async def delete_user(
    user_id: str = Path(..., description="사용자 ID(UUID)"),
    service: UserService = Depends(get_user_service),
) -> None:
    await service.delete_user(user_id)
    await service.commit()
