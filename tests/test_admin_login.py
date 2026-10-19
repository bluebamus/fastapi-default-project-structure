"""/admin 로그인 — ``AdminAuthBackend``·Bootstrap 로그인 화면·create_superuser 흐름 (admin-login).

실물 부품으로 조립한다: SQLite 파일 DB(``NullPool`` — create_superuser 가 자기 이벤트 루프를 돌린다),
fakeredis(레이트 리밋), 실제 ``build_admin_auth_backend``·``create_admin_interface``. 앱은 테스트마다
새 ``FastAPI()`` 이고 ``app.state.redis`` 에 fakeredis 를 둔다(lifespan 이 하는 일과 같다).
"""

from __future__ import annotations

import asyncio
import io
import json
import re
from base64 import b64decode, b64encode

import bcrypt
import httpx
import itsdangerous
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import config
from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features import admin as admin_module
from app.features.auth import admin_backend
from app.features.auth.admin_backend import ADMIN_SESSION_COOKIE, AdminAuthBackend
from app.features.user.models.models import User
from config import jwt_settings, session_settings
from scripts.create_superuser import EXIT_OK
from scripts.create_superuser import main as create_superuser_main
from tests.admin_csrf import CSRF_INPUT, admin_csrf_token, admin_login

import_all_models()

PASSWORD = "s3cret-pass-word"
BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
BOOTSTRAP_SRI = "sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"


# =============================================================================
# fixtures
# =============================================================================
@pytest_asyncio.fixture
async def maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def admin_app(maker, redis):
    app = FastAPI()
    app.state.redis = redis
    backend = admin_module.build_admin_auth_backend(app, session_factory=maker)
    admin_module.create_admin_interface(app, maker.kw["bind"], backend)
    return app, backend


@pytest_asyncio.fixture
async def client(admin_app):
    app, _ = admin_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def _add_user(
    maker,
    username: str,
    *,
    superuser: bool = True,
    active: bool = True,
    hashed: str | None = None,
) -> str:
    hashed = hashed or await get_password_hasher().hash(PASSWORD)
    async with maker() as session:
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hashed,
            is_superuser=superuser,
            is_active=active,
        )
        session.add(user)
        await session.commit()
        return user.id


async def _set_flags(maker, user_id: str, **flags) -> None:
    async with maker() as session:
        user = await session.get(User, user_id)
        for name, value in flags.items():
            setattr(user, name, value)
        await session.commit()


async def _login(client, username: str, password: str = PASSWORD) -> httpx.Response:
    return await admin_login(client, username, password)


def _session_data(client) -> dict:
    """클라이언트 쿠키 jar 의 admin_session 을 풀어 본다(서명 검증 포함)."""
    raw = client.cookies.get(ADMIN_SESSION_COOKIE)
    if raw is None:
        return {}
    signer = itsdangerous.TimestampSigner(session_settings.SESSION_SECRET_KEY)
    return json.loads(b64decode(signer.unsign(raw.encode())))


# =============================================================================
# 백엔드 — login / authenticate / logout
# =============================================================================
async def test_active_superuser_logs_in_and_reaches_index(client, maker):
    user_id = await _add_user(maker, "root")

    response = await _login(client, "root")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/")
    assert _session_data(client) == {"user_id": user_id}
    assert (await client.get("/admin/")).status_code == 200


@pytest.mark.parametrize(
    ("username", "password", "superuser", "active"),
    [
        ("root", "wrong-password", True, True),
        ("ghost", PASSWORD, True, True),
        ("plain", PASSWORD, False, True),
        ("sleepy", PASSWORD, True, False),
    ],
    ids=["wrong-password", "unknown-user", "not-superuser", "inactive"],
)
async def test_failed_login_is_400_with_one_generic_message(
    client, maker, username, password, superuser, active
):
    for name in ("root", "plain", "sleepy"):
        await _add_user(maker, name, superuser=name != "plain", active=name != "sleepy")

    response = await _login(client, username, password)

    assert response.status_code == 400
    assert admin_backend.INVALID_LOGIN_MESSAGE in response.text
    assert "alert alert-danger" in response.text
    assert "user_id" not in _session_data(client)
    assert (await client.get("/admin/")).status_code == 302


