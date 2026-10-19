"""MySQL 8.4 에서 /admin 로그인 — 실제 ``python -m scripts.create_superuser`` 로 만든 계정 (admin-login).

운영자가 하는 그대로 스크립트를 **별도 프로세스**로 실행해(설정은 환경 변수로만) 임의 사용자명의 슈퍼유저를
MySQL 에 만든 뒤, 같은 DB 를 보는 ``AdminAuthBackend`` 로 로그인 흐름을 확인한다. Redis 는 fakeredis.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI

from app.features import admin as admin_module
from tests.admin_csrf import admin_login
from tests.integration.conftest import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

pytestmark = pytest.mark.mysql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "s3cret-pass-word"


def _create_superuser(username: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ENV": "test",
        "MYSQL_HOST": MYSQL_HOST,
        "MYSQL_PORT": str(MYSQL_PORT),
        "MYSQL_USER": MYSQL_USER,
        "MYSQL_PASSWORD": MYSQL_PASSWORD,
        "MYSQL_DATABASE": MYSQL_DATABASE,
        "DB_ROUTER_ENABLED": "false",
        "DB_REPLICATION_ENABLED": "false",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.create_superuser",
            "--username",
            username,
            "--email",
            f"{username}@example.com",
            "--password-stdin",
        ],
        input=PASSWORD + "\n",
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


async def test_superuser_from_script_logs_into_admin(mysql_session_maker):
    username = f"admin_{uuid.uuid4().hex[:8]}"
    result = await asyncio.to_thread(_create_superuser, username)
    assert result.returncode == 0, result.stderr[-2000:]
    assert PASSWORD not in result.stdout + result.stderr

    app = FastAPI()
    app.state.redis = FakeAsyncRedis()
    backend = admin_module.build_admin_auth_backend(app, session_factory=mysql_session_maker)
    admin_module.create_admin_interface(app, mysql_session_maker.kw["bind"], backend)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get("/admin/")).status_code == 302
            assert (await admin_login(client, username, "wrong-password")).status_code == 400
            assert (await admin_login(client, username, PASSWORD)).status_code == 302
            assert (await client.get("/admin/")).status_code == 200
            assert (await client.get("/admin/logout")).status_code == 302
            assert (await client.get("/admin/")).status_code == 302
    finally:
        await app.state.redis.aclose()
