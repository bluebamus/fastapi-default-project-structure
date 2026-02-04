"""
Pagination Module

페이지네이션 관련 Pydantic 스키마와 유틸리티 함수를 정의합니다.

사용 예시:
    from app.utils.pagination import PaginatedResponse, get_paginated

    # 라우터에서 response_model로 사용
    @router.get("/items", response_model=PaginatedResponse[ItemModel])
    async def get_items(
        page: int = 1,
        page_size: int = 20,
        session: AsyncSession = Depends(get_session),
    ):
        return await get_paginated(
            session=session,
            model=Item,
            item_schema=ItemModel,
            page=page,
            page_size=page_size,
        )
"""

import math
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")
ModelT = TypeVar("ModelT")


class PaginatedResponse(BaseModel, Generic[T]):
    """페이지네이션 응답 스키마 (재사용 가능)

    Usage:
        다른 모델에서도 페이지네이션이 필요할 때 재사용 가능:
        - PaginatedResponse[LyricListItem]
        - PaginatedResponse[SongListItem]
        - PaginatedResponse[VideoListItem]

    Example:
        from app.utils.pagination import PaginatedResponse

        @router.get("/items", response_model=PaginatedResponse[ItemModel])
        async def get_items(page: int = 1, page_size: int = 20):
            ...

    Example Response:
        {
            "items": [...],
            "total": 100,
            "page": 1,
            "page_size": 20,
            "total_pages": 5,
            "has_next": true,
            "has_prev": false
        }
    """

    items: List[T] = Field(..., description="데이터 목록")
    total: int = Field(..., description="전체 데이터 수")
    page: int = Field(..., description="현재 페이지 (1부터 시작)")
    page_size: int = Field(..., description="페이지당 데이터 수")
    total_pages: int = Field(..., description="전체 페이지 수")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")
    has_prev: bool = Field(..., description="이전 페이지 존재 여부")

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """페이지네이션 응답을 생성하는 헬퍼 메서드

        Args:
            items: 현재 페이지의 데이터 목록
            total: 전체 데이터 수
            page: 현재 페이지 번호
            page_size: 페이지당 데이터 수

        Returns:
            PaginatedResponse: 완성된 페이지네이션 응답

        Usage:
            items = [LyricListItem(...) for lyric in lyrics]
            return PaginatedResponse.create(items, total=100, page=1, page_size=20)
        """
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


async def get_paginated(
    session: AsyncSession,
    model: Type[ModelT],
    item_schema: Type[T],
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[str] = "created_at",
    order_desc: bool = True,
    transform_fn: Optional[Callable[[ModelT], T]] = None,
) -> PaginatedResponse[T]:
    """범용 페이지네이션 조회 함수

    Args:
        session: SQLAlchemy AsyncSession
        model: SQLAlchemy 모델 클래스 (예: Lyric, Song, Video)
        item_schema: Pydantic 스키마 클래스 (예: LyricListItem)
        page: 페이지 번호 (1부터 시작, 기본값: 1)
        page_size: 페이지당 데이터 수 (기본값: 20)
        max_page_size: 최대 페이지 크기 (기본값: 100)
        filters: 필터 조건 딕셔너리 (예: {"status": "completed"})
        order_by: 정렬 기준 컬럼명 (기본값: "created_at")
        order_desc: 내림차순 정렬 여부 (기본값: True)
        transform_fn: 모델을 스키마로 변환하는 함수 (None이면 자동 변환)

    Returns:
        PaginatedResponse[T]: 페이지네이션된 응답

    Usage:
        # 기본 사용
        result = await get_paginated(
            session=session,
            model=Lyric,
            item_schema=LyricListItem,
            page=1,
            page_size=20,
        )

        # 필터링 사용
        result = await get_paginated(
            session=session,
            model=Lyric,
            item_schema=LyricListItem,
            filters={"status": "completed"},
        )

        # 커스텀 변환 함수 사용
        def transform(lyric: Lyric) -> LyricListItem:
            return LyricListItem(
                id=lyric.id,
                task_id=lyric.task_id,
                status=lyric.status,
                lyric_result=lyric.lyric_result[:100] if lyric.lyric_result else None,
                created_at=lyric.created_at,
            )

        result = await get_paginated(
            session=session,
            model=Lyric,
            item_schema=LyricListItem,
            transform_fn=transform,
        )
    """
    # 페이지 크기 제한
    page_size = min(page_size, max_page_size)
    offset = (page - 1) * page_size

    # 기본 쿼리
    query = select(model)
    count_query = select(func.count(model.id))

    # 필터 적용
    if filters:
        for field, value in filters.items():
            if value is not None and hasattr(model, field):
                column = getattr(model, field)
                query = query.where(column == value)
                count_query = count_query.where(column == value)

    # 전체 개수 조회
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # 정렬 적용
    if order_by and hasattr(model, order_by):
        order_column = getattr(model, order_by)
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

    # 페이지네이션 적용
    query = query.offset(offset).limit(page_size)

    # 데이터 조회
    result = await session.execute(query)
    records = result.scalars().all()

    # 페이지네이션 정보 계산
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    # 스키마로 변환
    if transform_fn:
        items = [transform_fn(record) for record in records]
    else:
        # 자동 변환: 모델의 속성을 스키마 필드와 매칭
        items = []
        for record in records:
            item_data = {}
            for field_name in item_schema.model_fields.keys():
                if hasattr(record, field_name):
                    item_data[field_name] = getattr(record, field_name)
            items.append(item_schema(**item_data))

    return PaginatedResponse[T](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
