"""Reply 도메인 스키마 — 댓글 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReplyBase(BaseModel):
    """댓글 공통 필드."""

    content: str = Field(..., min_length=1, description="댓글 본문")
    author: str | None = Field(None, max_length=100, description="작성자(선택)")
    post_id: str | None = Field(None, max_length=36, description="대상 게시글 ID(선택)")


class ReplyCreate(ReplyBase):
    """댓글 생성 요청."""


class ReplyUpdate(BaseModel):
    """댓글 수정 요청 — 전달된 필드만 부분 수정한다."""

    content: str | None = Field(None, min_length=1, description="댓글 본문")
    author: str | None = Field(None, max_length=100, description="작성자")


class ReplyResponse(ReplyBase):
    """댓글 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="댓글 ID(UUID)")
    created_at: datetime = Field(..., description="생성 시각(UTC)")
    updated_at: datetime = Field(..., description="마지막 수정 시각(UTC)")


class ReplyListResponse(BaseModel):
    """댓글 목록 응답(페이지네이션)."""

    items: list[ReplyResponse] = Field(..., description="현재 페이지의 댓글 목록")
    total: int = Field(..., description="조건에 해당하는 전체 댓글 수")
    skip: int = Field(..., description="건너뛴 개수(요청한 `skip`)")
    limit: int = Field(..., description="페이지 크기(요청한 `limit`)")
