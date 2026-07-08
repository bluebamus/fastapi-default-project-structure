"""SNS 도메인 스키마 — 피드 게시물 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SnsPostBase(BaseModel):
    """피드 게시물 공통 필드."""

    content: str = Field(..., min_length=1, max_length=500, description="게시물 본문")
    author: str | None = Field(None, max_length=100, description="작성자(선택)")


class SnsPostCreate(SnsPostBase):
    """피드 게시물 생성 요청."""


class SnsPostUpdate(BaseModel):
    """피드 게시물 수정 요청 — 전달된 필드만 부분 수정한다."""

    content: str | None = Field(None, min_length=1, max_length=500, description="본문")
    author: str | None = Field(None, max_length=100, description="작성자")


class SnsPostResponse(SnsPostBase):
    """피드 게시물 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    like_count: int
    created_at: datetime
    updated_at: datetime


class SnsPostListResponse(BaseModel):
    """피드 게시물 목록 응답(페이지네이션)."""

    items: list[SnsPostResponse]
    total: int
    skip: int
    limit: int
