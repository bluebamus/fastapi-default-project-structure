"""Home 접속 로그 서비스의 실제 DB 동작 검증 (UnitOfWork 제거 후 세션 기반).

in-memory sqlite 로 service → repository → ORM CRUD 흐름을 검증한다.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.domains.home.models.models import UserAccessLog  # noqa: F401  (register table)
from app.domains.home.services.user_access_log_service import UserAccessLogService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_list(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {"ip_address": "1.2.3.4", "request_path": "/x", "request_method": "GET"}
    )
    await session.commit()

    logs, total = await service.get_access_logs()
    assert total == 1
    assert logs[0].ip_address == "1.2.3.4"
    assert logs[0].id  # repository auto-assigns UUID


@pytest.mark.asyncio
async def test_stats_counts_device_type(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {
            "ip_address": "1.1.1.1",
            "request_path": "/a",
            "request_method": "GET",
            "device_type": "desktop",
        }
    )
    await session.commit()

    stats = await service.get_stats()
    assert stats.total_count == 1
    assert any(d.device_type == "desktop" and d.count == 1 for d in stats.device_types)
