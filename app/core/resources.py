"""애플리케이션 프로세스 수명 자원의 생성·해제 단일 지점 (AR-005~008).

``main.py`` 의 lifespan 은 이 컨텍스트를 열고 yield 하는 **조립만** 담당한다.
자원별 startup/shutdown 코드를 main 에 나열하면 종료 순서가 암묵적이 되고,
startup 중간에 실패했을 때 이미 만든 자원이 새는 경로가 생긴다.

자원마다 작은 async context manager 를 두고 **획득 순서대로 중첩**한다. 정리는 파이썬이
그 **역순**으로 실행하므로, 순서를 따로 강제할 장치가 필요 없다 (ADR-017)::

    async with _database(...), _background_tasks():
        ...
    # 정리 순서: background drain → DB dispose

이 순서인 이유는 의존 관계다. DB 를 쓰는 주체(background task)를 먼저 멈춰야 커넥션 풀을
닫는 것이 안전하다.

**logging listener 는 여기서 멈추지 않는다** (ADR-018). 소유자는 프로세스이고
``app/utils/logs/setup.py`` 의 ``atexit`` 훅이 정리한다. lifespan 이 멈추면 그 뒤에
uvicorn 이 남기는 최종 로그와 startup 실패 traceback 이 소비자 없는 큐에 갇혀 사라진다
(F-029).

**이 중첩을 평평한 ``finally`` 안의 연속 ``await`` 로 되돌리지 말 것.**
``asyncio.CancelledError`` 는 ``Exception`` 이 아니라 ``BaseException`` 이라
``_run_cleanup()`` 의 그물을 통과한다. 연속 ``await`` 였을 때는 첫 cleanup 에서 취소를
맞으면 **뒤 단계가 통째로 건너뛰어졌다**(F-028 — DB 커넥션 풀이 닫히지 않고
``app.state.resources`` 가 닫힌 객체를 계속 가리켰다). 중첩 컨텍스트는 바깥
``__aexit__`` 가 반드시 실행되므로 그 경로 자체가 없다.
회귀 테스트: ``tests/core/test_resources.py::test_manager_cancellation_still_runs_remaining_cleanup``.

각 cleanup 은 ``_run_cleanup()`` 이 감싸서 **일반 실패·timeout 만** 로깅하고 삼킨다 —
하나가 실패했다고 뒤따르는 cleanup 을 건너뛰면 자원이 새기 때문이다. 취소는 삼키지 않는다.

테이블 자동 생성은 **파일 존재 여부가 아니라** 모델 import 후
``Base.metadata.tables`` 의 실제 개수로 판정한다. 모델이 0개면 DB 에 접속조차 하지
않는다(AR-007).

자원 소유권은 FastAPI API 프로세스가 만든 것으로 한정한다. Celery worker 의
broker/backend 연결은 worker 프로세스가 소유하며 여기서 닫지 않는다(AR-006).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.core.db.models_registry import import_all_models
from app.core.db.session import create_db_tables, dispose_engine
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.models.models_base import Base
from app.utils.logs import get_logger
from config import app_settings

logger = get_logger("resources")

# 자원별 shutdown 예산 (확정 정책 6). 합이 전체 예산을 넘지 않아야 한다.
BACKGROUND_DRAIN_TIMEOUT_SECONDS = 5.0
DB_DISPOSE_TIMEOUT_SECONDS = 10.0
SHUTDOWN_TOTAL_TIMEOUT_SECONDS = 20.0
# logging listener 의 종료 예산은 여기 없다 — 프로세스 종료 훅의 몫이다 (ADR-018).

# drain 예산 중 "완료를 기다리는" 몫. 나머지는 timeout 이후 pending 을 취소하고
# 회수(gather)하는 데 쓴다. 바깥 guard 와 같은 값을 주면 취소 회수 도중 잘려,
# 태스크의 finally(세션 rollback/close)가 실행되지 못한 채 DB dispose 로 넘어간다.
DRAIN_WAIT_RATIO = 0.8


@dataclass(slots=True)
class ApplicationResources:
    """이 프로세스가 실제로 생성한 장기 수명 자원과 startup 판정 결과.

    ``app.state.resources`` 로 참조하며, shutdown 후에는 닫힌 자원을 가리키지
    않도록 ``None`` 으로 되돌린다.
    """

    model_modules: tuple[str, ...] = ()
    table_count: int = 0
    tables_created: bool = False


async def _run_cleanup(
    name: str,
    action: Callable[[], Awaitable[None]],
    timeout: float,
) -> None:
    """cleanup 하나를 timeout 안에서 실행하고 **일반 실패만** 삼킨다.

    cleanup 실패를 밖으로 던지면 원래의 startup 실패 원인이 그것으로 덮인다. 그래서
    ``Exception`` 과 timeout 은 여기서 기록하고 끝낸다.

    **삼키는 범위는 ``Exception`` 까지다.** ``asyncio.CancelledError`` 는
    ``BaseException`` 이라 이 그물을 통과해 밖으로 나간다 — 그래야 취소가 호출자에게
    재전파된다. 취소돼도 **뒤따르는 cleanup 이 실행되는 것은 이 함수가 아니라 중첩
    context manager 구조가 보장한다**(ADR-017). 둘을 혼동해 "실패 격리는 여기서 다
    책임진다" 고 읽으면 구조를 평평하게 되돌리게 되고, 그 순간 F-028 이 재발한다.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await action()
    except TimeoutError:
        logger.error("[shutdown] %s 정리 timeout (%.1fs 초과)", name, timeout)
    except Exception:
        logger.exception("[shutdown] %s 정리 실패", name)
    else:
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("[shutdown] %s 정리 완료 (%.1fms)", name, elapsed)


