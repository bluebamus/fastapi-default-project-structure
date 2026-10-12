"""ProductRepository 의 정렬 — 같은 created_at 의 상품도 순서가 정해진다 (service-hardening ADR-005)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.catalog.models.models import Product  # noqa: F401  (테이블 등록)
from app.features.catalog.repositories.product_repository import ProductRepository


@pytest_asyncio.fixture
async def repository():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db_session:
        yield ProductRepository(db_session)
    await engine.dispose()


async def test_list_active_breaks_created_at_ties_by_id(repository):
    """삽입 순서(m, z, a)와 다른 ``id DESC`` 로 나오고, offset 페이지가 겹치지 않는다."""
    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    for pk in ["m", "z", "a"]:
        await repository.create(
            {"id": pk, "name": pk, "price": Decimal("1.00"), "created_at": same_time}
        )

    everything = [p.id for p in await repository.list_active()]
    paged = [p.id for skip in (0, 2) for p in await repository.list_active(skip=skip, limit=2)]

    assert everything == ["z", "m", "a"]
    assert paged == everything
