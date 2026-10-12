"""Home 접속 로그 서비스의 실제 DB 동작 검증 (UnitOfWork 제거 후 세션 기반).

in-memory sqlite 로 service → repository → ORM CRUD 흐름을 검증한다.
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog  # noqa: F401  (register table)
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.features.home.services.user_access_log_service import UserAccessLogService


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


_SAME_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "query",
    [
        lambda repo: repo.get_by_ip("9.9.9.9"),
        lambda repo: repo.get_by_user_id("u-1"),
        lambda repo: repo.get_by_date_range(_SAME_TIME, _SAME_TIME),
        lambda repo: repo.get_recent_logs(limit=10),
    ],
    ids=["by-ip", "by-user", "by-date-range", "recent"],
)
async def test_same_created_at_is_ordered_by_id(session, query):
    """created_at 이 같은 로그도 순서가 정해진다 — 보조 키 ``id DESC``.

    초 단위 저장에서 같은 시각은 흔하다. 보조 키가 없으면 offset 페이지가 실행마다
    겹치거나 빠진다(service-hardening ADR-005). 삽입 순서는 기대 순서와 다르게 둔다.
    """
    repository = UserAccessLogRepository(session)
    for pk in ["m", "z", "a"]:
        await repository.create(
            {
                "id": pk,
                "ip_address": "9.9.9.9",
                "user_id": "u-1",
                "request_path": "/x",
                "request_method": "GET",
                "created_at": _SAME_TIME,
            }
        )

    assert [log.id for log in await query(repository)] == ["z", "m", "a"]