async def test_too_many_attempts_redraw_login_with_429_and_retry_after(client, maker, redis):
    await _add_user(maker, "root")
    for _ in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS):
        assert (await _login(client, "root", "wrong-password")).status_code == 400

    response = await _login(client, "root")  # 맞는 비밀번호여도 한도가 먼저다

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert admin_backend.TOO_MANY_MESSAGE in response.text
    assert 'name="password"' in response.text
    keys = {key.decode() for key in await redis.keys("*")}
    assert keys and all(key.startswith("admin:rl:login:") for key in keys)  # API 로그인 키와 분리


async def test_success_resets_ip_username_counter(client, maker, redis):
    await _add_user(maker, "root")
    await _login(client, "root", "wrong-password")

    assert (await _login(client, "root")).status_code == 302

    keys = {key.decode() for key in await redis.keys("*")}
    assert keys == {"admin:rl:login:127.0.0.1"}  # IP 카운터만 남는다


async def test_demoted_superuser_is_rejected_on_next_request(client, maker):
    user_id = await _add_user(maker, "root")
    await _login(client, "root")
    assert (await client.get("/admin/")).status_code == 200

    await _set_flags(maker, user_id, is_superuser=False)

    response = await client.get("/admin/")
    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert _session_data(client) == {}  # 세션도 비운다


async def test_deactivated_superuser_is_rejected_on_next_request(client, maker):
    user_id = await _add_user(maker, "root")
    await _login(client, "root")

    await _set_flags(maker, user_id, is_active=False)

    assert (await client.get("/admin/")).status_code == 302


async def test_logout_clears_session(client, maker):
    await _add_user(maker, "root")
    await _login(client, "root")

    response = await client.get("/admin/logout")

    assert response.status_code == 302
    assert _session_data(client) == {}
    assert (await client.get("/admin/")).status_code == 302


async def test_login_replaces_preexisting_session_data(client, maker):
    """세션 고정 방지 — 로그인 전 세션 내용(심어 둔 값 포함)은 남지 않는다."""
    user_id = await _add_user(maker, "root")
    signer = itsdangerous.TimestampSigner(session_settings.SESSION_SECRET_KEY)
    planted = b64encode(json.dumps({"planted": "x", "user_id": "attacker"}).encode())
    # httpx 는 점 없는 호스트의 쿠키를 "<host>.local" 도메인으로 저장한다 — 서버가 내려 줄 쿠키와
    # 같은 자리에 심어야 로그인 응답이 그것을 덮어쓴다.
    client.cookies.set(
        ADMIN_SESSION_COOKIE,
        signer.sign(planted).decode(),
        domain="testserver.local",
        path="/admin",
    )
    assert _session_data(client)["planted"] == "x"

    await _login(client, "root")

    assert _session_data(client) == {"user_id": user_id}


async def test_session_cookie_attributes(client, maker):
    await _add_user(maker, "root")

    response = await _login(client, "root")

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{ADMIN_SESSION_COOKIE}=")
    assert ADMIN_SESSION_COOKIE != session_settings.SESSION_COOKIE_NAME
    for attribute in ("path=/admin", "samesite=strict", "httponly", "max-age=28800"):
        assert attribute in cookie
    assert "secure" not in cookie  # ENV=test


@pytest.mark.parametrize(
    ("env", "secure"), [("production", True), ("staging", True), ("development", False)]
)
def test_secure_cookie_in_deployed_envs(monkeypatch, env, secure):
    monkeypatch.setattr(admin_module.app_settings, "ENV", env)
    backend = admin_module.build_admin_auth_backend(FastAPI())
    assert backend.middlewares[0].kwargs["https_only"] is secure


