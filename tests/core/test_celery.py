"""Celery — 앱 설정·태스크 탐색(``models_registry.iter_task_modules``)·async 브리지·worker 종료.

태스크는 기능별 ``tasks.py`` 에 있고 워커의 include 는 기능 패키지 탐색이 만든다 — 기능을 지우면 그
태스크도 include 에서 빠진다.

``run_async`` 는 worker 프로세스마다 영속 event loop 하나를 재사용한다. async DB 커넥션(aiomysql)은
만든 루프에 묶이고 풀이 커넥션을 재사용하므로, 호출마다 ``asyncio.run()`` 으로 루프를 새로 열고 닫으면
두 번째 태스크부터 'Event loop is closed' 로 실패한다. aiosqlite 는 루프에 묶이지 않아 그 증상을
재현하지 못하므로, 여기서는 근본 성질(연속 호출이 살아 있는 같은 루프에서 돈다)을 검증한다.
"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys

import pytest

import app.features
from app.celery.task import run_async
from app.core.db import models_registry


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")
    assert list(celery_app.conf.include) == models_registry.iter_task_modules()
    assert "app.features.home.tasks" in celery_app.conf.include


def test_discovery_lists_home_tasks():
    assert "app.features.home.tasks" in models_registry.iter_task_modules()


@pytest.fixture
def fake_features(tmp_path, monkeypatch):
    """``app.features`` 의 탐색 경로를 임시 디렉터리로 바꾼다 — 실제 기능 패키지는 건드리지 않는다."""
    monkeypatch.setattr(app.features, "__path__", [str(tmp_path)])
    prefix = "app.features.zz_fake_"
    yield tmp_path
    for name in [m for m in sys.modules if m.startswith(prefix)]:
        del sys.modules[name]


def _make_feature(root: pathlib.Path, name: str, *, with_tasks: bool) -> None:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if with_tasks:
        # 탐색이 태스크 모듈을 import 하면 이 줄이 터진다 — 실제 태스크 모듈은 celery_app 을
        # import 하므로, Celery 앱 생성 중에 import 하면 순환 import 가 된다.
        (pkg / "tasks.py").write_text(
            "raise RuntimeError('imported at discovery')\n", encoding="utf-8"
        )
    importlib.invalidate_caches()


def test_discovery_skips_features_without_tasks_and_does_not_import_them(fake_features):
    _make_feature(fake_features, "zz_fake_with", with_tasks=True)
    _make_feature(fake_features, "zz_fake_without", with_tasks=False)

    assert models_registry.iter_task_modules() == ["app.features.zz_fake_with.tasks"]
    assert "app.features.zz_fake_with.tasks" not in sys.modules


def test_removing_a_feature_removes_its_tasks_from_include(fake_features):
    """기능 디렉터리를 지우면 include 에서도 빠진다 — 손볼 중앙 목록이 없다."""
    _make_feature(fake_features, "zz_fake_a", with_tasks=True)
    _make_feature(fake_features, "zz_fake_b", with_tasks=True)
    assert models_registry.iter_task_modules() == [
        "app.features.zz_fake_a.tasks",
        "app.features.zz_fake_b.tasks",
    ]

    for path in sorted((fake_features / "zz_fake_a").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (fake_features / "zz_fake_a").rmdir()
    sys.modules.pop("app.features.zz_fake_a", None)
    importlib.invalidate_caches()

    assert models_registry.iter_task_modules() == ["app.features.zz_fake_b.tasks"]


def test_every_include_module_imports_and_registers_its_tasks():
    """include 의 모든 ``tasks.py`` 를 워커처럼 실제로 import 하고, 각 모듈이 태스크를 등록하는지 본다.

    탐색(``find_spec``)은 존재만 확인하고 import 하지 않는다. 그래서 ``tasks.py`` 의 import
    오류·오타는 워커 기동 때에야 드러난다 — 여기서 같은 import 를 해 CI 에서 먼저 터지게 한다.
    """
    from app.celery.app import celery_app

    include = list(celery_app.conf.include)
    assert include, "include 가 비면 이 검사가 헛통과한다"
    for module in include:
        importlib.import_module(module)
    registered = {
        task.__module__ for name, task in celery_app.tasks.items() if not name.startswith("celery.")
    }
    assert (
        set(include) <= registered
    ), f"태스크를 등록하지 않은 include 모듈: {set(include) - registered}"


def test_celery_uses_utc_internally():
    """Celery 내부 시각은 UTC 다 — DB 저장 시각과 같은 기준."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE


