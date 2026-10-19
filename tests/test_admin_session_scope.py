"""관리 세션은 /admin 전용이다 — API 인증과 섞이지 않는다 (admin-login ADR-006).

API 인증은 JWT Bearer(``get_current_principal``)뿐이고 앱 전역 세션 미들웨어는 없다. 관리 세션 쿠키
(``admin_session`` — Redis 서버 세션의 ID, admin-session-hardening ADR-001)는 SQLAdmin 하위 앱의
``RedisSessionMiddleware`` 만 읽고 쓴다. ``SESSION_COOKIE_NAME`` 은 접속 로그가
쿠키 값을 기록용으로 읽을 뿐 인증에 쓰지 않는다.
"""

from __future__ import annotations

import httpx
import pytest

import main
from app.core.security.admin_session import (
    ADMIN_SESSION_COOKIE,
    AdminCsrfMiddleware,
    AdminSessionStore,
    RedisSessionMiddleware,
)


def _admin_cookie() -> str:
    """형식상 유효한 관리 세션 ID(서버에 없는 값)."""
    return AdminSessionStore.new_session_id()


def test_main_app_has_no_session_middleware():
    names = [m.cls.__name__ for m in main.app.user_middleware]
    assert all("Session" not in name for name in names), names


def test_session_middleware_lives_only_in_the_admin_sub_app():
    sub_app_middleware = [m.cls for m in main.admin.admin.user_middleware]
    # 서명 쿠키 SessionMiddleware 는 없고, Redis 세션 → CSRF 순서다.
    assert sub_app_middleware == [RedisSessionMiddleware, AdminCsrfMiddleware]


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/home/access-logs"])
async def test_api_is_not_authenticated_by_a_valid_admin_session_cookie(path):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            path, headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={_admin_cookie()}"}
        )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("path", ["/health", "/openapi.json", "/api/v1/auth/me", "/no-such-path"])
async def test_admin_session_cookie_is_never_set_outside_admin(path):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            path, headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={_admin_cookie()}"}
        )
    assert ADMIN_SESSION_COOKIE not in response.headers.get("set-cookie", "")