async def test_legacy_bcrypt_superuser_login_persists_argon2_rehash(client, maker):
    """API 로그인의 재해시 경로(``AuthService.authenticate``)를 그대로 쓰고 커밋한다."""
    legacy = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    user_id = await _add_user(maker, "root", hashed=legacy)

    assert (await _login(client, "root")).status_code == 302

    async with maker() as session:
        stored = (
            await session.execute(select(User.hashed_password).where(User.id == user_id))
        ).scalar_one()
    assert stored.startswith("$argon2id$")


def test_create_admin_interface_injects_backend_and_templates(maker):
    app = FastAPI()
    backend = admin_module.build_admin_auth_backend(app, session_factory=maker)
    assert backend.templates is None

    admin = admin_module.create_admin_interface(app, maker.kw["bind"], backend)

    assert admin.authentication_backend is backend
    assert backend.templates is admin.templates
    assert admin.templates_dir == str(admin_module.ADMIN_TEMPLATES_DIR)


# =============================================================================
# 화면 — Bootstrap 로그인 템플릿
# =============================================================================
async def test_login_page_is_bootstrap_with_sri(client):
    response = await client.get("/admin/login")

    assert response.status_code == 200
    html = response.text
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="ko">' in html
    assert 'name="viewport"' in html
    link = re.search(r"<link[^>]*bootstrap[^>]*>", html, re.S)
    assert link, "Bootstrap CSS 링크가 없다"
    assert f'href="{BOOTSTRAP_CSS}"' in link.group(0)
    assert f'integrity="{BOOTSTRAP_SRI}"' in link.group(0)
    assert 'crossorigin="anonymous"' in link.group(0)
    assert "<script" not in html  # JS 는 쓰지 않는다
    assert 'action="http://testserver/admin/login"' in html
    assert 'method="POST"' in html


async def test_login_form_fields_and_labels(client):
    html = (await client.get("/admin/login")).text

    username = re.search(r'<input[^>]*name="username"[^>]*>', html, re.S).group(0)
    password = re.search(r'<input[^>]*name="password"[^>]*>', html, re.S).group(0)
    assert (
        'autocomplete="username"' in username and "required" in username and "autofocus" in username
    )
    assert 'autocomplete="current-password"' in password and "required" in password
    assert 'type="password"' in password
    for field in ("username", "password"):
        assert f'<label for="{field}"' in html and f'id="{field}"' in html
    assert "alert-danger" not in html  # 오류가 없으면 경고 상자도 없다


async def test_error_message_is_html_escaped(client, maker, monkeypatch):
    monkeypatch.setattr(admin_backend, "INVALID_LOGIN_MESSAGE", "<script>alert(1)</script>")

    response = await _login(client, "nobody", "whatever-password")

    assert response.status_code == 400
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)</script>" not in response.text


# =============================================================================
# 통합 — scripts/create_superuser 로 만든 계정으로 /admin 에 들어간다
# =============================================================================
async def test_create_superuser_then_admin_login_flow(client, maker):
    code = await asyncio.to_thread(
        create_superuser_main,
        ["--username", "boss", "--email", "boss@example.com", "--password-stdin"],
        stdin=io.StringIO(PASSWORD + "\n"),
        session_factory=maker,
    )
    assert code == EXIT_OK
    await _add_user(maker, "worker", superuser=False)

    first = await client.get("/admin/")
    assert first.status_code == 302 and first.headers["location"].endswith("/admin/login")
    assert (await _login(client, "boss", "wrong-password")).status_code == 400
    assert (await _login(client, "worker")).status_code == 400  # 일반 사용자는 못 들어온다
    assert (await _login(client, "boss")).status_code == 302
    assert (await client.get("/admin/")).status_code == 200
    assert (await client.get("/admin/logout")).status_code == 302
    assert (await client.get("/admin/")).status_code == 302


def test_main_app_admin_requires_login():
    """조립된 ``main.app`` 의 /admin 에도 백엔드가 붙어 있다."""
    import main

    assert isinstance(main.admin.authentication_backend, AdminAuthBackend)
    assert main.admin.templates_dir == str(admin_module.ADMIN_TEMPLATES_DIR)
    assert (admin_module.ADMIN_TEMPLATES_DIR / "sqladmin" / "login.html").is_file()
    assert config.session_settings.SESSION_SECRET_KEY  # 서명 키는 기존 설정


