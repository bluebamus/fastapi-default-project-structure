"""관리 세션은 /admin 전용이다 — API 인증과 섞이지 않는다 (admin-login ADR-006).

API 인증은 JWT Bearer(``get_current_principal``)뿐이고 앱 전역 ``SessionMiddleware`` 는 없다. 서명 세션
쿠키(``admin_session``)는 SQLAdmin 하위 앱의 미들웨어만 읽고 쓴다. ``SESSION_COOKIE_NAME`` 은 접속 로그가
쿠키 값을 기록용으로 읽을 뿐 인증에 쓰지 않는다.
"""

from __future__ import annotations

import json
from base64 import b64encode

import httpx
import itsdangerous
import pytest
from starlette.middleware.sessions import SessionMiddleware

import main
from app.features.auth.admin_backend import ADMIN_SESSION_COOKIE
from config import session_settings


def _signed_admin_cookie(user_id: str = "any-user-id") -> str:
    signer = itsdangerous.TimestampSigner(session_settings.SESSION_SECRET_KEY)
    return signer.sign(b64encode(json.dumps({"user_id": user_id}).encode())).decode()


def test_main_app_has_no_session_middleware():
    assert all(m.cls is not SessionMiddleware for m in main.app.user_middleware)


def test_session_middleware_lives_only_in_the_admin_sub_app():
    sub_app_middleware = [m.cls for m in main.admin.admin.user_middleware]
    assert SessionMiddleware in sub_app_middleware
    [session_mw] = [m for m in main.admin.admin.user_middleware if m.cls is SessionMiddleware]
    assert session_mw.kwargs["session_cookie"] == ADMIN_SESSION_COOKIE
    assert session_mw.kwargs["path"] == "/admin"


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/home/access-logs"])
async def test_api_is_not_authenticated_by_a_valid_admin_session_cookie(path):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            path, headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={_signed_admin_cookie()}"}
        )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("path", ["/health", "/openapi.json", "/api/v1/auth/me", "/no-such-path"])
async def test_admin_session_cookie_is_never_set_outside_admin(path):
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            path, headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={_signed_admin_cookie()}"}
        )
    assert ADMIN_SESSION_COOKIE not in response.headers.get("set-cookie", "")
