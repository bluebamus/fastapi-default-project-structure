"""DB engine 정리의 실패 격리 (F-032 / REQ-010).

``dispose_engine()`` 은 writer·read replica·background 세 종류의 커넥션 풀을 닫는다.
하나가 실패했다고 뒤따르는 engine 을 건너뛰면 그 풀은 열린 채 프로세스가 죽고, DB 쪽에
좀비 연결이 남는다. **모든 engine 을 시도**하고 실패는 이름과 함께 기록하는 것이 계약이다.

실제 DB 에 붙지 않는다 — 어떤 engine 을 몇 개나 시도했는지가 계약이므로 가짜로 갈아끼운다.
"""

from __future__ import annotations

import inspect

import pytest

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
