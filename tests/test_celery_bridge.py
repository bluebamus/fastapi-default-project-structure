"""Celery async 브릿지(run_async) 회귀 테스트.

C1(검수 REQ-008): `run_async` 가 매 호출 `asyncio.run()` 으로 새 이벤트 루프를
열고 닫으면, 커넥션 풀에 캐시된 async DB 커넥션(aiomysql)이 종료된 루프에
바인딩되어 두 번째 태스크부터 'Event loop is closed' 로 실패한다.
워커 프로세스당 단일 영속 루프를 재사용하면, 재사용되는 커넥션이 '살아있는
동일 루프'를 참조하므로 반복 태스크가 정상 동작한다.

주의: aiomysql 은 커넥션을 생성 루프에 엄격히 바인딩하지만 aiosqlite 는 그렇지
않아, 인메모리 sqlite 로는 C1 증상을 충실히 재현하지 못한다(버그 코드에서도
통과). 따라서 여기서는 C1 을 유발/방지하는 *근본 성질* —"연속 run_async 호출이
살아있는 동일 루프에서 실행된다"—를 결정적으로 검증한다. 실제 MySQL 을 띄운
Celery 통합 재현은 단위테스트 범위 밖(운영 환경 스모크 테스트로 위임).
"""

import asyncio

from app.celery.task import run_async


def test_run_async_reuses_a_single_live_loop() -> None:
    """연속 호출이 '동일한, 닫히지 않은' 루프에서 실행되어야 한다.

    루프 바인딩 자원(aiomysql 커넥션 등)이 태스크 간 재사용돼도 살아남으려면
    이 성질이 필수다. 매 호출 asyncio.run() 이면 루프가 매번 새로 생성·종료되어
    이 단언이 깨진다(= C1 재발).
    """
    seen: dict[str, asyncio.AbstractEventLoop] = {}

    async def capture(key: str) -> None:
        seen[key] = asyncio.get_running_loop()

    run_async(capture("first"))
    run_async(capture("second"))

    assert seen["first"] is seen["second"], "연속 태스크가 서로 다른 루프에서 실행됨"
    assert not seen["first"].is_closed(), "재사용 루프가 호출 사이에 닫힘"


def test_run_async_returns_coroutine_result() -> None:
    """브릿지가 코루틴의 반환값을 그대로 전달한다(기존 계약 유지)."""

    async def compute() -> int:
        await asyncio.sleep(0)
        return 21 * 2

    assert run_async(compute()) == 42


# =============================================================================
# AR-010 — worker 프로세스 종료 시 async 자원 해제
#
# FastAPI lifespan 은 Celery worker 프로세스에서 실행되지 않는다. worker 가 만든
# 영속 루프와 그 루프에 바인딩된 DB pool 을 아무도 닫지 않으면, 종료 시 커넥션이
# 서버 쪽에 남고 "Event loop is closed" 경고가 쏟아진다.
# =============================================================================
def test_worker_shutdown_disposes_db_before_closing_loop(monkeypatch) -> None:
    """DB dispose 는 루프가 **살아 있는 동안** 실행돼야 한다.

    루프를 먼저 닫으면 dispose 가 실행될 자리가 사라진다 — async pool 정리는
    코루틴이라 루프가 필요하다.
    """
    from app.celery import lifecycle

    order: list[str] = []
    observed: dict[str, bool] = {}

    async def fake_dispose() -> None:
        order.append("dispose")
        observed["loop_alive"] = not asyncio.get_running_loop().is_closed()

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    run_async(asyncio.sleep(0))  # 워커 루프 생성
    lifecycle.shutdown_worker_resources()

    assert order == ["dispose"]
    assert observed["loop_alive"] is True
    assert lifecycle.get_worker_loop() is None, "종료 후 전역 루프 참조가 남아 있다"


def test_worker_shutdown_closes_loop_and_is_idempotent(monkeypatch) -> None:
    """루프를 닫고 참조를 비운다. 두 번 불러도 터지지 않는다."""
    from app.celery import lifecycle

    async def fake_dispose() -> None:
        return None

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    run_async(asyncio.sleep(0))
    loop = lifecycle.get_worker_loop()
    assert loop is not None and not loop.is_closed()

    lifecycle.shutdown_worker_resources()
    assert loop.is_closed(), "worker 루프가 닫히지 않았다"

    lifecycle.shutdown_worker_resources()  # 재호출 안전


def test_worker_shutdown_without_loop_is_noop(monkeypatch) -> None:
    """태스크를 한 번도 실행하지 않은 worker 에서도 안전해야 한다."""
    from app.celery import lifecycle

    called: list[str] = []

    async def fake_dispose() -> None:
        called.append("dispose")

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    lifecycle.shutdown_worker_resources()  # 남아 있으면 먼저 정리
    called.clear()
    lifecycle.shutdown_worker_resources()  # 이제 루프가 없다

    assert called == [], "루프가 없는데 DB dispose 를 시도했다"


def test_dispose_failure_still_closes_loop(monkeypatch) -> None:
    """dispose 가 실패해도 루프는 닫아야 한다 — 안 닫으면 프로세스가 안 죽는다."""
    from app.celery import lifecycle

    async def boom() -> None:
        raise RuntimeError("dispose 실패(의도적)")

    monkeypatch.setattr(lifecycle, "dispose_engine", boom)

    run_async(asyncio.sleep(0))
    loop = lifecycle.get_worker_loop()
    assert loop is not None

    lifecycle.shutdown_worker_resources()

    assert loop.is_closed()
    assert lifecycle.get_worker_loop() is None
