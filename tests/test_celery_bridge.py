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
