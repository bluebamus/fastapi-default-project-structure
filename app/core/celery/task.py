"""
Async-aware helper for Celery workers.

Celery workers run in a synchronous context. This module provides
`run_async` which bridges a coroutine into that sync context via
`asyncio.run`, creating a fresh event loop per invocation.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """동기 Celery 워커에서 async 코루틴 실행."""
    return asyncio.run(coro)
