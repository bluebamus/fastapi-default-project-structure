"""
Async-aware helper for Celery workers.

Celery workers run in a synchronous context. This module bridges a coroutine
into that sync context by reusing a single, long-lived event loop **per worker
process**.

이전 구현은 매 호출 ``asyncio.run()`` 으로 이벤트 루프를 새로 열고 닫았다.
그러나 async DB 커넥션(aiomysql)은 자신을 생성한 루프에 바인딩되고,
``background_engine`` 의 커넥션 풀은 그 커넥션을 태스크 간 캐시·재사용한다.
루프가 매번 닫히면 두 번째 태스크가 '종료된 루프에 묶인' 커넥션을 재사용하며
``RuntimeError: Event loop is closed`` 로 확정 실패한다(검수 C1/REQ-008).

Celery 기본 prefork 워커는 태스크를 프로세스 안에서 순차 실행하므로,
프로세스당 단일 영속 루프를 유지하면 재사용 커넥션이 살아있는 루프를 참조해
안전하다. (엔진/풀 설계·미들웨어 sink 경로는 변경하지 않는다.)
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

# 워커 프로세스당 하나만 생성해 재사용하는 영속 이벤트 루프.
_worker_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """동기 Celery 워커에서 async 코루틴 실행(영속 루프 재사용)."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)
