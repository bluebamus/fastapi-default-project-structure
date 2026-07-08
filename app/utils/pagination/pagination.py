"""페이지네이션 유틸 (프레임워크 독립 순수 데이터클래스).

많은 프로젝트에서 공통으로 쓰이는 페이지네이션 결과 컨테이너를 외부 의존 없이 정의한다.
어떤 계층(도메인 스키마·서비스·응답 변환)에서도 재사용할 수 있도록 SQLAlchemy·Pydantic
등 상위/외부 계층에 의존하지 않는다(`app/utils/` 순수성 규칙).

설계:
    - 모든 필드는 초기값을 가진 클래스 변수로 정의되어, ``Pagination()`` 만으로 '빈 페이지'를
      만들 수 있다. ``items`` 는 가변 기본값이므로 dataclass 규칙에 따라 ``default_factory``
      를 사용한다(가변 기본값 공유 안티패턴 회피).
    - ``create()`` 클래스메서드는 ``total``/``page_size`` 로 파생값(total_pages/has_next/
      has_prev)을 계산한 뒤 ``return cls(...)`` 로 인스턴스를 만든다. 반환 타입은 정의된
      클래스 변수(필드)로 고정된다.

Example:
    from app.utils.pagination import Pagination

    page = Pagination.create(items=rows, total=100, page=2, page_size=20)
    # page.total_pages == 5, page.has_next is True, page.has_prev is True
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class Pagination(Generic[T]):
    """페이지네이션 결과 컨테이너.

    Attributes:
        items: 현재 페이지의 항목 목록
        total: 전체 항목 수
        page: 현재 페이지 번호(1부터 시작)
        page_size: 페이지당 항목 수
        total_pages: 전체 페이지 수
        has_next: 다음 페이지 존재 여부
        has_prev: 이전 페이지 존재 여부
    """

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int = 1,
        page_size: int = 20,
    ) -> Pagination[T]:
        """항목과 페이지 정보로 파생 필드를 계산해 인스턴스를 생성한다.

        Args:
            items: 현재 페이지의 항목 목록
            total: 전체 항목 수
            page: 현재 페이지 번호(1부터 시작)
            page_size: 페이지당 항목 수

        Returns:
            파생 필드(total_pages/has_next/has_prev)가 채워진 ``Pagination`` 인스턴스.
        """
        total_pages = math.ceil(total / page_size) if total > 0 and page_size > 0 else 1
        return cls(
            items=list(items),
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )
