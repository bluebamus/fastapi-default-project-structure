"""엔드포인트 테스트의 DB 세션 override — 한 곳에서만 만든다 (service-hardening ADR-009).

운영 의존성은 읽기 세션에 ``mark_read_only``, 쓰기 세션에 ``using_writer`` 를 건다.
예전 테스트들은 두 의존성을 **표시 없는 같은 세션**으로 바꿔 끼워, GET 경로가 몰래 써도
테스트가 통과했다(검수 R-15). 여기서는 운영과 같은 표시를 붙인 세션을 yield 한다 —
read-only 세션의 flush·DML 은 ``ReadOnlyRoutingError`` 로 실패한다.

엔드포인트 테스트가 ``app.dependency_overrides[get_*_db_session]`` 를 직접 쓰지 않는다는
계약은 ``tests/test_session_overrides.py`` 가 지킨다.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db.router import mark_read_only, using_writer
from app.core.db.session import get_read_only_db_session, get_writer_db_session


def override_db_sessions(
    app: FastAPI,
    maker: async_sessionmaker[AsyncSession],
    on_session: Callable[[AsyncSession], None] | None = None,
) -> None:
    """두 세션 의존성을 ``maker`` 의 세션으로 바꾼다(표시는 운영과 같다).

    Args:
        app: override 를 걸 앱. 해제는 호출자가 ``app.dependency_overrides.clear()`` 로 한다.
        maker: 테스트 DB 의 세션 팩토리.
        on_session: 세션마다 한 번 불린다 — commit 횟수 집계처럼 세션을 감쌀 때 쓴다.
    """

    async def _read_only() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            mark_read_only(session)
            if on_session is not None:
                on_session(session)
            yield session

    async def _writer() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            using_writer(session)
            if on_session is not None:
                on_session(session)
            yield session

    app.dependency_overrides[get_read_only_db_session] = _read_only
    app.dependency_overrides[get_writer_db_session] = _writer
