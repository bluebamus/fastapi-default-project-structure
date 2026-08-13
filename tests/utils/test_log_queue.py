"""bounded queue logging 계약 검증 — NFR-009, TEST-006.

핵심은 **요청 event loop 를 절대 막지 않는다**는 것이다. 로그 적재는
``put_nowait()`` 뿐이고, queue 가 가득 차면 blocking 대신 레벨별 정책을 쓴다.

    DEBUG/INFO/WARNING  -> drop + counter (관측 신호는 rate limit)
    ERROR/CRITICAL      -> logging API 를 다시 호출하지 않는 최소 stderr fallback

fallback 이 ``logger.xxx()`` 를 부르면 그 로그가 또 가득 찬 queue 로 들어가
무한 재귀가 된다. 그래서 fallback 은 ``sys.stderr.write`` 만 쓴다.
"""

from __future__ import annotations

import io
import logging
import queue

import pytest

from app.utils.logs.queue_handler import BoundedQueueHandler


def _record(level: int, message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=level,
        pathname="/x/app/core/thing.py",
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


@pytest.fixture
def full_handler(monkeypatch):
    """즉시 포화되는 queue(maxsize=1)를 가진 핸들러와 stderr 버퍼."""
    buffer = io.StringIO()
    handler = BoundedQueueHandler(queue.Queue(maxsize=1), stderr=buffer)
    handler.enqueue(_record(logging.INFO, "채움"))  # maxsize 1 소진
    return handler, buffer


def test_enqueue_never_blocks_when_full(full_handler):
    """포화 상태에서도 emit 이 즉시 반환한다(blocking put 금지)."""
    handler, _ = full_handler
    handler.enqueue(_record(logging.INFO))  # 블로킹이면 여기서 테스트가 멈춘다
    assert handler.dropped == 1


def test_low_level_records_are_dropped_and_counted(full_handler):
    """DEBUG/INFO/WARNING 은 버리고 counter 만 올린다."""
    handler, buffer = full_handler
    for level in (logging.DEBUG, logging.INFO, logging.WARNING):
        handler.enqueue(_record(level))

    assert handler.dropped == 3
    # 첫 1회만 관측 신호를 남기고 나머지는 rate limit 으로 억제한다.
    assert buffer.getvalue().count("log queue full") == 1


def test_error_records_fall_back_to_stderr(full_handler):
    """ERROR/CRITICAL 은 버리지 않고 최소 포맷으로 stderr 에 남긴다."""
    handler, buffer = full_handler
    handler.enqueue(_record(logging.ERROR, "터졌다"))

    text = buffer.getvalue()
    assert "ERROR" in text
    assert "터졌다" in text
    assert handler.fallbacks == 1
    # ERROR 는 drop 이 아니다.
    assert handler.dropped == 0


def test_fallback_does_not_reenter_logging(full_handler, monkeypatch):
    """fallback 이 logging API 를 다시 호출하면 무한 재귀가 된다."""
    handler, _ = full_handler

    def explode(*args, **kwargs):  # pragma: no cover - 호출되면 실패
        raise AssertionError("fallback 이 logging API 를 재호출했다")

    monkeypatch.setattr(logging.Logger, "handle", explode)
    monkeypatch.setattr(logging.Logger, "callHandlers", explode)

    handler.enqueue(_record(logging.CRITICAL, "치명적"))
    assert handler.fallbacks == 1


def test_rate_limited_notice_resets_after_interval(full_handler, monkeypatch):
    """관측 신호는 억제하되 영영 숨기지는 않는다 — 간격이 지나면 다시 남긴다."""
    handler, buffer = full_handler
    handler.enqueue(_record(logging.INFO))
    assert buffer.getvalue().count("log queue full") == 1

    # 다음 알림 허용 시각을 과거로 돌린다.
    handler._notice_allowed_at = 0.0
    handler.enqueue(_record(logging.INFO))
    assert buffer.getvalue().count("log queue full") == 2


def test_healthy_queue_records_nothing_to_stderr():
    """여유가 있으면 stderr 로 새지 않고 queue 에만 들어간다."""
    buffer = io.StringIO()
    q: queue.Queue = queue.Queue(maxsize=10)
    handler = BoundedQueueHandler(q, stderr=buffer)

    handler.enqueue(_record(logging.ERROR, "정상 경로"))

    assert buffer.getvalue() == ""
    assert handler.dropped == 0
    assert handler.fallbacks == 0
    assert q.qsize() == 1


def test_context_fields_are_attached_before_enqueue():
    """appname/classname 은 **적재 전** 요청 스레드에서 채워져야 한다.

    ContextFilter 는 호출 스택을 훑어 classname 을 얻는다. listener 스레드에서
    돌리면 스택이 이미 사라져 항상 '-' 가 된다. 그래서 필터는 queue 핸들러에
    붙어야 하며, 이 테스트가 그 배선을 지킨다.
    """
    from app.utils.logs.filters import ContextFilter

    q: queue.Queue = queue.Queue(maxsize=10)
    handler = BoundedQueueHandler(q)
    handler.addFilter(ContextFilter())

    class _Caller:
        def emit(self) -> None:
            handler.handle(_record(logging.INFO))

    _Caller().emit()

    enqueued = q.get_nowait()
    assert enqueued.appname == "core"
    assert enqueued.classname == "_Caller"
