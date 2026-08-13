"""Product Repository — 상품 데이터 접근 (ORM).

Base 의 최소 CRUD 로 표현되지 않는 조회만 **명시적 메서드**로 추가한다.
문자열 컬럼명을 받는 범용 필터를 Base 에 두지 않는 이유는 오타가 실행 시점에만
드러나기 때문이다(ORM-REP-005).
"""

from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repositories.repository_base import BaseRepository
from app.features.catalog.models.models import Product


class ProductRepository(BaseRepository[Product, str]):
    """상품 Repository."""

    model = Product

    async def list_active(self, *, skip: int = 0, limit: int = 100) -> Sequence[Product]:
        """판매 중인 상품만 최신순으로 조회한다.

        Base 의 ``list()`` 는 필터를 모른다 — 이런 도메인 조건은 기능 Repository 가
        SQLAlchemy 속성으로 직접 표현한다(문자열 컬럼명이 아니라).
        """
        statement = (
            select(Product)
            .where(Product.is_active.is_(True))
            .order_by(Product.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db_session.execute(statement)
        return result.scalars().all()

    async def count_active(self) -> int:
        """판매 중인 상품 수."""
        statement = select(func.count()).select_from(Product).where(Product.is_active.is_(True))
        result = await self.db_session.execute(statement)
        return result.scalar_one()
