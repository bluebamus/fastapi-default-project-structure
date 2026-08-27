"""요청 event loop 를 막지 않는 bounded queue 로그 핸들러 (NFR-009).

표준 ``logging`` 에는 await 기반 파일/스트림 API 가 없다. 그래서 요청 스레드에서
직접 출력하면 write/flush/rotation 이 event loop 를 그대로 막는다. 일반적인 해법인
``QueueHandler``/``QueueListener`` 를 쓰되, **queue 를 무한으로 두지 않는다** —
출력이 느려지면 무한 queue 는 메모리로 장애를 옮길 뿐이다.

queue 가 가득 찼을 때의 정책 (확정 정책 9)::

    DEBUG/INFO/WARNING  ->  drop + counter (관측 신호는 rate limit)
    ERROR/CRITICAL      ->  최소 포맷 stderr fallback

producer 를 블로킹하는 선택지는 쓰지 않는다. 로그 때문에 API latency 가 무너지는
것이 로그 몇 줄을 잃는 것보다 나쁘다.

fallback 은 ``logging`` API 를 다시 호출하지 않는다. 부르면 그 로그가 또 가득 찬
queue 로 들어가 무한 재귀가 된다. ``sys.stderr.write`` 만 쓴다.
"""

from __future__ import annotations

import queue
import sys
import time
from logging import LogRecord
from logging.handlers import QueueHandler, QueueListener
from typing import IO

# worker 프로세스별 queue 상한 (확정 정책 8).
LOG_QUEUE_MAX_SIZE = 10_000

# 종료 sentinel 을 넣을 때 기다리는 시간. queue 가 잠깐 가득 차 있어도 종료가
# 실패하지 않게 하되, 영원히 매달리지도 않는다.
SENTINEL_ENQUEUE_TIMEOUT_SECONDS = 2.0

# listener 스레드가 멈추기를 기다리는 시간. 이 예산이 없으면 sentinel 이 소비되지
# 않을 때 join 이 영원히 대기하고, atexit 훅에 물려 있으면 프로세스 종료가 막힌다.
LISTENER_JOIN_TIMEOUT_SECONDS = 5.0

# 쌓인 로그가 전부 기록되기를 기다리는 시간 (ADR-023). 종료 예산의 일부다.
LOG_FLUSH_TIMEOUT_SECONDS = 2.0

# 포화 알림을 남기는 최소 간격(초). 포화 상태에서는 알림 자체가 폭주한다.
OVERFLOW_NOTICE_INTERVAL_SECONDS = 5.0

# fallback 은 포매터를 거치지 않는다 — 포매터가 또 실패하면 잃을 게 더 많다.
_FALLBACK_FORMAT = "[log-fallback] {level} {name}: {message}\n"


class BoundedQueueHandler(QueueHandler):
    """상한이 있는 queue 에 non-blocking 으로 적재하는 핸들러.

    Attributes:
        dropped: 상한 초과로 버린 저레벨 record 수.
        fallbacks: stderr 로 우회 기록한 ERROR/CRITICAL record 수.
    """

    def __init__(self, log_queue: queue.Queue, stderr: IO[str] | None = None) -> None:
        super().__init__(log_queue)
        self.dropped = 0
        self.fallbacks = 0
        # 테스트가 갈아끼울 수 있도록 주입받되, 기본은 실제 stderr 다.
        self._stderr = stderr
        self._notice_allowed_at = 0.0

    @property
    def stream(self) -> IO[str]:
        """fallback 출력 대상. ``sys.stderr`` 는 런타임에 교체될 수 있어 매번 읽는다."""
        return self._stderr if self._stderr is not None else sys.stderr

    def enqueue(self, record: LogRecord) -> None:
        """queue 에 적재한다. 가득 차면 레벨별 정책으로 처리하고 즉시 반환한다."""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self._on_overflow(record)

    def _on_overflow(self, record: LogRecord) -> None:
        from logging import ERROR

        if record.levelno >= ERROR:
            self.fallbacks += 1
            self._write_fallback(record)
            return

        self.dropped += 1
        self._write_overflow_notice()

    def _write_fallback(self, record: LogRecord) -> None:
        """ERROR/CRITICAL 을 logging 을 거치지 않고 stderr 에 남긴다."""
        try:
            message = record.getMessage()
        except Exception:  # 포매팅 실패로 오류 로그를 통째로 잃지 않는다.
            message = str(record.msg)
        self._write(
            _FALLBACK_FORMAT.format(
                level=record.levelname,
                name=record.name,
                message=message,
            )
        )

    def _write_overflow_notice(self) -> None:
        """drop 이 일어나고 있음을 알리되 알림 자체가 폭주하지 않게 억제한다."""
        now = time.monotonic()
        if now < self._notice_allowed_at:
            return
        self._notice_allowed_at = now + OVERFLOW_NOTICE_INTERVAL_SECONDS
        self._write(f"[log-fallback] log queue full — dropped {self.dropped} record(s)\n")

    def _write(self, text: str) -> None:
        """stderr 기록 실패가 요청 처리로 전파되지 않게 한다."""
        try:
            stream = self.stream
            stream.write(text)
            stream.flush()
        except Exception:
            pass


