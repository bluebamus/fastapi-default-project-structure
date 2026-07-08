"""
Reply v1 API 엔드포인트 — 댓글 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직과 트랜잭션 경계는 services / dependencies 가 담당한다(UnitOfWork 제거).
"""

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.domains.reply.dependencies.reply_dependencies import get_reply_service
from app.domains.reply.schemas.reply_schema import (
    ReplyCreate,
    ReplyListResponse,
    ReplyResponse,
    ReplyUpdate,
)
from app.domains.reply.services.reply_service import ReplyService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "댓글을 찾을 수 없음"}}


@router.post(
    "/replies",
    response_model=ReplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="댓글 생성",
    description="새 댓글을 생성합니다.",
    operation_id="createReply",
)
async def create_reply(
    payload: ReplyCreate,
    service: ReplyService = Depends(get_reply_service),
) -> ReplyResponse:
    reply = await service.create_reply(payload)
    return ReplyResponse.model_validate(reply)


@router.get(
    "/replies",
    response_model=ReplyListResponse,
    summary="댓글 목록 조회",
    description="댓글 목록을 페이지네이션하여 조회합니다.",
    operation_id="listReplies",
)
async def list_replies(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: ReplyService = Depends(get_reply_service),
) -> ReplyListResponse:
    replies, total = await service.list_replies(skip=skip, limit=limit)
    return ReplyListResponse(
        items=[ReplyResponse.model_validate(r) for r in replies],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/replies/{reply_id}",
    response_model=ReplyResponse,
    responses=_NOT_FOUND,
    summary="댓글 단건 조회",
    description="ID로 댓글을 조회합니다.",
    operation_id="getReply",
)
async def get_reply(
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service),
) -> ReplyResponse:
    reply = await service.get_reply(reply_id)
    return ReplyResponse.model_validate(reply)


@router.patch(
    "/replies/{reply_id}",
    response_model=ReplyResponse,
    responses=_NOT_FOUND,
    summary="댓글 수정",
    description="댓글을 부분 수정합니다(전달한 필드만).",
    operation_id="updateReply",
)
async def update_reply(
    payload: ReplyUpdate,
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service),
) -> ReplyResponse:
    reply = await service.update_reply(reply_id, payload)
    return ReplyResponse.model_validate(reply)


@router.delete(
    "/replies/{reply_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="댓글 삭제",
    description="댓글을 삭제합니다.",
    operation_id="deleteReply",
)
async def delete_reply(
    reply_id: str = Path(..., description="댓글 ID(UUID)"),
    service: ReplyService = Depends(get_reply_service),
) -> None:
    await service.delete_reply(reply_id)
