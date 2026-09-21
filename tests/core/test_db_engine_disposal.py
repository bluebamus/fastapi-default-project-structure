"""DB engine 정리의 실패 격리 (F-032 / REQ-010).

``dispose_engine()`` 은 writer·read replica·background 세 종류의 커넥션 풀을 닫는다.
하나가 실패했다고 뒤따르는 engine 을 건너뛰면 그 풀은 열린 채 프로세스가 죽고, DB 쪽에
좀비 연결이 남는다. **모든 engine 을 시도**하고 실패는 이름과 함께 기록하는 것이 계약이다.

실제 DB 에 붙지 않는다 — 어떤 engine 을 몇 개나 시도했는지가 계약이므로 가짜로 갈아끼운다.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db import session as db_session


class _FakeEngine:
    """dispose 호출을 기록하는 engine 대역."""

    def __init__(self, name: str, calls: list[str], *, fail: bool = False) -> None:
        self.name = name
        self._calls = calls
        self._fail = fail

    async def dispose(self) -> None:
        self._calls.append(self.name)
        if self._fail:
            raise RuntimeError(f"{self.name} dispose 실패(의도적)")


class _RecordingLogger:
    """session 모듈 로거 대역 — 포맷된 메시지만 모은다."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def _record(self, msg: str, *args: object, **_kwargs: object) -> None:
        self.messages.append(msg % args if args else msg)

    info = _record
    warning = _record
    error = _record
    exception = _record


@pytest.fixture
def engines(monkeypatch):
    """writer / reader 2개 / background 를 가짜로 갈아끼우고 호출 기록을 돌려준다."""
    calls: list[str] = []
    log = _RecordingLogger()

    def install(*, writer_fails: bool = False, failing_reader: int | None = None):
        writer = _FakeEngine("writer", calls, fail=writer_fails)
        readers = [_FakeEngine(f"reader{i}", calls, fail=(failing_reader == i)) for i in range(2)]
        background = _FakeEngine("background", calls)
        monkeypatch.setattr(db_session, "engine", writer)
        monkeypatch.setattr(db_session, "read_engines", readers)
        monkeypatch.setattr(db_session, "background_engine", background)
        monkeypatch.setattr(db_session, "logger", log)
        return calls, log

    return install


async def test_all_engines_are_disposed_on_the_happy_path(engines):
    """정상 경로에서 writer·모든 reader·background 가 전부 정리된다."""
    calls, _ = engines()

    await db_session.dispose_engine()

    assert sorted(calls) == [
        "background",
        "reader0",
        "reader1",
        "writer",
    ], f"정리되지 않은 engine 이 있다: {calls}"


async def test_writer_failure_still_disposes_the_rest(engines):
    """writer dispose 가 실패해도 reader 와 background 는 전부 시도된다 (F-032)."""
    calls, _ = engines(writer_fails=True)

    await db_session.dispose_engine()

    assert (
        "reader0" in calls and "reader1" in calls
    ), f"writer 실패 뒤 read replica 정리가 생략됐다: {calls}"
    assert "background" in calls, f"writer 실패 뒤 background engine 정리가 생략됐다: {calls}"


async def test_middle_reader_failure_does_not_stop_the_rest(engines):
    """중간 reader 가 실패해도 후속 reader 와 background 는 시도된다 (F-032)."""
    calls, _ = engines(failing_reader=0)

    await db_session.dispose_engine()

    assert "reader1" in calls, f"중간 reader 실패 뒤 후속 reader 가 생략됐다: {calls}"
    assert "background" in calls, f"중간 reader 실패 뒤 background 가 생략됐다: {calls}"


async def test_failed_engine_is_named_in_the_log(engines):
    """어느 engine 이 실패했는지 로그만 보고 알 수 있어야 한다.

    "정리 실패" 만 남으면 운영에서 어느 풀이 열린 채인지 알 수 없다.
    """
    _, log = engines(writer_fails=True)

    await db_session.dispose_engine()

    joined = " | ".join(log.messages)
    assert "writer" in joined, f"실패한 engine 이름이 로그에 없다: {log.messages}"


async def test_dispose_failure_does_not_propagate(engines):
    """dispose 실패가 종료 절차를 깨뜨리지 않는다.

    이 함수는 lifespan 의 종료 경로와 Celery worker 양쪽에서 불린다. 예외를 올리면
    원래의 종료 원인이 dispose 실패로 덮인다.
    """
    engines(writer_fails=True, failing_reader=1)

    await db_session.dispose_engine()  # 예외가 나오면 이 테스트가 실패한다