# --- async 브리지 · worker 종료 ------------------------------------------------
def test_run_async_reuses_a_single_live_loop() -> None:
    """연속 호출이 '동일한, 닫히지 않은' 루프에서 실행되어야 한다.

    루프 바인딩 자원(aiomysql 커넥션 등)이 태스크 간 재사용돼도 살아남으려면
    이 성질이 필수다. 매 호출 asyncio.run() 이면 루프가 매번 새로 생성·종료되어
    이 단언이 깨진다(= C1 재발).
    """
    seen: dict[str, asyncio.AbstractEventLoop] = {}

    async def capture(key: str) -> None:
        seen[key] = asyncio.get_running_loop()

    run_async(capture("first"))
    run_async(capture("second"))

    assert seen["first"] is seen["second"], "연속 태스크가 서로 다른 루프에서 실행됨"
    assert not seen["first"].is_closed(), "재사용 루프가 호출 사이에 닫힘"


def test_run_async_returns_coroutine_result() -> None:
    """브릿지가 코루틴의 반환값을 그대로 전달한다(기존 계약 유지)."""

    async def compute() -> int:
        await asyncio.sleep(0)
        return 21 * 2

    assert run_async(compute()) == 42


# =============================================================================
# worker 프로세스 종료 시 async 자원 해제
#
# FastAPI lifespan 은 Celery worker 프로세스에서 실행되지 않는다. worker 가 만든
# 영속 루프와 그 루프에 바인딩된 DB pool 을 아무도 닫지 않으면, 종료 시 커넥션이
# 서버 쪽에 남고 "Event loop is closed" 경고가 쏟아진다.
# =============================================================================
def test_worker_shutdown_disposes_db_before_closing_loop(monkeypatch) -> None:
    """DB dispose 는 루프가 **살아 있는 동안** 실행돼야 한다.

    루프를 먼저 닫으면 dispose 가 실행될 자리가 사라진다 — async pool 정리는
    코루틴이라 루프가 필요하다.
    """
    from app.celery import lifecycle

    order: list[str] = []
    observed: dict[str, bool] = {}

    async def fake_dispose() -> None:
        order.append("dispose")
        observed["loop_alive"] = not asyncio.get_running_loop().is_closed()

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    run_async(asyncio.sleep(0))  # 워커 루프 생성
    lifecycle.shutdown_worker_resources()

    assert order == ["dispose"]
    assert observed["loop_alive"] is True
    assert lifecycle.get_worker_loop() is None, "종료 후 전역 루프 참조가 남아 있다"


def test_worker_shutdown_closes_loop_and_is_idempotent(monkeypatch) -> None:
    """루프를 닫고 참조를 비운다. 두 번 불러도 터지지 않는다."""
    from app.celery import lifecycle

    async def fake_dispose() -> None:
        return None

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    run_async(asyncio.sleep(0))
    loop = lifecycle.get_worker_loop()
    assert loop is not None and not loop.is_closed()

    lifecycle.shutdown_worker_resources()
    assert loop.is_closed(), "worker 루프가 닫히지 않았다"

    lifecycle.shutdown_worker_resources()  # 재호출 안전


def test_worker_shutdown_without_loop_is_noop(monkeypatch) -> None:
    """태스크를 한 번도 실행하지 않은 worker 에서도 안전해야 한다."""
    from app.celery import lifecycle

    called: list[str] = []

    async def fake_dispose() -> None:
        called.append("dispose")

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    lifecycle.shutdown_worker_resources()  # 남아 있으면 먼저 정리
    called.clear()
    lifecycle.shutdown_worker_resources()  # 이제 루프가 없다

    assert called == [], "루프가 없는데 DB dispose 를 시도했다"


def test_dispose_failure_still_closes_loop(monkeypatch) -> None:
    """dispose 가 실패해도 루프는 닫아야 한다 — 안 닫으면 프로세스가 안 죽는다."""
    from app.celery import lifecycle

    async def boom() -> None:
        raise RuntimeError("dispose 실패(의도적)")

    monkeypatch.setattr(lifecycle, "dispose_engine", boom)

    run_async(asyncio.sleep(0))
    loop = lifecycle.get_worker_loop()
    assert loop is not None

    lifecycle.shutdown_worker_resources()

    assert loop.is_closed()
    assert lifecycle.get_worker_loop() is None
