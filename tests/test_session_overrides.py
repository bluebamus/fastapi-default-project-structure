"""공용 세션 override 헬퍼의 계약 (service-hardening ADR-009, ledger F-014).

1. read-only override 로 받은 세션에서 쓰면 운영과 같이 ``ReadOnlyRoutingError`` 로 실패한다.
   예전 override 는 표시 없는 세션이라 GET 경로의 실수 쓰기가 테스트를 통과했다(검수 R-15).
2. writer override 의 세션은 쓸 수 있다.
3. 엔드포인트 테스트는 두 세션 의존성의 override 를 손으로 만들지 않는다 — 헬퍼 하나만 쓴다.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import ReadOnlyRoutingError, is_read_only
from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.catalog.models.models import Product
from tests.session_overrides import override_db_sessions

ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(__file__).with_name("session_overrides.py")
SESSION_DEPENDENCIES = {get_read_only_db_session.__name__, get_writer_db_session.__name__}

probe = FastAPI()


async def _write(db_session: AsyncSession) -> dict[str, bool]:
    db_session.add(Product(name="probe", price=Decimal("1.00")))
    await db_session.flush()
    return {"read_only": is_read_only(db_session)}


@probe.get("/sneaky-write")
async def sneaky_write(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> dict[str, bool]:
    return await _write(db_session)


@probe.post("/write")
async def write(db_session: AsyncSession = Depends(get_writer_db_session)) -> dict[str, bool]:
    return await _write(db_session)


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    seen: list[AsyncSession] = []
    override_db_sessions(probe, async_sessionmaker(engine, expire_on_commit=False), seen.append)
    transport = ASGITransport(app=probe)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, seen
    probe.dependency_overrides.clear()
    await engine.dispose()


async def test_get_route_writing_through_read_only_override_is_rejected(client):
    http_client, _ = client
    with pytest.raises(ReadOnlyRoutingError):
        await http_client.get("/sneaky-write")


async def test_writer_override_session_can_write(client):
    http_client, seen = client
    resp = await http_client.post("/write")
    assert resp.status_code == 200
    assert resp.json() == {"read_only": False}
    assert len(seen) == 1  # on_session 이 세션마다 불린다


def _hand_rolled_overrides(path: Path) -> list[int]:
    """``x.dependency_overrides[get_*_db_session] = ...`` 의 줄 번호."""
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "dependency_overrides"
            and isinstance(node.slice, ast.Name)
            and node.slice.id in SESSION_DEPENDENCIES
        ):
            lines.append(node.lineno)
    return lines


def test_tests_do_not_hand_roll_session_overrides():
    offenders = {
        str(path.relative_to(ROOT)): found
        for top in ("app", "tests")
        for path in (ROOT / top).rglob("*.py")
        if path != HELPER and (found := _hand_rolled_overrides(path))
    }
    assert offenders == {}, (
        f"세션 의존성 override 를 직접 만든 파일: {offenders}. "
        "tests.session_overrides.override_db_sessions 를 쓰세요(read-only 표시가 빠진다)."
    )


def test_contract_detects_a_hand_rolled_override(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "app.dependency_overrides[get_read_only_db_session] = lambda: None\n", encoding="utf-8"
    )
    assert _hand_rolled_overrides(sample) == [1]