async def _drain_background_tasks() -> None:
    wait_timeout = BACKGROUND_DRAIN_TIMEOUT_SECONDS * DRAIN_WAIT_RATIO
    await _run_cleanup(
        "background task",
        lambda: access_log_tasks.drain(timeout=wait_timeout),
        BACKGROUND_DRAIN_TIMEOUT_SECONDS,
    )


async def _dispose_db_engines() -> None:
    await _run_cleanup("DB engine", dispose_engine, DB_DISPOSE_TIMEOUT_SECONDS)


async def _prepare_database(resources: ApplicationResources) -> None:
    """모델을 import 하고, 실제 테이블 수를 근거로 자동 생성 여부를 판정한다."""
    modules = import_all_models()
    resources.model_modules = tuple(modules)
    resources.table_count = len(Base.metadata.tables)
    logger.info(
        "[startup] 모델 모듈 %d개 · metadata 테이블 %d개",
        len(modules),
        resources.table_count,
    )

    if resources.table_count == 0:
        logger.info("[startup] 등록된 테이블이 없어 DB 연결과 테이블 생성을 건너뛴다")
        return

    if not app_settings.DEBUG:
        logger.info("[startup] 테이블 자동 생성 건너뜀 (운영 정책 — Alembic 사용)")
        return

    # 모델은 위에서 이미 import 했다. 다시 import 하면 같은 startup 에서
    # discovery 가 두 번 도는 셈이라 로그와 소요 시간이 어긋난다.
    await create_db_tables(import_models=False)
    resources.tables_created = True
    logger.info("[startup] 테이블 자동 생성 완료 (개발 정책)")


@asynccontextmanager
async def _database(app: FastAPI) -> AsyncIterator[None]:
    """커넥션 풀을 닫는다 — background task 가 멈춘 **뒤**에."""
    try:
        yield
    finally:
        await _dispose_db_engines()

        # 닫힌 자원을 다음 lifespan/테스트가 재사용하지 않도록 참조도 지운다.
        app.state.resources = None
        # 이 줄이 실제로 출력되려면 큐를 소비할 listener 가 아직 살아 있어야 한다.
        # 그 보장은 ADR-018(프로세스 소유)이 준다 — lifespan 은 listener 를 멈추지
        # 않는다. 예전에는 여기서 멈춰 이 줄이 한 번도 안 나왔다(F-026).
        logger.info("[shutdown] 애플리케이션 요청 처리 자원 해제 완료")


@asynccontextmanager
async def _background_tasks() -> AsyncIterator[None]:
    """가장 안쪽 자원 — DB 를 쓰는 주체이므로 가장 먼저 멈춘다."""
    try:
        yield
    finally:
        # 가장 안쪽이라 이 finally 가 종료 절차의 첫 순간이다.
        logger.info("[shutdown] 애플리케이션 요청 처리 자원 해제 시작")
        await _drain_background_tasks()


@asynccontextmanager
async def manage_application_resources(
    app: FastAPI,
) -> AsyncIterator[ApplicationResources]:
    """프로세스 수명 자원을 생성하고, 정상·실패·취소 종료 모두에서 해제한다."""
    resources = ApplicationResources()
    app.state.resources = resources
    started = time.perf_counter()
    logger.info("[startup] 애플리케이션 자원 초기화 시작 (DEBUG=%s)", app_settings.DEBUG)

    # 획득 순서대로 중첩하면 정리는 자동으로 역순이다 (모듈 독스트링 참조).
    async with _database(app), _background_tasks():
        # startup 작업은 두 컨텍스트에 **모두 진입한 뒤** 실행한다. 여기서 실패하면
        # 두 finally 가 전부 돌아 이미 열려 있던 engine 이 정리된다 — engine 은 이
        # 컨텍스트가 만든 것이 아니라 import 시점에 이미 존재하므로 startup 성공
        # 여부와 무관하게 닫아야 한다.
        await _prepare_database(resources)

        elapsed = (time.perf_counter() - started) * 1000
        logger.info("[startup] 자원 초기화 완료 (%.1fms)", elapsed)
        yield resources