class TimeoutSentinelListener(QueueListener):
    """종료가 **정해진 시간 안에** 끝나는 QueueListener.

    표준 구현은 두 곳이 무방비다.

    1. ``enqueue_sentinel()`` 이 ``put_nowait`` 을 써서, bounded queue 가 포화면
       ``queue.Full`` 로 종료 자체가 실패한다(F-030). 표준 라이브러리가 이 메서드의
       독스트링에서 *"timeout 을 쓰고 싶으면 오버라이드하라"* 고 확장 지점을 지정하고
       있으므로 그대로 따른다.
    2. ``stop()`` 의 ``thread.join()`` 에 timeout 이 없다. sentinel 이 다른 소비자에게
       가로채이면 영원히 기다린다 — 그리고 ``atexit`` 훅은 daemon 스레드 정리보다
       **먼저** 실행되므로, 그 join 이 프로세스 종료를 그대로 막는다(F-037, 실측).

    실패는 삼키지 않고 ``TimeoutError`` 로 알린다. 호출자가 참조를 유지한 채 재시도할
    수 있어야 하기 때문이다 — 조용히 넘어가면 살아 있는 스레드를 잃는다.
    """

    def enqueue_sentinel(self) -> None:
        """종료 sentinel 을 적재한다. 자리가 빌 때까지 제한된 시간만 기다린다.

        typeshed 의 스텁은 ``QueueListener._sentinel`` 과 실제 queue 의 ``put`` 을
        노출하지 않는다(스텁의 ``_QueueLike`` 는 ``get``/``put_nowait`` 만 가진다).
        런타임 계약은 CPython 구현에 있으므로 이 두 줄만 타입 검사에서 제외한다.
        """
        sentinel = self._sentinel  # type: ignore[attr-defined]
        self.queue.put(sentinel, timeout=SENTINEL_ENQUEUE_TIMEOUT_SECONDS)  # type: ignore[attr-defined]

    def stop(self) -> None:
        """listener 를 멈춘다. 예산을 넘기면 ``TimeoutError`` 를 올린다."""
        if self._thread is None:  # 여러 번 불러도 안전하다.
            return
        self.enqueue_sentinel()
        self._thread.join(LISTENER_JOIN_TIMEOUT_SECONDS)
        if self._thread.is_alive():
            raise TimeoutError(
                f"logging listener 가 {LISTENER_JOIN_TIMEOUT_SECONDS}초 안에 멈추지 않았다"
            )
        self._thread = None


def wait_until_written(
    log_queue: queue.Queue,
    timeout: float = LOG_FLUSH_TIMEOUT_SECONDS,
) -> bool:
    """큐에 넣은 record 가 **전부 기록될 때까지** 기다린다 (ADR-023).

    listener 를 멈추지 않는다 — 소비가 끝나기를 기다리기만 한다. 종료 직전에 이걸
    한 번 해 두면, 그 뒤 프로세스가 갑자기 죽어도 잃을 것이 남지 않는다.

    표준 ``QueueListener._monitor`` 는 record 를 하나 처리할 때마다 ``task_done()``
    을 부른다. 그래서 "unfinished_tasks 가 0" 이 곧 "넣은 걸 전부 썼다" 는 뜻이다.
    ``Queue.join()`` 이 기다리는 조건과 **같은 조건**을 기다리되, ``join()`` 에는
    timeout 이 없어서 여기서 직접 조건을 본다 — listener 가 죽어 있으면 ``join()``
    은 영원히 매달린다(F-037 이 그 함정이었다).

    Args:
        log_queue: 확인할 로그 큐.
        timeout: 최대 대기 시간(초).

    Returns:
        시간 안에 전부 기록됐으면 True, 예산을 넘겼으면 False.
    """
    with log_queue.all_tasks_done:
        return bool(
            log_queue.all_tasks_done.wait_for(
                lambda: log_queue.unfinished_tasks == 0,
                timeout,
            )
        )


def build_log_queue() -> queue.Queue:
    """worker 프로세스별 bounded 로그 queue 를 만든다."""
    return queue.Queue(maxsize=LOG_QUEUE_MAX_SIZE)
