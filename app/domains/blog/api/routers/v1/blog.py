"""
Blog v1 API 엔드포인트 — 게시글 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직과 트랜잭션 경계는 services / dependencies 가 담당한다(UnitOfWork 제거).
"""

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.domains.blog.dependencies.blog_dependencies import get_blog_service
from app.domains.blog.schemas.blog_schema import (
    PostCreate,
    PostListResponse,
    PostResponse,
    PostUpdate,
)
from app.domains.blog.services.blog_service import BlogService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "게시글을 찾을 수 없음"}}


@router.post(
    "/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="게시글 생성",
    description="새 게시글을 생성합니다.",
    operation_id="createPost",
)
async def create_post(
    payload: PostCreate,
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.create_post(payload)
    return PostResponse.model_validate(post)


@router.get(
    "/posts",
    response_model=PostListResponse,
    summary="게시글 목록 조회",
    description="게시글 목록을 페이지네이션하여 조회합니다.",
    operation_id="listPosts",
)
async def list_posts(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: BlogService = Depends(get_blog_service),
) -> PostListResponse:
    posts, total = await service.list_posts(skip=skip, limit=limit)
    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in posts],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/posts/{post_id}",
    response_model=PostResponse,
    responses=_NOT_FOUND,
    summary="게시글 단건 조회",
    description="ID로 게시글을 조회합니다.",
    operation_id="getPost",
)
async def get_post(
    post_id: str = Path(..., description="게시글 ID(UUID)"),
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.get_post(post_id)
    return PostResponse.model_validate(post)


@router.patch(
    "/posts/{post_id}",
    response_model=PostResponse,
    responses=_NOT_FOUND,
    summary="게시글 수정",
    description="게시글을 부분 수정합니다(전달한 필드만).",
    operation_id="updatePost",
)
async def update_post(
    payload: PostUpdate,
    post_id: str = Path(..., description="게시글 ID(UUID)"),
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.update_post(post_id, payload)
    return PostResponse.model_validate(post)


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="게시글 삭제",
    description="게시글을 삭제합니다.",
    operation_id="deletePost",
)
async def delete_post(
    post_id: str = Path(..., description="게시글 ID(UUID)"),
    service: BlogService = Depends(get_blog_service),
) -> None:
    await service.delete_post(post_id)
