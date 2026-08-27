"""로깅 설정 적용 + 로거 팩토리 + queue listener lifecycle.

``configure_logging()`` 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
``get_logger()`` 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).

root 에 붙는 유일한 핸들러는 ``BoundedQueueHandler`` 이며, 실제 stdout/stderr 쓰기는
``QueueListener`` 스레드가 맡는다(NFR-009). listener 는 여기서 시작한다 — Celery
worker·Alembic·테스트처럼 FastAPI lifespan 이 돌지 않는 프로세스에서도 로그가
나가야 하기 때문이다.

**종료(flush/stop) 소유자는 프로세스다** (ADR-018). 여기서 ``atexit`` 훅을 프로세스당
한 번 등록하고, FastAPI lifespan 은 listener 를 멈추지 않는다. lifespan 이 멈추면 그
**뒤에** uvicorn 이 남기는 최종 로그와 startup 실패 traceback 이 소비자 없는 큐에 갇혀
사라진다 — DB 가 꺼진 채 ``python main.py`` 를 실행하면 오류 원인이 한 글자도 나오지
않았다(F-029). listener 는 자신을 쓰는 모든 것보다 오래 살아야 한다.

listener 인스턴스는 ``dictConfig`` 가 queue 핸들러와 **함께** 만들어
``handler.listener`` 에 붙여 준다(ADR-021). 여기서는 시작·정지만 관리한다.

핸들러 참조를 ``logging.getHandlerByName()`` 으로 나중에 다시 찾지 않고 여기 모듈
상태에 붙잡아 둔다. ``dictConfig`` 는 호출될 때마다 기존 핸들러 이름 레지스트리를
비우므로(uvicorn 이 자기 dictConfig 를 적용한다), 나중에 조회하면 None 이 된다.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import signal
import sys
import threading
from logging.config import dictConfig
from logging.handlers import QueueListener

from app.utils.logs.config import (
    LOG_FORMAT,
    _env,
    _level,
    build_dictconfig,
)
from app.utils.logs.queue_handler import BoundedQueueHandler

_configured = False
_queue_handler: BoundedQueueHandler | None = None
_listener: QueueListener | None = None
_exit_hook_registered = False


def _write_listener_lifecycle_status(message: str) -> None:
    """listener 종료 상태를 **queue 를 거치지 않고** 최종 sink 에 적는다.

    이 메시지는 listener 를 멈추는 과정에 대한 것이라, 평소 logger 로 남기면 지금
    멈추는 중인 바로 그 listener 의 queue 로 들어간다 — 자기 죽음을 자기가 보고하려다
    아무 데도 못 남기는 구조다(F-026·F-029 가 같은 함정이었다).

    ``sys.stderr`` 가 아니라 ``sys.__stderr__`` 를 쓰는 이유는, 종료 시점에 누군가
    ``sys.stderr`` 를 이미 갈아끼웠거나 닫았을 수 있기 때문이다.
    """
    stream = sys.__stderr__
    if stream is None:  # pragma: no cover - pythonw 등 stderr 가 없는 환경
        return
    try:
        print(f"[log-lifecycle] {message}", file=stream, flush=True)
    except Exception:  # 종료 경로에서 보고 실패가 종료를 막아서는 안 된다.
        pass


# 기본 동작이 "그 자리에서 프로세스 종료" 인 신호들. 이 신호로 죽으면 ``atexit`` 훅이
# 실행되지 않는다.
#
# ``SIGINT`` 은 **일부러 빼 두었다.** 파이썬의 기본 핸들러가 ``KeyboardInterrupt`` 를
# 올리기 때문에 정상 종료 경로를 타고 ``atexit`` 이 이미 실행된다. 굳이 가로채면 코드
# 전반에서 ``KeyboardInterrupt`` 를 기대하는 곳(pytest·REPL·디버거)이 조용히 달라진다.
_DEADLY_DEFAULT_SIGNALS = ("SIGTERM", "SIGBREAK")


def _drain_logs_then_default(signum: int, frame: object) -> None:
    """로그를 마저 내보낸 뒤 **원래 종료 동작으로 돌아간다** (ADR-022 / F-038).

    정리만 하고 신호를 삼키면 안 된다 — 삼키면 ``docker stop`` 이 종료되지 않는
    컨테이너를 만나 결국 SIGKILL 로 끌려 죽는다. 기본 동작으로 되돌린 뒤 같은 신호를
    다시 올려, 종료 코드와 종료 사유를 원래대로 유지한다.
    """
    try:
        stop_log_listener()
    except Exception:
        # 실패 사유는 stop_log_listener 가 이미 최종 sink 에 적었다. 여기는 죽는 길이라
        # 재시도할 호출자가 없으므로, 정리 실패가 종료 자체를 막게 두지 않는다.
        pass
    signal.signal(signum, signal.SIG_DFL)
    signal.raise_signal(signum)


def _install_signal_drain() -> None:
    """즉시 종료형 신호에 "로그를 비우고 죽는" 핸들러를 건다 (ADR-022 / F-038).

    uvicorn 은 정상 종료를 마친 뒤 원래 핸들러를 복구하고 **잡았던 신호를 다시 올린다**
    (``capture_signals()``). 복구된 것이 ``SIG_DFL`` 이면 프로세스는 그 자리에서 끝나고
    ``atexit`` 훅은 돌지 않는다 — queue 에 남은 종료 로그가 통째로 사라진다(daemon
    스레드인 listener 도 함께 죽는다). 앱 import 시점에 미리 걸어 두면, uvicorn 이
    "원래 핸들러" 로 복구하는 대상이 곧 이 핸들러가 된다.
    """
    if threading.current_thread() is not threading.main_thread():
        # ``signal.signal`` 은 main thread 에서만 호출할 수 있다. worker thread 안에서
        # 로깅을 처음 구성하는 경우(스레드 풀·일부 테스트)는 조용히 건너뛴다.
        return
    for name in _DEADLY_DEFAULT_SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:  # 플랫폼에 없는 신호(SIGBREAK 은 Windows 전용)
            continue
        if signal.getsignal(signum) is not signal.SIG_DFL:
            # 이미 누군가 다루고 있으면 뺏지 않는다 — gunicorn·Celery 처럼 자기 종료
            # 절차를 가진 실행기가 있고, 그쪽 핸들러가 정상 종료하면 atexit 이 돈다.
            continue
        signal.signal(signum, _drain_logs_then_default)


def _register_process_exit_hook() -> None:
    """프로세스 종료 시 listener 를 멈추도록 **한 번만** 등록한다 (ADR-018 · ADR-022).

    두 경로를 함께 덮는다.

    1. ``atexit`` — 정상 종료(스크립트 종료·``sys.exit``·``KeyboardInterrupt``).
    2. 신호 핸들러 — ``SIGTERM``/``SIGBREAK`` 처럼 기본 동작이 즉시 종료라 ``atexit``
       이 실행되지 않는 경로(``docker stop``·k8s·Ctrl+Break).

    여러 번 등록되면 종료 때 stop 이 여러 번 불리고, 아예 없으면 프로세스가 listener
    스레드를 남긴 채 죽는다. SIGKILL 과 uvicorn 의 force_exit 은 어느 훅도 돌지 않는
    경로이며 비범위다.
    """
    global _exit_hook_registered
    if _exit_hook_registered:
        return
    atexit.register(stop_log_listener)
    _install_signal_drain()
    _exit_hook_registered = True


def configure_logging(force: bool = False) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent)."""
    global _configured, _queue_handler
    if _configured and not force:
        return

    try:
        stop_log_listener()
    except Exception as exc:
        # 기존 listener 를 정상적으로 멈추지 못했으면 **재구성하지 않는다.** 그대로
        # 진행하면 root 핸들러는 새 queue 를, 살아 있는 옛 listener 는 옛 queue 를
        # 보게 되어 로그가 조용히 사라진다.
        _write_listener_lifecycle_status(f"stop 실패({exc!r}) — 로깅 재구성을 중단한다")
        return

    dictConfig(build_dictconfig())

    # dictConfig 직후에만 이름 레지스트리가 우리 것이다 — 지금 붙잡는다.
    _queue_handler = next(
        (h for h in logging.getLogger().handlers if isinstance(h, BoundedQueueHandler)),
        None,
    )
    _configured = True

    _register_process_exit_hook()
    start_log_listener()


