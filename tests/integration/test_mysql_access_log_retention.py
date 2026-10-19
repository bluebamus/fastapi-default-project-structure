"""MySQL 8.4 에서 접속 로그 보존 삭제 — id 선택 후 ``DELETE ... WHERE id IN`` 배치 (security-ops-hardening ADR-002).

SQLite 단위 테스트와 같은 쿼리가 MySQL 에서도 경계·배치대로 동작하는지(``DATETIME(6)`` 소수 초 포함) 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.features.home.models.models import UserAccessLog
from app.features.home.services.access_log_retention_service import AccessLogRetentionService

pytestmark = pytest.mark.mysql

NOW = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)


async def test_retention_purge_on_mysql(mysql_session_maker):
    cutoff = NOW - timedelta(days=30)
    rows = {
        **{f"old-{i}": cutoff - timedelta(days=1, microseconds=i + 1) for i in range(5)},
        "older-by-1us": cutoff - timedelta(microseconds=1),
        "exactly-cutoff": cutoff,
        "newer": cutoff + timedelta(microseconds=1),
    }
    async with mysql_session_maker() as db_session:
        for name, created_at in rows.items():
            db_session.add(
                UserAccessLog(
                    ip_address="127.0.0.1",
                    request_path=f"/{name}",
                    request_method="GET",
                    created_at=created_at,
                )
            )
        await db_session.commit()

    async with mysql_session_maker() as db_session:
        service = AccessLogRetentionService(
            db_session, retention_days=30, clock=lambda: NOW, batch_size=2
        )
        assert await service.purge() == 6

    async with mysql_session_maker() as db_session:
        remaining = (await db_session.execute(select(UserAccessLog.request_path))).scalars().all()
    assert sorted(remaining) == ["/exactly-cutoff", "/newer"]
