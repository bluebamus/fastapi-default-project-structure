"""Lifespan 자원 관리자(app/core/resources.py) 계약 검증 — AR-005~008, TEST-005.

이 테스트들은 **실제 DB 에 붙지 않는다**. 자원 관리자가 "무엇을, 어떤 순서로, 어떤
조건에서" 호출하는지가 계약이므로 협력자를 가짜로 갈아끼우고 호출 기록만 본다.
실제 연결이 필요한 검증은 통합 테스트의 몫이다.

가장 중요한 계약은 AR-007 이다: **모델이 하나도 없으면 DB 에 접속조차 하지 않는다.**
파일 존재 여부가 아니라 ``Base.metadata.tables`` 의 실제 개수로 판정해야 한다.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from sqlalchemy import Column, Integer, MetaData, Table

from app.core import resources


class _FakeBase:
    """비어 있거나 채워진 metadata 를 갖는 Base 대역."""

    def __init__(self, table_count: int) -> None:
        self.metadata = MetaData()
        for index in range(table_count):
            Table(f"t{index}", self.metadata, Column("id", Integer, primary_key=True))


class _FakeRunner:
    """BackgroundTaskRunner 대역 — drain 호출을 기록한다."""

    def __init__(self, calls: list[str], *, fail: bool = False) -> None:
        self._calls = calls
        self._fail = fail
        self.drain_timeout: float | None = None

    async def drain(self, timeout: float | None = None) -> None:
        self._calls.append("drain")
        self.drain_timeout = timeout
        if self._fail:
            raise RuntimeError("drain 실패(의도적)")


@pytest.fixture
def wiring(monkeypatch):
    """자원 관리자의 협력자를 전부 가짜로 갈아끼우고 호출 기록을 돌려준다."""

    calls: list[str] = []
    state: dict = {"create_kwargs": None, "imported": 0}

    async def fake_dispose() -> None:
        calls.append("dispose")

    async def fake_create(**kwargs) -> None:
        calls.append("create_tables")
        state["create_kwargs"] = kwargs

    def fake_import() -> list[str]:
        state["imported"] += 1
        return ["app.features.demo.models.models"]

    async def fake_stop_listener() -> None:
        calls.append("listener_stop")

    def fake_start_listener() -> str:
        calls.append("listener_start")
        return "listener"

    monkeypatch.setattr(resources, "dispose_engine", fake_dispose)
    monkeypatch.setattr(resources, "create_db_tables", fake_create)
    monkeypatch.setattr(resources, "import_all_models", fake_import)
    monkeypatch.setattr(resources, "access_log_tasks", _FakeRunner(calls))
    # 실제 listener 를 멈추면 이후 테스트의 로그 소비자가 사라진다.
    monkeypatch.setattr(resources, "stop_log_listener_async", fake_stop_listener)
    monkeypatch.setattr(resources, "start_log_listener", fake_start_listener)
    return calls, state


def _use_tables(monkeypatch, count: int) -> None:
    monkeypatch.setattr(resources, "Base", _FakeBase(count))


def _set_debug(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(resources.app_settings, "DEBUG", value, raising=False)


# =============================================================================
# AR-007 — 모델 유무에 따른 테이블 생성 분기
# =============================================================================
async def test_no_models_skips_db_entirely(monkeypatch, wiring):
    """metadata table 이 0개면 create_all 도, DB 연결도 시도하지 않는다."""
    calls, _ = wiring
    _use_tables(monkeypatch, 0)
    _set_debug(monkeypatch, True)

    app = FastAPI()
    async with resources.manage_application_resources(app) as res:
        assert res.table_count == 0
        assert res.tables_created is False

    assert "create_tables" not in calls, "모델이 없는데 테이블 생성을 시도했다 (AR-007 위반)"


async def test_models_with_debug_creates_tables_once(monkeypatch, wiring):
    """테이블이 1개 이상이고 개발 자동 생성 정책이 켜져 있으면 1회 생성한다."""
    calls, state = wiring
    _use_tables(monkeypatch, 3)
    _set_debug(monkeypatch, True)

    app = FastAPI()
    async with resources.manage_application_resources(app) as res:
        assert res.table_count == 3
        assert res.tables_created is True

    assert calls.count("create_tables") == 1


async def test_models_without_debug_never_creates_tables(monkeypatch, wiring):
    """운영 정책(DEBUG=False)에서는 모델이 있어도 create_all 을 실행하지 않는다."""
    calls, _ = wiring
    _use_tables(monkeypatch, 3)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app) as res:
        assert res.tables_created is False

    assert "create_tables" not in calls, "운영에서 create_all 을 실행했다 (AR-007 위반)"


async def test_model_discovery_runs_once_per_startup(monkeypatch, wiring):
    """같은 startup 에서 모델 discovery/import 를 두 번 수행하지 않는다 (AR-007)."""
    _, state = wiring
    _use_tables(monkeypatch, 2)
    _set_debug(monkeypatch, True)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    assert state["imported"] == 1, "모델 import 가 중복 실행됐다"
    assert state["create_kwargs"] == {
        "import_models": False
    }, "create_db_tables 가 모델을 다시 import 하지 않도록 호출해야 한다"


# =============================================================================
# AR-008 — 종료 순서와 실패 안전 cleanup
# =============================================================================
async def test_shutdown_order_is_drain_dispose_then_listener(monkeypatch, wiring):
    """종료 순서는 background drain → DB dispose → logging listener stop 이다.

    listener 를 마지막에 멈춰야 앞 두 단계가 남기는 종료 로그가 출력된다.
    """
    calls, _ = wiring
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    assert calls == [
        "listener_start",
        "drain",
        "dispose",
        "listener_stop",
    ], f"종료 순서가 어긋났다: {calls}"


async def test_cleanup_failure_does_not_skip_remaining(monkeypatch, wiring):
    """하나의 cleanup 실패가 뒤따르는 cleanup 을 건너뛰게 하면 안 된다."""
    calls, _ = wiring
    monkeypatch.setattr(resources, "access_log_tasks", _FakeRunner(calls, fail=True))
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    assert calls[-3:] == [
        "drain",
        "dispose",
        "listener_stop",
    ], "drain 실패 후 뒤따르는 cleanup 이 생략됐다 (AR-008 위반)"


async def test_startup_failure_still_runs_cleanup(monkeypatch, wiring):
    """startup 중간 실패에서도 이미 등록된 자원이 해제된다."""
    calls, _ = wiring

    async def boom(**kwargs) -> None:
        calls.append("create_tables")
        raise RuntimeError("테이블 생성 실패(의도적)")

    monkeypatch.setattr(resources, "create_db_tables", boom)
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, True)

    app = FastAPI()
    with pytest.raises(RuntimeError, match="테이블 생성 실패"):
        async with resources.manage_application_resources(app):
            pytest.fail("startup 이 실패했는데 본문이 실행됐다")

    assert "drain" in calls and "dispose" in calls, "startup 실패 시 cleanup 이 실행되지 않았다"
    assert app.state.resources is None


async def test_state_resources_cleared_after_shutdown(monkeypatch, wiring):
    """cleanup 후 app.state.resources 가 닫힌 자원을 참조하지 않는다 (AR-005)."""
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app) as res:
        assert app.state.resources is res

    assert app.state.resources is None


async def test_lifespan_reentry_leaves_no_leak(monkeypatch, wiring):
    """lifespan 을 재진입해도 자원 참조가 누수되지 않는다 (TEST-005)."""
    calls, _ = wiring
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    for _ in range(2):
        async with resources.manage_application_resources(app):
            pass
        assert app.state.resources is None

    assert calls == ["listener_start", "drain", "dispose", "listener_stop"] * 2


async def test_slow_cleanup_is_bounded_by_timeout(monkeypatch, wiring):
    """cleanup 이 멈춰도 timeout 으로 끊고 다음 cleanup 으로 넘어간다."""
    calls, _ = wiring

    class _HangingRunner:
        async def drain(self, timeout: float | None = None) -> None:
            calls.append("drain")
            await asyncio.sleep(3600)

    monkeypatch.setattr(resources, "access_log_tasks", _HangingRunner())
    monkeypatch.setattr(resources, "BACKGROUND_DRAIN_TIMEOUT_SECONDS", 0.05)
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    assert calls[-3:] == [
        "drain",
        "dispose",
        "listener_stop",
    ], "timeout 후 다음 cleanup 이 실행되지 않았다"


async def test_drain_gets_headroom_to_finish_cancellation(monkeypatch, wiring):
    """drain 에 준 시간은 바깥 예산보다 짧아야 한다 (F-001).

    같은 값을 주면 drain 이 timeout 에 도달해 pending 을 취소하고 회수(gather)하려는
    순간 바깥 timeout 이 끊는다. 그러면 취소된 태스크의 finally — 세션 rollback/close
    — 가 실행되지 못한 채 곧바로 DB dispose 로 넘어간다(AR-009 보장 붕괴).
    """
    calls, _ = wiring
    seen: dict[str, float | None] = {}

    class _RecordingRunner:
        async def drain(self, timeout: float | None = None) -> None:
            calls.append("drain")
            seen["timeout"] = timeout

    monkeypatch.setattr(resources, "access_log_tasks", _RecordingRunner())
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    drain_timeout = seen["timeout"]
    assert drain_timeout is not None
    assert (
        drain_timeout < resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS
    ), "drain 에 바깥 예산과 같은 값을 주면 취소 회수 도중 잘린다"


async def test_cancelled_task_cleanup_survives_the_outer_timeout(monkeypatch, wiring):
    """실제 러너로, 예산 안에서 취소된 태스크의 finally 가 끝까지 실행되는지 본다."""
    from app.core.middlewares.background_tasks import BackgroundTaskRunner

    calls, _ = wiring
    cleaned: list[str] = []
    started = asyncio.Event()

    runner = BackgroundTaskRunner(max_concurrent=5)

    async def with_cleanup() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            await asyncio.sleep(0)  # 취소 후에도 await 지점이 남아 있는 경우
            cleaned.append("cleanup")

    assert runner.spawn(with_cleanup()) is True
    await started.wait()

    monkeypatch.setattr(resources, "access_log_tasks", runner)
    monkeypatch.setattr(resources, "BACKGROUND_DRAIN_TIMEOUT_SECONDS", 0.2)
    _use_tables(monkeypatch, 1)
    _set_debug(monkeypatch, False)

    app = FastAPI()
    async with resources.manage_application_resources(app):
        pass

    assert cleaned == ["cleanup"], "취소된 태스크의 정리가 바깥 timeout 에 잘렸다"
    assert runner.active == 0


def test_shutdown_timeout_budget_fits_total():
    """자원별 timeout 합이 전체 shutdown 예산을 넘지 않는다 (확정 정책 6)."""
    per_resource = (
        resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS
        + resources.DB_DISPOSE_TIMEOUT_SECONDS
        + resources.LOGGING_DRAIN_TIMEOUT_SECONDS
    )
    assert resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS == 5.0
    assert resources.DB_DISPOSE_TIMEOUT_SECONDS == 10.0
    assert resources.LOGGING_DRAIN_TIMEOUT_SECONDS == 5.0
    assert resources.SHUTDOWN_TOTAL_TIMEOUT_SECONDS == 20.0
    assert per_resource <= resources.SHUTDOWN_TOTAL_TIMEOUT_SECONDS
