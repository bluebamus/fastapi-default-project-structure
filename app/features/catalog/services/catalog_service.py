"""Catalog Service — 상품 유스케이스.

비즈니스 규칙은 여기, SQL 은 Repository, HTTP 계약은 View 가 담당한다.
트랜잭션 경계는 쓰기 View 본문이 응답 직전에 닫는다(TX-004).
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.catalog.exceptions import ProductNotFoundException
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate, ProductUpdate


class CatalogService(BaseService):
    """상품 비즈니스 로직 (DB 세션 기반)."""

    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = ProductRepository(db_session)

    async def create_product(self, payload: ProductCreate) -> Product:
        """상품을 생성한다(커밋은 View 가 수행)."""
        self.log.debug("상품 생성: name=%s", payload.name)
        return await self.repository.create(payload.model_dump())

    async def get_product(self, product_id: str) -> Product:
        """상품을 조회한다. 없으면 ProductNotFoundException."""
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundException(detail={"id": product_id})
        return product

    async def list_products(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
    ) -> tuple[Sequence[Product], int]:
        """상품 목록과 전체 개수를 조회한다.

        ``active_only`` 는 도메인 조건이므로 Repository 의 명시적 메서드로 내려간다.
        """
        if active_only:
            items = await self.repository.list_active(skip=skip, limit=limit)
            total = await self.repository.count_active()
        else:
            items = await self.repository.list(skip=skip, limit=limit)
            total = await self.repository.count()
        return items, total

    async def update_product(self, product_id: str, payload: ProductUpdate) -> Product:
        """상품을 부분 수정한다. 없으면 ProductNotFoundException."""
        existing = await self.get_product(product_id)  # 존재 보장(없으면 404)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            # 바꿀 것이 없으면 UPDATE 를 보내지 않는다 — updated_at 만 갱신되는
            # 무의미한 쓰기를 피한다.
            return existing

        updated = await self.repository.update_by_id(product_id, changes)
        # rowcount 0 은 "값이 동일해 변경 없음"(MySQL changed-rows 의미)일 수 있다.
        # 존재는 이미 보장했으므로 404 가 아니라 현재 엔티티를 돌려준다.
        return updated if updated is not None else existing

    async def delete_product(self, product_id: str) -> None:
        """상품을 삭제한다. 없으면 ProductNotFoundException."""
        deleted = await self.repository.delete_by_id(product_id)
        if not deleted:
            raise ProductNotFoundException(detail={"id": product_id})
