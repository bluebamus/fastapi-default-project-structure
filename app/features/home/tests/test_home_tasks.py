"""home 태스크 — 기능별 tasks.py 와 provider 재사용 (service-hardening ADR-012)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.celery.task import clear_worker_loop, get_worker_loop


def test_aggregate_task_registered_through_discovery():
    """워커가 include 를 import 하면 home 태스크가 기존 이름 그대로 등록된다."""
    from app.celery.app import celery_app

    celery_app.loader.import_default_modules()

    assert "home.aggregate_access_stats" in celery_app.tasks


def test_task_builds_service_through_home_provider(monkeypatch):
    """태스크 본문은 서비스를 직접 만들지 않고 home provider 에 세션을 넘겨 조립한다."""
    from app.features.home import tasks

    session = object()
    built: list[object] = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class FakeService:
        async def get_stats(self):
            return SimpleNamespace(total_count=7)

    def fake_build(db_session):
        built.append(db_session)
        return FakeService()

    monkeypatch.setattr(tasks, "background_db_session", fake_background_session)
    monkeypatch.setattr(tasks, "build_user_access_log_service", fake_build)

    try:
        assert tasks.aggregate_access_stats.run() == {"total": 7}
    finally:
        loop = get_worker_loop()
        if loop is not None:
            loop.close()
        clear_worker_loop()

    assert built == [session]
