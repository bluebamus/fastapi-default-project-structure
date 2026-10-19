"""관리 화면 테스트가 함께 쓰는 CSRF·세션 도우미 (security-ops-hardening ADR-004, admin-session-hardening).

- 로그인 화면의 hidden 토큰을 읽어 로그인한다.
- 로그인 이후 화면의 ``<meta name="csrf-token">`` 토큰을 읽는다.
- 로그아웃은 토큰을 실은 POST 다.
- 쿠키의 세션 ID 로 Redis 의 관리 세션 내용을 읽는다.
"""

from __future__ import annotations

import json
import re

import httpx

from app.core.security.admin_session import ADMIN_SESSION_COOKIE
from app.core.security.dependencies import new_admin_session_store

CSRF_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')
CSRF_META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')


async def admin_csrf_token(client: httpx.AsyncClient) -> str:
    """``GET /admin/login`` 이 그린 hidden 필드의 토큰(세션에 없으면 이때 만들어진다)."""
    html = (await client.get("/admin/login")).text
    match = CSRF_INPUT.search(html)
    assert match, "로그인 화면에 CSRF hidden 필드가 없다"
    return match.group(1)


async def admin_login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    """로그인 화면에서 토큰을 받아 함께 POST 한다(브라우저와 같은 순서)."""
    token = await admin_csrf_token(client)
    data = {"username": username, "password": password, "csrf_token": token}
    return await client.post("/admin/login", data=data)


async def admin_page_token(client: httpx.AsyncClient, path: str = "/admin/") -> str:
    """로그인 이후 화면의 meta 토큰."""
    response = await client.get(path)
    match = CSRF_META.search(response.text)
    assert match, f"{path} 에 csrf-token meta 가 없다 (status={response.status_code})"
    return match.group(1)


async def admin_logout(client: httpx.AsyncClient) -> httpx.Response:
    """화면의 토큰을 실어 POST 로 로그아웃한다(브라우저 스크립트가 하는 일)."""
    token = await admin_page_token(client)
    return await client.post("/admin/logout", data={"csrf_token": token})


def admin_session_id(client: httpx.AsyncClient) -> str | None:
    return client.cookies.get(ADMIN_SESSION_COOKIE)


async def admin_session_data(client: httpx.AsyncClient, redis) -> dict:
    """클라이언트 쿠키의 세션 ID 로 Redis 의 세션 내용을 읽는다(없으면 빈 dict)."""
    sid = admin_session_id(client)
    if not sid:
        return {}
    raw = await redis.get(new_admin_session_store(redis).key(sid))
    return json.loads(raw)["data"] if raw is not None else {}
