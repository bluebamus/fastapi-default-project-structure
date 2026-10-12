"""SNS 도메인 스키마 — 피드 게시물 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema


class SnsPostBase(BaseModel):
    """피드 게시물 공통 필드."""

    content: str = Field(..., min_length=1, max_length=500, description="게시물 본문")


class SnsPostCreate(SnsPostBase):
    """피드 게시물 생성 요청. 작성자(``author``·``author_id``)는 받지 않는다 — 서버가 인증 주체로 채운다."""


class SnsPostUpdate(PatchSchema):
    """피드 게시물 수정 요청 — 전달된 필드만 부분 수정한다.

    작성자는 수정할 수 없다(소유권이 바뀌지 않는다). 명시적 ``null`` 은 422.
    """

    content: str | None = Field(None, min_length=1, max_length=500, description="본문")


class SnsPostResponse(SnsPostBase):
    """피드 게시물 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="게시물 ID(UUID)")
    author: str | None = Field(
        None, max_length=100, description="작성자 이름 — 서버가 작성 시점의 사용자명으로 채운다"
    )
    author_id: str | None = Field(
        None,
        description="작성자 사용자 ID — 소유권 판정 기준. 인가 도입 전 행은 null(슈퍼유저만 수정)",
    )
    like_count: int = Field(..., description="좋아요 수 — 응답 전용(작성·수정으로 변경 불가)")
    created_at: datetime = Field(..., description="생성 시각(UTC)")
    updated_at: datetime = Field(..., description="마지막 수정 시각(UTC)")


class SnsPostListResponse(BaseModel):
    """피드 게시물 목록 응답(페이지네이션)."""

    items: list[SnsPostResponse] = Field(..., description="현재 페이지의 게시물 목록")
    total: int = Field(..., description="조건에 해당하는 전체 게시물 수")
    skip: int = Field(..., description="건너뛴 개수(요청한 `skip`)")
    limit: int = Field(..., description="페이지 크기(요청한 `limit`)")
