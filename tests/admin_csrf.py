"""관리 로그인 폼의 CSRF 토큰을 읽어 로그인한다 — 로그인 테스트들이 함께 쓴다 (security-ops-hardening ADR-004)."""

from __future__ import annotations

import re

import httpx

CSRF_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')


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
