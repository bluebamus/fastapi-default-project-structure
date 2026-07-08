"""
SNS v1 API 엔드포인트 — 피드 게시물 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직과 트랜잭션 경계는 services / dependencies 가 담당한다(UnitOfWork 제거).
"""

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.domains.sns.dependencies.sns_dependencies import get_sns_service
from app.domains.sns.schemas.sns_schema import (
    SnsPostCreate,
    SnsPostListResponse,
    SnsPostResponse,
    SnsPostUpdate,
)
from app.domains.sns.services.sns_service import SnsService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "피드 게시물을 찾을 수 없음"}}


@router.post(
    "/posts",
    response_model=SnsPostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="피드 게시물 생성",
    description="새 피드 게시물을 생성합니다.",
    operation_id="createSnsPost",
)
async def create_post(
    payload: SnsPostCreate,
    service: SnsService = Depends(get_sns_service),
) -> SnsPostResponse:
    post = await service.create_post(payload)
    return SnsPostResponse.model_validate(post)


@router.get(
    "/posts",
    response_model=SnsPostListResponse,
    summary="피드 게시물 목록 조회",
    description="피드 게시물 목록을 페이지네이션하여 조회합니다.",
    operation_id="listSnsPosts",
)
async def list_posts(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: SnsService = Depends(get_sns_service),
) -> SnsPostListResponse:
    posts, total = await service.list_posts(skip=skip, limit=limit)
    return SnsPostListResponse(
        items=[SnsPostResponse.model_validate(p) for p in posts],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/posts/{post_id}",
    response_model=SnsPostResponse,
    responses=_NOT_FOUND,
    summary="피드 게시물 단건 조회",
    description="ID로 피드 게시물을 조회합니다.",
    operation_id="getSnsPost",
)
async def get_post(
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service),
) -> SnsPostResponse:
    post = await service.get_post(post_id)
    return SnsPostResponse.model_validate(post)


@router.patch(
    "/posts/{post_id}",
    response_model=SnsPostResponse,
    responses=_NOT_FOUND,
    summary="피드 게시물 수정",
    description="피드 게시물을 부분 수정합니다(전달한 필드만).",
    operation_id="updateSnsPost",
)
async def update_post(
    payload: SnsPostUpdate,
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service),
) -> SnsPostResponse:
    post = await service.update_post(post_id, payload)
    return SnsPostResponse.model_validate(post)


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="피드 게시물 삭제",
    description="피드 게시물을 삭제합니다.",
    operation_id="deleteSnsPost",
)
async def delete_post(
    post_id: str = Path(..., description="피드 게시물 ID(UUID)"),
    service: SnsService = Depends(get_sns_service),
) -> None:
    await service.delete_post(post_id)
