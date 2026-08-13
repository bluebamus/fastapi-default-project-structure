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
from logging.handlers import QueueHandler
from typing import IO

# worker 프로세스별 queue 상한 (확정 정책 8).
LOG_QUEUE_MAX_SIZE = 10_000

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


def build_log_queue() -> queue.Queue:
    """worker 프로세스별 bounded 로그 queue 를 만든다."""
    return queue.Queue(maxsize=LOG_QUEUE_MAX_SIZE)


def build_queue_handler() -> BoundedQueueHandler:
    """dictConfig 의 ``()`` 팩토리 — 새 bounded queue 를 가진 핸들러를 만든다."""
    return BoundedQueueHandler(build_log_queue())
