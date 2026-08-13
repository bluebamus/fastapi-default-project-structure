"""로깅 설정 적용 + 로거 팩토리 + queue listener lifecycle.

``configure_logging()`` 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
``get_logger()`` 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).

root 에 붙는 유일한 핸들러는 ``BoundedQueueHandler`` 이며, 실제 stdout/stderr 쓰기는
``QueueListener`` 스레드가 맡는다(NFR-009). listener 는 여기서 시작한다 — Celery
worker·Alembic·테스트처럼 FastAPI lifespan 이 돌지 않는 프로세스에서도 로그가
나가야 하기 때문이다. **종료(flush/stop) 소유자는 자원 관리자 하나**이며
(``app/core/resources.py``) background drain 과 DB dispose 가 끝난 뒤 마지막에
호출한다.

핸들러 참조를 ``logging.getHandlerByName()`` 으로 나중에 다시 찾지 않고 여기 모듈
상태에 붙잡아 둔다. ``dictConfig`` 는 호출될 때마다 기존 핸들러 이름 레지스트리를
비우므로(uvicorn 이 자기 dictConfig 를 적용한다), 나중에 조회하면 None 이 된다.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import dictConfig
from logging.handlers import QueueListener

from app.utils.logs.config import (
    LOG_FORMAT,
    _env,
    _level,
    build_dictconfig,
    listener_handler_names,
)
from app.utils.logs.queue_handler import BoundedQueueHandler

_configured = False
_queue_handler: BoundedQueueHandler | None = None
_listener_targets: list[logging.Handler] = []
_listener: QueueListener | None = None


def configure_logging(force: bool = False) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent)."""
    global _configured, _queue_handler, _listener_targets
    if _configured and not force:
        return

    stop_log_listener()

    dictConfig(build_dictconfig())

    # dictConfig 직후에만 이름 레지스트리가 우리 것이다 — 지금 붙잡는다.
    _queue_handler = next(
        (h for h in logging.getLogger().handlers if isinstance(h, BoundedQueueHandler)),
        None,
    )
    _listener_targets = [
        handler
        for name in listener_handler_names()
        if (handler := logging.getHandlerByName(name)) is not None
    ]
    _configured = True

    start_log_listener()


def get_queue_handler() -> BoundedQueueHandler | None:
    """root 에 붙은 queue 핸들러(없으면 None)."""
    configure_logging()
    return _queue_handler


def start_log_listener() -> QueueListener | None:
    """queue listener 를 시작한다(이미 살아 있으면 그대로 둔다)."""
    global _listener
    if _listener is not None:
        return _listener
    if _queue_handler is None or not _listener_targets:
        return None

    listener = QueueListener(
        _queue_handler.queue,
        *_listener_targets,
        respect_handler_level=True,
    )
    listener.start()
    _listener = listener
    return listener


def restart_log_listener() -> QueueListener | None:
    """fork 직후처럼 listener 스레드가 사라진 프로세스에서 다시 세운다.

    스레드는 fork 를 넘어 살아남지 않는다. Celery prefork worker 의 자식
    프로세스는 큐 핸들러만 물려받고 소비자가 없어, 그대로 두면 로그가 큐에
    쌓이다 상한에서 버려진다.
    """
    global _listener
    _listener = None
    return start_log_listener()


def stop_log_listener() -> None:
    """listener 를 flush 하고 멈춘다(동기). 없으면 no-op."""
    global _listener
    listener, _listener = _listener, None
    if listener is not None:
        listener.stop()


async def stop_log_listener_async() -> None:
    """listener 종료를 event loop 밖에서 수행한다.

    ``QueueListener.stop()`` 은 sentinel 을 넣고 스레드를 join 하는 **동기** 작업이라
    그대로 await 하면 종료 중 event loop 를 막는다.
    """
    await asyncio.to_thread(stop_log_listener)


def get_logger(name: str = "app") -> logging.Logger:
    """설정된 로깅을 공유하는 로거를 반환한다.

    Args:
        name: 로거 이름(모듈명 권장). 헤더의 app 은 소스 경로에서 자동 산출된다.
    """
    configure_logging()
    return logging.getLogger(name)


def get_shared_queue_handler() -> logging.Handler:
    """uvicorn dictConfig 가 앱과 **같은** queue 를 쓰도록 핸들러를 넘겨준다."""
    handler = get_queue_handler()
    if handler is None:  # pragma: no cover - 구성 실패 시의 보수적 대비
        return logging.StreamHandler()
    return handler


def setup_uvicorn_logging() -> dict:
    """Uvicorn(log_config)용 dictConfig — 앱과 동일한 queue 출력 경로를 쓴다.

    uvicorn 로거는 소스가 site-packages 라 경로 판별이 ``ext`` 로 떨어진다.
    로거 단에서 ``StaticAppFilter`` 로 ``app=uvicorn`` 을 먼저 찍어두면 공유
    핸들러의 ``ContextFilter`` 가 이미 채워진 값을 존중한다. 필터를 핸들러가 아닌
    **로거**에 붙이는 이유는 핸들러가 앱과 공유되기 때문이다 — 핸들러에 붙이면
    앱 로그까지 uvicorn 으로 라벨링된다.
    """
    level = _level()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "uvicorn_app": {
                "()": "app.utils.logs.filters.StaticAppFilter",
                "appname": "uvicorn",
            },
        },
        "handlers": {
            "queue": {"()": "app.utils.logs.setup.get_shared_queue_handler"},
        },
        "loggers": {
            name: {
                "handlers": ["queue"],
                "filters": ["uvicorn_app"],
                "level": level,
                "propagate": False,
            }
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        },
    }


__all__ = [
    "LOG_FORMAT",
    "_env",
    "configure_logging",
    "get_logger",
    "get_queue_handler",
    "get_shared_queue_handler",
    "restart_log_listener",
    "setup_uvicorn_logging",
    "start_log_listener",
    "stop_log_listener",
    "stop_log_listener_async",
]
