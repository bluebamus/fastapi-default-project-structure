"""MySQL 전용 검증의 픽스처 — CI 의 ``mysql`` 잡에서만 돈다.

평소 ``pytest``·게이트는 이 폴더를 수집하지 않는다(pyproject ``norecursedirs``). 경로를 직접 줄 때만
돈다: ``MYSQL_TEST_URL=mysql+aiomysql://user:pw@host:3306/db pytest tests/mysql``.

접속 정보는 ``MYSQL_TEST_URL`` 하나로만 받는다. 없으면 **실패**한다 — skip 이면 CI 가 초록인 채
MySQL 검증이 0건이 된다. localhost 기본값은 두지 않는다(남의 인스턴스에 붙는 사고를 막는다).
URL 의 계정은 ``CREATE DATABASE``·``DROP DATABASE`` 권한이 필요하다 — 테스트마다 빈 DB 를 만들고 지운다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import session as session_module

ENV_NAME = "MYSQL_TEST_URL"


@pytest.fixture(scope="session", autouse=True)
def mysql_server_url() -> URL:
    """접속 정보가 없으면 연결을 시도하기 전에 실패한다."""
    raw = os.environ.get(ENV_NAME)
    if not raw:
        pytest.fail(
            f"{ENV_NAME} 가 없습니다. MySQL 테스트는 CI 전용입니다 — 로컬에서는 자기 소유의 "
            f"빈 MySQL 을 {ENV_NAME}=mysql+aiomysql://user:pw@host:port/db 로 지정하세요.",
            pytrace=False,
        )
    url = make_url(raw)
    if url.get_backend_name() != "mysql":
        pytest.fail(
            f"{ENV_NAME} 는 mysql URL 이어야 합니다: {url.get_backend_name()}", pytrace=False
        )
    return url.set(drivername="mysql+aiomysql")


@pytest_asyncio.fixture
async def mysql_url(mysql_server_url: URL) -> AsyncIterator[URL]:
    """테스트 하나만 쓰는 빈 DB 의 URL(aiomysql). 끝나면 DB 를 지운다."""
    name = f"t_{uuid.uuid4().hex[:16]}"
    admin = create_async_engine(mysql_server_url, poolclass=NullPool)
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
        yield mysql_server_url.set(database=name)
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
        await admin.dispose()


@pytest_asyncio.fixture
async def mysql_engine(mysql_url: URL) -> AsyncIterator[AsyncEngine]:
    """앱 엔진과 같은 설정(charset·hide_parameters·풀 옵션)의 엔진."""
    engine = session_module._create_read_engine(mysql_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def mysql_sessionmaker(mysql_engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(mysql_engine, expire_on_commit=False, autoflush=False)