# =============================================================================
# 로그인 폼 CSRF — synchronizer token (security-ops-hardening ADR-004)
# =============================================================================
def _refuse_credentials(backend: AdminAuthBackend) -> None:
    """자격 확인에 닿으면 실패하게 한다 — CSRF 거부는 그보다 먼저여야 한다."""

    def boom(*_args):
        raise AssertionError("CSRF 거부 전에 자격 확인을 했다")

    backend._auth_service_factory = boom


async def _post(client, csrf_token: str | None, username: str = "root") -> httpx.Response:
    data = {"username": username, "password": PASSWORD}
    if csrf_token is not None:
        data["csrf_token"] = csrf_token
    return await client.post("/admin/login", data=data)


async def test_login_page_renders_hidden_csrf_field_bound_to_session(client):
    token = await admin_csrf_token(client)

    assert len(token) >= 43  # token_urlsafe(32)
    assert _session_data(client)["csrf_token"] == token
    assert await admin_csrf_token(client) == token  # 다시 그려도 같은 토큰


@pytest.mark.parametrize("submitted", [None, "", "wrong-token"], ids=["missing", "empty", "wrong"])
async def test_post_without_matching_csrf_token_is_403_before_rate_limit_and_credentials(
    client, admin_app, maker, redis, submitted
):
    _, backend = admin_app
    await _add_user(maker, "root")
    await admin_csrf_token(client)
    _refuse_credentials(backend)

    response = await _post(client, submitted)

    assert response.status_code == 403
    assert admin_backend.CSRF_FAILED_MESSAGE in response.text
    assert 'name="password"' in response.text  # 로그인 화면을 다시 그린다
    assert await redis.keys("*") == []  # 레이트 리밋 카운터도 늘지 않는다
    assert "user_id" not in _session_data(client)


async def test_post_without_any_session_is_403(client, admin_app, maker):
    _, backend = admin_app
    await _add_user(maker, "root")
    _refuse_credentials(backend)

    response = await _post(client, "forged-token")

    assert response.status_code == 403
    # 다시 그린 화면은 새 토큰을 싣는다 — 사용자가 바로 재시도할 수 있다.
    assert CSRF_INPUT.search(response.text).group(1) == _session_data(client)["csrf_token"]


async def test_token_from_another_session_is_rejected(admin_app, maker):
    app, backend = admin_app
    await _add_user(maker, "root")
    transport = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as victim,
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as attacker,
    ):
        attacker_token = await admin_csrf_token(attacker)
        await admin_csrf_token(victim)
        _refuse_credentials(backend)

        response = await _post(victim, attacker_token)

    assert response.status_code == 403


async def test_failed_login_keeps_token_so_the_user_can_retry(client, maker):
    await _add_user(maker, "root")
    token = await admin_csrf_token(client)

    failed = await _post(client, token, username="nobody")
    assert failed.status_code == 400
    assert CSRF_INPUT.search(failed.text).group(1) == token

    assert (await _post(client, token)).status_code == 302


async def test_successful_login_rotates_csrf_token(client, maker):
    user_id = await _add_user(maker, "root")
    before = await admin_csrf_token(client)

    assert (await _post(client, before)).status_code == 302
    assert _session_data(client) == {"user_id": user_id}  # 이전 토큰은 버려졌다

    after = await admin_csrf_token(client)
    assert after != before
    assert (await _post(client, before)).status_code == 403  # 옛 토큰은 다시 못 쓴다


async def test_csrf_comparison_is_constant_time(client, maker, monkeypatch):
    await _add_user(maker, "root")
    token = await admin_csrf_token(client)
    calls = []
    real = admin_backend.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(admin_backend.hmac, "compare_digest", spy)

    assert (await _post(client, token)).status_code == 302
    # 같은 hmac 모듈을 세션 서명 검증(itsdangerous)도 쓴다 — 토큰 대조 호출이 있는지만 본다.
    assert (token.encode(), token.encode()) in calls
