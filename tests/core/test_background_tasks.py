"""BackgroundTaskRunner 회귀 테스트 (검수 W1/REQ-009).

미들웨어 접속로그 저장을 fire-and-forget 로 던지되,
- 동시 실행 태스크 수에 상한을 두어(백프레셔) 고부하 시 무제한 증가를 막고,
- 앱 종료 시 in-flight 태스크를 drain 하여 마지막 로그 유실/엔진 경합을 줄인다.
"""

import asyncio

from app.core.middlewares import background_tasks as bg
from app.core.middlewares.background_tasks import BackgroundTaskRunner


async def test_backpressure_drops_tasks_over_capacity() -> None:
    runner = BackgroundTaskRunner(max_concurrent=2)
    gate = asyncio.Event()

    async def blocked() -> None:
        await gate.wait()

    accepted = [runner.spawn(blocked()) for _ in range(5)]

    assert accepted.count(True) == 2, "상한(2)까지만 수락해야 함"
    assert runner.dropped == 3, "초과분 3건은 드롭·집계되어야 함"

    gate.set()
    await runner.drain(timeout=1.0)


async def test_drain_waits_for_inflight_tasks() -> None:
    runner = BackgroundTaskRunner(max_concurrent=10)
    done: list[int] = []

    async def work(i: int) -> None:
        await asyncio.sleep(0.01)
        done.append(i)

    for i in range(5):
        assert runner.spawn(work(i)) is True

    await runner.drain(timeout=2.0)

    assert sorted(done) == [0, 1, 2, 3, 4], "drain 은 모든 in-flight 태스크 완료를 기다려야 함"


async def test_completed_tasks_are_not_retained() -> None:
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def quick() -> None:
        return None

    assert runner.spawn(quick()) is True
    await runner.drain(timeout=1.0)

    assert runner.active == 0, "완료된 태스크는 추적 집합에서 제거되어야 함(누수 방지)"


# =============================================================================
# AR-009 — drain timeout 후 남은 태스크 처리
#
# timeout 이 지났다고 태스크를 그대로 두면, 곧이어 실행되는 DB engine dispose
# 이후에도 태스크가 살아 돌아 이미 닫힌 pool 을 만진다. 취소만 하고 반환해도
# 안 된다 — 취소는 다음 await 지점에서 CancelledError 를 넣을 뿐이라, await 해서
# finally/rollback/close 가 실제로 실행될 기회를 줘야 한다.
# =============================================================================
async def test_drain_cancels_pending_tasks_after_timeout() -> None:
    """timeout 후 미완료 태스크는 취소되고 추적 집합이 비어야 한다."""
    runner = BackgroundTaskRunner(max_concurrent=5)
    started = asyncio.Event()

    async def never_ends() -> None:
        started.set()
        await asyncio.sleep(3600)

    assert runner.spawn(never_ends()) is True
    await started.wait()

    await runner.drain(timeout=0.05)

    assert runner.active == 0, "drain 후에도 태스크가 추적 집합에 남아 있다 (AR-009 위반)"
    assert runner.cancelled == 1


async def test_cancelled_task_gets_a_chance_to_clean_up() -> None:
    """취소한 태스크를 await 해야 finally 의 rollback/close 가 실행된다."""
    runner = BackgroundTaskRunner(max_concurrent=5)
    started = asyncio.Event()
    cleaned: list[str] = []

    async def with_cleanup() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            # 실제 코드에서는 session.rollback()/close() 자리다.
            cleaned.append("cleanup")

    assert runner.spawn(with_cleanup()) is True
    await started.wait()

    await runner.drain(timeout=0.05)

    assert cleaned == ["cleanup"], "취소한 태스크를 await 하지 않아 정리가 실행되지 않았다"


async def test_drain_reports_failed_task_without_raising() -> None:
    """태스크가 예외로 끝나도 drain 이 종료 절차를 깨뜨리지 않는다."""
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def boom() -> None:
        raise RuntimeError("백그라운드 실패(의도적)")

    assert runner.spawn(boom()) is True
    await runner.drain(timeout=1.0)

    assert runner.active == 0


async def test_drain_is_safe_when_called_twice() -> None:
    """재진입(lifespan 재시작)에서 두 번 호출해도 안전하다."""
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def quick() -> None:
        return None

    assert runner.spawn(quick()) is True
    await runner.drain(timeout=1.0)
    await runner.drain(timeout=1.0)

    assert runner.active == 0


# =============================================================================
# F-033 — 완료된 태스크의 예외 회수
#
# done callback 이 추적 집합에서 빼기만 하고 아무도 task.exception() 을 꺼내지 않으면,
# 실패한 태스크가 GC 될 때 asyncio 가 "Task exception was never retrieved" 를 찍는다.
# 조용한 실패는 아니지만, 우리 로그 포맷 밖에서 나오는 소음이라 원인을 따라가기 어렵다.
# =============================================================================
async def test_failed_task_exception_is_recovered_and_logged_once(monkeypatch) -> None:
    """실패한 태스크의 예외를 회수해 **정확히 한 번** 기록한다."""
    recorded: list[str] = []
    monkeypatch.setattr(
        bg.logger,
        "error",
        lambda msg, *args, **kwargs: recorded.append(msg % args if args else msg),
    )

    runner = BackgroundTaskRunner(max_concurrent=5)

    async def boom() -> None:
        raise RuntimeError("백그라운드 실패(의도적)")

    assert runner.spawn(boom()) is True
    await runner.drain(timeout=1.0)
    await asyncio.sleep(0)  # done callback 이 돌 기회를 준다

    assert len(recorded) == 1, f"실패 태스크 기록이 정확히 1건이 아니다: {recorded}"
    assert (
        "백그라운드 실패(의도적)" in recorded[0]
    ), f"기록에 원래 예외가 담기지 않았다: {recorded[0]!r}"


async def test_successful_task_is_not_logged_as_error(monkeypatch) -> None:
    """정상 완료를 오류로 기록하지 않는다 — 그러면 로그가 거짓말을 한다."""
    recorded: list[str] = []
    monkeypatch.setattr(bg.logger, "error", lambda msg, *args, **kwargs: recorded.append(msg))

    runner = BackgroundTaskRunner(max_concurrent=5)

    async def quick() -> None:
        return None

    assert runner.spawn(quick()) is True
    await runner.drain(timeout=1.0)
    await asyncio.sleep(0)

    assert recorded == [], f"정상 완료가 오류로 기록됐다: {recorded}"


async def test_cancelled_task_is_not_logged_as_error(monkeypatch) -> None:
    """종료 drain 이 스스로 취소한 태스크를 오류로 기록하지 않는다.

    취소는 우리가 시킨 것이다. 이것을 error 로 남기면 정상 종료마다 오류가 쌓인다.
    """
    recorded: list[str] = []
    monkeypatch.setattr(bg.logger, "error", lambda msg, *args, **kwargs: recorded.append(msg))

    runner = BackgroundTaskRunner(max_concurrent=5)
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.sleep(3600)

    assert runner.spawn(forever()) is True
    await started.wait()
    await runner.drain(timeout=0.05)
    await asyncio.sleep(0)

    assert recorded == [], f"취소된 태스크가 오류로 기록됐다: {recorded}"
