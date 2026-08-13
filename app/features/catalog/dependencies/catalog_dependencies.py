"""Catalog 기능 의존성 — 세션 선택과 객체 조립만 담당한다 (TX-001).

Dependency 는 Service 유스케이스를 실행하지 않고 커밋하지도 않는다.
teardown commit 패턴도 쓰지 않는다 — yield 이후 코드는 **응답 전송 후**에 실행되어
커밋 실패가 2xx 로 둔갑한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.catalog.services.catalog_service import CatalogService


async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    """쓰기용 — 첫 쿼리부터 primary 에 고정된다. 커밋은 View 본문이 한다."""
    return CatalogService(db_session)


async def get_catalog_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    """조회용 — 커밋하지 않으며, 쓰기를 시도하면 즉시 실패한다."""
    return CatalogService(db_session)
