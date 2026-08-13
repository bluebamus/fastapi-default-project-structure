"""Celery worker 프로세스의 자원 수명 관리 (AR-010).

FastAPI 의 lifespan 은 **worker 프로세스에서 실행되지 않는다.** worker 는 첫 async
태스크에서 영속 event loop 를 만들고 그 루프에 DB 커넥션 pool 을 바인딩하는데,
종료 시 아무도 닫지 않으면 커넥션이 서버 쪽에 남고 "Event loop is closed" 경고가
쏟아진다.

종료 순서가 중요하다::

    1. DB engine/pool dispose   — 루프가 **살아 있는 동안** 해야 한다(코루틴이다)
    2. loop.shutdown_asyncgens()
    3. loop.close()
    4. 전역 루프 참조 제거

FastAPI Resource Manager 와는 **소유권이 다른 프로세스**다. 공통 cleanup
primitive(``dispose_engine``)만 재사용하고, FastAPI lifespan 이 Celery 자원을
닫거나 그 반대를 하지 않는다(AR-006).
"""

from __future__ import annotations

import asyncio

from celery.signals import worker_process_init, worker_process_shutdown

from app.celery.task import clear_worker_loop, get_worker_loop
from app.core.db.session import dispose_engine
from app.utils.logs import get_logger, restart_log_listener

logger = get_logger("celery.lifecycle")

# worker cleanup 전용 예산 (확정 정책 7). FastAPI 의 20초와 별개다.
CELERY_CLEANUP_TIMEOUT_SECONDS = 10.0


def shutdown_worker_resources(
    timeout: float = CELERY_CLEANUP_TIMEOUT_SECONDS,
) -> None:
    """worker 가 소유한 async 자원을 해제하고 루프를 닫는다."""
    loop = get_worker_loop()
    if loop is None or loop.is_closed():
        clear_worker_loop()
        return

    try:
        loop.run_until_complete(asyncio.wait_for(dispose_engine(), timeout))
    except TimeoutError:
        logger.error("[celery] DB dispose timeout (%.1fs 초과)", timeout)
    except Exception:
        logger.exception("[celery] DB dispose 실패")

    # dispose 가 실패해도 루프는 반드시 닫는다 — 안 닫으면 프로세스가 종료되지 않는다.
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    except Exception:
        logger.exception("[celery] async generator 종료 실패")
    finally:
        loop.close()
        clear_worker_loop()
        logger.info("[celery] worker 자원 해제 완료")


@worker_process_init.connect
def _on_worker_process_init(**_kwargs: object) -> None:
    """fork 직후 로그 listener 를 다시 세운다.

    스레드는 fork 를 넘어 살아남지 않는다. 자식 프로세스는 queue 핸들러만 물려받고
    소비자가 없어, 그대로 두면 로그가 큐에 쌓이다 상한에서 버려진다.
    """
    restart_log_listener()


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**_kwargs: object) -> None:
    shutdown_worker_resources()