def test_dispose_engine_signature_is_unchanged():
    """공개 계약을 바꾸지 않는다 — 인자 없이 호출 가능해야 한다.

    ``app/celery/lifecycle.py`` 가 ``dispose_engine()`` 을 인자 없이 부른다. 필수
    인자를 추가하면 Celery worker 종료가 조용히 깨진다.
    """
    required = [
        name
        for name, param in inspect.signature(db_session.dispose_engine).parameters.items()
        if param.default is inspect.Parameter.empty
    ]
    assert required == [], f"dispose_engine 에 필수 인자가 생겼다: {required}"


# ---------------------------------------------------------------------------
# 세션 Dependency 의 예외 경로 정리
#
# `get_writer_db_session()`·`get_read_only_db_session()` 에는 명시적인
# `except Exception: await session.rollback(); raise` 가 있었다. 죽은 코드다 —
# `AsyncSession.__aexit__` 이 `asyncio.shield(create_task(self.close()))` 이고,
# `close()` 는 `if self.is_active: self._connection_rollback_impl()` 로 ROLLBACK 을
# 이미 보낸다. 게다가 `except Exception` 은 `asyncio.CancelledError`(BaseException
# 상속, 클라이언트 연결 끊김)를 **못 잡는데** `__aexit__` 의 shield 는 잡는다.
#
# `get_routed_db_session()`·`get_background_db_session()` 은 except 블록에
# 로깅 부수효과가 있으므로 그대로 둔다.
# ---------------------------------------------------------------------------

SIMPLE_DEPENDENCIES = ("get_writer_db_session", "get_read_only_db_session")
LOGGING_DEPENDENCIES = ("get_routed_db_session", "get_background_db_session")


@pytest_asyncio.fixture
async def rollbacks(monkeypatch):
    """엔진 이벤트로 ROLLBACK 횟수를 세는 in-memory 세션 팩토리로 갈아끼운다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    counted: list[str] = []
    event.listen(engine.sync_engine, "rollback", lambda connection: counted.append("rollback"))

    maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(db_session, "AsyncSessionLocal", maker)

    yield counted
    await engine.dispose()


async def _raise_inside(dependency_name: str, error: BaseException) -> None:
    """Dependency 를 열고 트랜잭션을 연 뒤 본문에서 예외가 난 상황을 재현한다."""
    generator = getattr(db_session, dependency_name)()
    session = await generator.__anext__()
    await session.execute(text("SELECT 1"))  # 트랜잭션을 연다

    with pytest.raises(type(error)):
        await generator.athrow(error)


@pytest.mark.parametrize("dependency_name", SIMPLE_DEPENDENCIES)
@pytest.mark.parametrize(
    "error", [RuntimeError("boom"), asyncio.CancelledError()], ids=["exception", "cancelled"]
)
async def test_exception_path_rolls_back_exactly_once(rollbacks, dependency_name, error):
    """명시적 rollback 을 지워도 ROLLBACK 은 정확히 1회 나간다.

    `CancelledError` 도 같다 — `except Exception` 은 못 잡지만 `__aexit__` 은 잡는다.
    """
    await _raise_inside(dependency_name, error)

    assert rollbacks == ["rollback"]


@pytest.mark.parametrize("dependency_name", SIMPLE_DEPENDENCIES)
def test_simple_dependencies_have_no_explicit_rollback(dependency_name):
    """정리는 `async with` 에 맡긴다 — 중복 rollback 코드를 되살리지 않는다.

    독스트링이 "왜 없는지" 를 설명하느라 rollback 을 언급하므로 호출 형태로 본다.
    """
    source = inspect.getsource(getattr(db_session, dependency_name))

    assert "session.rollback()" not in source


@pytest.mark.parametrize("dependency_name", LOGGING_DEPENDENCIES)
def test_logging_dependencies_keep_their_except_block(dependency_name):
    """로깅 부수효과가 있는 쪽은 except 블록이 필요하다 — 함께 지우지 않는다."""
    source = inspect.getsource(getattr(db_session, dependency_name))

    assert "except Exception" in source
    assert "ROLLBACK" in source