def get_queue_handler() -> BoundedQueueHandler | None:
    """root 에 붙은 queue 핸들러(없으면 None)."""
    configure_logging()
    return _queue_handler


def start_log_listener() -> QueueListener | None:
    """queue listener 를 시작한다(이미 살아 있으면 그대로 둔다).

    listener 를 여기서 만들지 않는다 — ``dictConfig`` 가 queue 핸들러와 함께 만들어
    ``handler.listener`` 에 붙여 준다(ADR-021).
    """
    global _listener
    if _listener is not None:
        return _listener
    listener: QueueListener | None = getattr(_queue_handler, "listener", None)
    if listener is None:
        return None
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
    listener: QueueListener | None = getattr(_queue_handler, "listener", None)
    if listener is not None:
        # 스레드는 fork 를 넘어오지 못했지만 객체에는 **죽은 스레드 참조**가 남아 있다.
        # 그대로 start() 하면 stdlib 이 "Listener already started" 로 거절한다.
        listener._thread = None
    return start_log_listener()


def stop_log_listener() -> None:
    """listener 를 flush 하고 멈춘다(동기·멱등). 없으면 no-op.

    프로세스 종료 훅이 부르는 경로다. 상태는 queue 가 아니라 최종 sink 로 적는다 —
    이 함수가 멈추는 대상이 바로 그 queue 의 소비자이기 때문이다.
    """
    global _listener
    listener = _listener
    if listener is None:
        return
    _write_listener_lifecycle_status("stop 시작")
    try:
        listener.stop()
    except Exception as exc:
        # 참조를 **버리지 않는다.** 버리면 스레드는 살아 있는데 회수할 손잡이가 없다
        # (F-030). 여기서 유지해야 호출자가 재시도할 수 있다.
        _write_listener_lifecycle_status(f"stop 실패({exc!r}) — 참조 유지, 재시도 가능")
        raise
    _listener = None
    _write_listener_lifecycle_status("stop 완료")


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
