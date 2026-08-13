"""쓰기 도메인의 트랜잭션 경계 회귀 테스트 (계획서 P1-2).

`get_blog_service` 는 `yield` 이후 `session.commit()` 을 호출하는 구조다. 이 경계는
FastAPI 의 yield dependency 종료 코드 실행 시점에 의존하므로, 버전을 올릴 때 조용히
바뀔 수 있다. 여기서 네 가지 성질을 고정해 업그레이드 시 회귀를 잡는다.

1. 읽기 경로는 커밋하지 않는다
2. 쓰기 성공은 정확히 1회 커밋한다
3. 예외 발생 시 커밋 없이 롤백으로 끝난다
4. 커밋 실패는 성공 응답으로 둔갑하지 않는다  <- 업그레이드 시 가장 먼저 깨질 지점

4번이 실패하면 클라이언트가 201 을 받았는데 데이터는 없는 상태가 된다. 그 경우
계획서 P1-3(쓰기 경로를 명시적 트랜잭션 컨텍스트로 전환)이 발동한다.

측정 결과 (FastAPI 0.115.x, 2026-08-10): 4번 통과 — 커밋 실패가 응답 전송보다
먼저 일어나 클라이언트는 5xx 를 받는다. 따라서 현재 핀에서 P1-3 은 불필요하다.

상향 검토 결과 (FastAPI 0.141.1, 2026-08-10): **4번 실패** — 커밋 실패에도
클라이언트가 201 을 받고 데이터는 저장되지 않는다. `yield` 이후 종료 코드가 응답
전송 후에 실행되도록 바뀌었다. 즉 **FastAPI 를 올리려면 P1-3 이 선결 조건**이다.
이 테스트가 정확히 그 판정을 위해 존재한다. 자세한 내용은
`docs/review/improvement-plan-2026-08-10.md` 의 P5 절.

1번은 최초 측정에서 실패해 xfail 로 고정했다가, P4-1(읽기 전용 의존성 분리)로
해소되어 마커를 제거했다.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.blog.models.models import Post  # noqa: F401  (register table)
from main import app

_NEW_POST = {"title": "경계 검증", "content": "본문", "author": "kim"}
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest_asyncio.fixture
async def tx_client():
    """commit/rollback 호출을 집계하는 클라이언트.

    `calls["fail_commit"] = True` 로 두면 commit 이 실패하도록 주입할 수 있다.
    실제 커밋 동작은 그대로 위임하므로 데이터 검증도 같이 가능하다.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    calls = {"commit": 0, "rollback": 0, "fail_commit": False}

    async def _override_get_session():
        async with maker() as session:
            original_commit = session.commit
            original_rollback = session.rollback

            async def _counting_commit(*args, **kwargs):
                calls["commit"] += 1
                if calls["fail_commit"]:
                    raise RuntimeError("injected commit failure")
                return await original_commit(*args, **kwargs)

            async def _counting_rollback(*args, **kwargs):
                calls["rollback"] += 1
                return await original_rollback(*args, **kwargs)

            session.commit = _counting_commit  # type: ignore[method-assign]
            session.rollback = _counting_rollback  # type: ignore[method-assign]
            yield session

    # 조회 엔드포인트는 get_read_only_db_session 을 쓴다. 같은 세션으로 오버라이드해야
    # 읽기/쓰기 커밋 횟수를 한 카운터로 셀 수 있다.
    app.dependency_overrides[get_writer_db_session] = _override_get_session
    app.dependency_overrides[get_read_only_db_session] = _override_get_session
    # raise_app_exceptions=False: 서버 예외를 그대로 던지지 않고 실제 응답으로 받아야
    # "클라이언트가 무엇을 보는가"를 검증할 수 있다.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, calls
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_read_path_does_not_commit(tx_client):
    """목록 조회는 쓰기가 없으므로 커밋할 이유가 없다 (P4-1 로 해소)."""
    client, calls = tx_client

    resp = await client.get("/api/v1/blog/posts")

    assert resp.status_code == 200
    assert calls["commit"] == 0, f"읽기 경로가 {calls['commit']}회 커밋함"


async def test_write_path_commits_exactly_once(tx_client):
    """쓰기 성공은 1회만 커밋한다. 2회 이상이면 커밋 주체가 중복된 것이다."""
    client, calls = tx_client

    resp = await client.post("/api/v1/blog/posts", json=_NEW_POST)

    assert resp.status_code == 201
    assert calls["commit"] == 1, f"쓰기 성공이 {calls['commit']}회 커밋함"


async def test_exception_path_rolls_back_without_commit(tx_client):
    """없는 리소스 수정(404)은 커밋 없이 끝나야 한다."""
    client, calls = tx_client

    resp = await client.patch(f"/api/v1/blog/posts/{_MISSING_ID}", json={"title": "수정"})

    assert resp.status_code == 404
    assert calls["commit"] == 0, "예외 경로가 커밋함 — 부분 저장 위험"


async def test_commit_failure_is_not_reported_as_success(tx_client):
    """커밋이 실패했는데 클라이언트가 2xx 를 받으면 데이터 불일치다.

    이 테스트가 빨간불이면 응답이 이미 전송된 뒤에 커밋이 실행된다는 뜻이고,
    계획서 P1-3(명시적 트랜잭션 컨텍스트 전환)을 착수해야 한다.
    """
    client, calls = tx_client
    calls["fail_commit"] = True

    resp = await client.post("/api/v1/blog/posts", json=_NEW_POST)

    assert calls["commit"] == 1, "커밋이 시도되지 않아 이 테스트가 무의미해졌다"
    assert resp.status_code >= 500, (
        f"커밋이 실패했는데 클라이언트는 {resp.status_code} 를 받았다 — "
        "성공 응답 후 커밋 구조이므로 P1-3 전환이 필요하다"
    )
