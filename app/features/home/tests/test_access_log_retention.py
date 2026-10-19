"""접속 로그 보존 — 경계·배치·0=보존·설정 검증·beat 등록·provider 조립 (security-ops-hardening ADR-002·ADR-003)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery.task import clear_worker_loop, get_worker_loop
from app.core.db.session import Base
from app.features.home.dependencies.access_log_dependencies import (
    build_access_log_retention_service,
)
from app.features.home.models.models import UserAccessLog
from app.features.home.services.access_log_retention_service import (
    DEFAULT_BATCH_SIZE,
    AccessLogRetentionService,
)
from config import MiddlewareSettings, middleware_settings, timezone_settings

NOW = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


async def _add(session, name: str, created_at: datetime) -> None:
    session.add(
        UserAccessLog(
            ip_address="127.0.0.1",
            request_path=f"/{name}",
            request_method="GET",
            created_at=created_at,
        )
    )
    await session.commit()


async def _remaining(session) -> set[str]:
    rows = (await session.execute(select(UserAccessLog.request_path))).scalars().all()
    return {path.lstrip("/") for path in rows}


async def test_only_rows_older_than_retention_are_deleted(session):
    cutoff = NOW - timedelta(days=30)
    await _add(session, "older", cutoff - timedelta(microseconds=1))
    await _add(session, "exactly-cutoff", cutoff)
    await _add(session, "newer", cutoff + timedelta(seconds=1))

    deleted = await AccessLogRetentionService(session, retention_days=30, clock=_clock).purge()

    assert deleted == 1
    assert await _remaining(session) == {"exactly-cutoff", "newer"}


async def test_deletes_in_batches_and_commits_each_batch(session, monkeypatch):
    for index in range(5):
        await _add(session, f"old-{index}", NOW - timedelta(days=400, minutes=index))
    await _add(session, "fresh", NOW)
    service = AccessLogRetentionService(session, retention_days=365, clock=_clock, batch_size=2)
    batches: list[int] = []
    commits: list[int] = []
    real_delete = service.repository.delete_created_before
    real_commit = session.commit

    async def spy_delete(cutoff, limit):
        deleted = await real_delete(cutoff, limit)
        batches.append(deleted)
        return deleted

    async def spy_commit():
        commits.append(len(batches))
        await real_commit()

    monkeypatch.setattr(service.repository, "delete_created_before", spy_delete)
    monkeypatch.setattr(session, "commit", spy_commit)

    assert await service.purge() == 5

    assert batches == [2, 2, 1]
    assert commits == [1, 2, 3]  # 배치마다 커밋
    assert await _remaining(session) == {"fresh"}


async def test_zero_retention_deletes_nothing_without_querying(session, monkeypatch):
    await _add(session, "ancient", NOW - timedelta(days=10_000))
    service = AccessLogRetentionService(session, retention_days=0, clock=_clock)

    async def must_not_run(*_args):
        raise AssertionError("보존 0 인데 삭제 쿼리를 실행했다")

    monkeypatch.setattr(service.repository, "delete_created_before", must_not_run)

    assert await service.purge() == 0
    assert await _remaining(session) == {"ancient"}


@pytest.mark.parametrize(("days", "batch"), [(-1, 10), (1, 0)])
def test_service_rejects_bad_policy(days, batch):
    with pytest.raises(ValueError):
        AccessLogRetentionService(object(), retention_days=days, clock=_clock, batch_size=batch)


def test_setting_default_is_one_year_and_env_overrides(monkeypatch):
    monkeypatch.delenv("ACCESS_LOG_RETENTION_DAYS", raising=False)
    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 365
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "90")
    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 90
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "0")
    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 0


def test_negative_retention_setting_is_a_validation_error(monkeypatch):
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "-1")
    with pytest.raises(ValidationError):
        MiddlewareSettings(_env_file=None)


def test_provider_builds_service_from_settings():
    service = build_access_log_retention_service(object())

    assert service.retention_days == middleware_settings.ACCESS_LOG_RETENTION_DAYS
    assert service._clock == timezone_settings.utc_now
    assert service.batch_size == DEFAULT_BATCH_SIZE


def test_purge_task_is_registered_and_scheduled_daily_at_0330_local():
    from app.celery.app import celery_app

    celery_app.loader.import_default_modules()
    from app.features.home import tasks

    assert tasks.PURGE_TASK_NAME in celery_app.tasks
    entry = celery_app.conf.beat_schedule[tasks.PURGE_TASK_NAME]
    assert entry["task"] == tasks.PURGE_TASK_NAME
    assert entry["schedule"].hour == {3}
    assert entry["schedule"].minute == {30}
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE  # crontab 은 로컬 시간대


def test_purge_task_builds_service_through_home_provider(monkeypatch):
    from app.features.home import tasks

    session = object()
    built: list[object] = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class FakeService:
        async def purge(self):
            return 42

    def fake_build(db_session):
        built.append(db_session)
        return FakeService()

    monkeypatch.setattr(tasks, "background_db_session", fake_background_session)
    monkeypatch.setattr(tasks, "build_access_log_retention_service", fake_build)

    try:
        assert tasks.purge_expired_access_logs.run() == 42
    finally:
        loop = get_worker_loop()
        if loop is not None:
            loop.close()
        clear_worker_loop()

    assert built == [session]
