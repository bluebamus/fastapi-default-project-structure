"""관리 세션 = Redis 서버 세션 (admin-session-hardening ADR-001·002).

쿠키에는 무작위 세션 ID 만, 내용은 Redis(``admin:sess:{HMAC}``). 로그아웃·강등·비활성화·삭제는 서버에서 바로
폐기하고, 이전 쿠키 사본은 다시 쓸 수 없다. 미사용·절대 만료, Redis 장애 fail-closed, 설정 검증.
실물 부품: SQLite 파일 DB, fakeredis, 실제 ``build_admin_auth_backend``·``create_admin_interface``·뷰 등록.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import config
from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security import admin_session
from app.core.security.admin_session import (
    ADMIN_SESSION_COOKIE,
    STORE_UNAVAILABLE_MESSAGE,
    AdminSessionStore,
)
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.dependencies import get_password_hasher, new_admin_session_store
from app.core.security.refresh_store import RefreshTokenStore
from app.features import admin as admin_module
from app.features.user.models.models import User
from app.features.user.schemas.user_schema import UserUpdate
from app.features.user.services.user_service import UserService
from config import session_settings
from tests.admin_csrf import (
    admin_login,
    admin_logout,
    admin_page_token,
    admin_session_data,
    admin_session_id,
)

import_all_models()

PASSWORD = "s3cret-pass-word"
SUPER = Principal(id="admin-id", username="admin", is_superuser=True)


# =============================================================================
# fixtures
# =============================================================================
@pytest_asyncio.fixture
async def maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sess.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def server():
    return FakeServer()


@pytest_asyncio.fixture
async def redis(server):
    client = FakeAsyncRedis(server=server)
    yield client
    await client.aclose()


@pytest.fixture
def app(maker, redis):
    app = FastAPI()
    app.state.redis = redis
    backend = admin_module.build_admin_auth_backend(app, session_factory=maker)
    admin = admin_module.create_admin_interface(app, maker.kw["bind"], backend)
    admin_module.register_admin_views(admin)
    return app


def _browser(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest_asyncio.fixture
async def client(app):
    async with _browser(app) as http:
        yield http


async def _add_user(maker, username: str = "root", *, superuser: bool = True) -> str:
    async with maker() as session:
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=await get_password_hasher().hash(PASSWORD),
            is_superuser=superuser,
        )
        session.add(user)
        await session.commit()
        return user.id


def _store(redis) -> AdminSessionStore:
    return new_admin_session_store(redis)


async def _key_of(client, redis) -> str:
    return _store(redis).key(admin_session_id(client))


def _with_cookie(app, sid: str) -> httpx.AsyncClient:
    """다른 곳에 복사해 둔 쿠키 사본으로 요청하는 브라우저."""
    browser = _browser(app)
    browser.cookies.set(ADMIN_SESSION_COOKIE, sid, domain="testserver.local", path="/admin")
    return browser


async def _index_status(browser) -> int:
    return (await browser.get("/admin/")).status_code


# =============================================================================
# 쿠키에는 세션 ID 만, Redis 키는 HMAC
# =============================================================================
async def test_cookie_carries_only_a_random_session_id(client, maker, redis):
    user_id = await _add_user(maker)

    response = await admin_login(client, "root", PASSWORD)

    assert response.status_code == 302
    sid = admin_session_id(client)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", sid)  # token_urlsafe(32), 서명·내용 없음
    assert user_id not in sid and "." not in sid
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{ADMIN_SESSION_COOKIE}={sid};")
    assert user_id not in cookie


async def test_redis_key_is_hmac_of_session_id_and_value_holds_the_session(client, maker, redis):
    user_id = await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    sid = admin_session_id(client)

    digest = hmac.new(
        session_settings.SESSION_SECRET_KEY.encode(), sid.encode(), hashlib.sha256
    ).hexdigest()
    key = f"admin:sess:{digest}"
    assert [k.decode() for k in await redis.keys("admin:sess:*")] == [key]
    assert sid not in key
    record = json.loads(await redis.get(key))
    assert record["data"] == {"user_id": user_id}
    assert record["user_id"] == user_id
    assert isinstance(record["created_at"], float)
    assert await redis.smembers(f"admin:user_sessions:{user_id}") == {key.encode()}


async def test_another_secret_key_maps_to_another_redis_key(redis):
    """``SESSION_SECRET_KEY`` 를 바꾸면 같은 쿠키가 다른 키를 가리킨다 — 모든 세션이 무효가 된다."""
    a = AdminSessionStore(redis, secret_key="a" * 32, max_age_seconds=600, idle_seconds=60)
    b = AdminSessionStore(redis, secret_key="b" * 32, max_age_seconds=600, idle_seconds=60)
    assert a.key("sid") != b.key("sid")


# =============================================================================
# 로그아웃 — 이전 쿠키 사본 거부
# =============================================================================
async def test_logout_deletes_the_server_session_and_rejects_a_copied_cookie(
    app, client, maker, redis
):
    user_id = await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    copied = admin_session_id(client)
    key = await _key_of(client, redis)

    response = await admin_logout(client)

    assert response.status_code == 302
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert await redis.get(key) is None
    assert await redis.smembers(f"admin:user_sessions:{user_id}") == set()
    async with _with_cookie(app, copied) as stolen:
        replay = await stolen.get("/admin/")
    assert replay.status_code == 302 and replay.headers["location"].endswith("/admin/login")
    assert "max-age=0" in replay.headers["set-cookie"].lower()  # 없는 세션의 쿠키는 지운다


async def test_unknown_session_id_is_an_empty_session(app):
    async with _with_cookie(app, AdminSessionStore.new_session_id()) as browser:
        response = await browser.get("/admin/")
    assert response.status_code == 302
    assert "max-age=0" in response.headers["set-cookie"].lower()


async def test_relogin_from_a_logged_in_session_rotates_the_id(client, maker, redis):
    await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    first, first_key = admin_session_id(client), await _key_of(client, redis)

    assert (await admin_login(client, "root", PASSWORD)).status_code == 302

    assert admin_session_id(client) != first
    assert await redis.get(first_key) is None


# =============================================================================
# 만료
# =============================================================================
async def test_every_request_resets_the_idle_ttl(client, maker, redis):
    await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    key = await _key_of(client, redis)
    await redis.expire(key, 5)

    assert await _index_status(client) == 200

    assert await redis.ttl(key) == session_settings.ADMIN_SESSION_IDLE_SECONDS


async def test_idle_session_expires(client, maker, monkeypatch):
    monkeypatch.setattr(session_settings, "ADMIN_SESSION_IDLE_SECONDS", 1)
    await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    assert await _index_status(client) == 200

    await asyncio.sleep(1.2)

    assert await _index_status(client) == 302


async def test_absolute_expiry_caps_the_ttl_and_is_not_extended(client, maker, redis):
    await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    key = await _key_of(client, redis)
    record = json.loads(await redis.get(key))
    max_age = session_settings.ADMIN_SESSION_MAX_AGE_SECONDS

    # 절대 만료까지 100초 남은 세션: 요청해도 TTL 은 남은 시간을 넘지 않는다.
    record["created_at"] -= max_age - 100
    await redis.set(key, json.dumps(record), ex=60)
    assert await _index_status(client) == 200
    assert 0 < await redis.ttl(key) <= 100

    # 절대 만료가 지난 세션: 쓰는 중이어도 끝난다.
    record["created_at"] -= 101
    await redis.set(key, json.dumps(record), ex=60)
    response = await client.get("/admin/")
    assert response.status_code == 302
    assert await redis.get(key) is None


def test_store_refuses_to_save_past_absolute_expiry():
    now = 1_000_000.0
    redis = FakeAsyncRedis()
    store = AdminSessionStore(
        redis, secret_key="k" * 32, max_age_seconds=600, idle_seconds=60, clock=lambda: now
    )

    async def scenario():
        assert await store.save("sid", {"user_id": "u"}, now - 590, new=True)
        assert await redis.ttl(store.key("sid")) == 10  # min(idle 60, 남은 10)
        assert await store.load("sid") is not None
        assert not await store.save("sid", {"user_id": "u"}, now - 600)
        assert await store.load("sid") is None

    asyncio.run(scenario())


# =============================================================================
# 즉시 폐기 — 다른 브라우저 세션까지
# =============================================================================
async def _two_browsers(app, maker):
    user_id = await _add_user(maker)
    first, second = _browser(app), _browser(app)
    for browser in (first, second):
        assert (await admin_login(browser, "root", PASSWORD)).status_code == 302
        assert await _index_status(browser) == 200
    return user_id, first, second


def _service(db_session, redis) -> UserService:
    return UserService(
        db_session,
        OwnershipPolicy(),
        get_password_hasher(),
        RefreshTokenStore(redis, 60),
        new_admin_session_store(redis),
    )


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(UserUpdate(is_active=False), id="deactivate"),
        pytest.param(UserUpdate(is_superuser=False), id="demote"),
        pytest.param(None, id="delete"),
    ],
)
async def test_user_service_revokes_every_admin_session_of_that_user(app, maker, redis, change):
    user_id, first, second = await _two_browsers(app, maker)
    copied = admin_session_id(first)
    assert len(await redis.keys("admin:sess:*")) == 2

    async with maker() as db_session:
        service = _service(db_session, redis)
        if change is None:
            await service.delete_user(user_id)
        else:
            await service.update_user(user_id, change, SUPER)
        await db_session.commit()

    assert await redis.keys("admin:sess:*") == []
    assert await redis.exists(f"admin:user_sessions:{user_id}") == 0
    if change is not None:  # 되돌려도(재활성화·재승격) 폐기된 세션은 살아나지 않는다
        async with maker() as db_session:
            await _service(db_session, redis).update_user(
                user_id, UserUpdate(is_active=True, is_superuser=True), SUPER
            )
            await db_session.commit()
    async with _with_cookie(app, copied) as stolen:
        assert await _index_status(stolen) == 302
    for browser in (first, second):
        assert await _index_status(browser) == 302
        await browser.aclose()


async def test_user_service_keeps_admin_sessions_on_unrelated_update(app, maker, redis):
    user_id, first, second = await _two_browsers(app, maker)
    async with maker() as db_session:
        await _service(db_session, redis).update_user(
            user_id, UserUpdate(email="new@example.com"), SUPER
        )
        await db_session.commit()
    assert len(await redis.keys("admin:sess:*")) == 2
    for browser in (first, second):
        await browser.aclose()


async def test_user_service_without_admin_store_still_works(maker, redis):
    """관리 화면을 끈 앱(저장소 None)에서도 비활성화·삭제가 된다."""
    user_id = await _add_user(maker)
    async with maker() as db_session:
        service = UserService(
            db_session, OwnershipPolicy(), get_password_hasher(), RefreshTokenStore(redis, 60), None
        )
        await service.update_user(user_id, UserUpdate(is_active=False), SUPER)
        await service.delete_user(user_id)


async def test_admin_ui_deactivation_revokes_other_browser_sessions(app, maker, redis):
    user_id, actor, victim = await _two_browsers(app, maker)
    other = await _add_user(maker, "other")
    async with _browser(app) as third:
        assert (await admin_login(third, "other", PASSWORD)).status_code == 302
        await _index_status(third)
        token = await admin_page_token(actor, f"/admin/user/edit/{other}")
        form = {
            "username": "other",
            "email": "other@example.com",
            "is_superuser": "y",
            "csrf_token": token,
        }  # is_active 를 빼면 체크 해제 = 비활성화

        response = await actor.post(f"/admin/user/edit/{other}", data=form)

        assert response.status_code == 302
        assert await _index_status(third) == 302
        assert await redis.exists(f"admin:user_sessions:{other}") == 0
    assert await _index_status(victim) == 200  # 다른 사용자의 세션은 그대로
    await actor.aclose()
    await victim.aclose()
    assert user_id


async def test_admin_ui_delete_revokes_that_users_sessions(app, maker, redis):
    _, actor, victim = await _two_browsers(app, maker)
    other = await _add_user(maker, "other")
    async with _browser(app) as third:
        assert (await admin_login(third, "other", PASSWORD)).status_code == 302
        token = await admin_page_token(actor, "/admin/user/list")

        response = await actor.delete(
            f"/admin/user/delete?pks={other}", headers={"X-CSRF-Token": token}
        )

        assert response.status_code == 200
        assert await redis.exists(f"admin:user_sessions:{other}") == 0
        assert await _index_status(third) == 302
    await actor.aclose()
    await victim.aclose()


async def test_revocation_during_a_request_is_not_undone_by_the_response(client, maker, redis):
    """요청 처리 중에 폐기된 세션을 응답 저장이 되살리지 않는다(SET XX)."""
    user_id = await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    store = _store(redis)
    key = await _key_of(client, redis)
    data = await admin_session_data(client, redis)
    created_at = json.loads(await redis.get(key))["created_at"]

    await store.revoke_user(user_id)

    assert not await store.save(admin_session_id(client), data, created_at)
    assert await redis.get(key) is None


# =============================================================================
# Redis 장애 — fail-closed
# =============================================================================
async def test_redis_outage_is_503_not_a_pass(client, maker, server):
    await _add_user(maker)
    await admin_login(client, "root", PASSWORD)
    assert await _index_status(client) == 200

    server.connected = False
    response = await client.get("/admin/")

    assert response.status_code == 503
    assert STORE_UNAVAILABLE_MESSAGE in response.text


async def test_missing_redis_client_is_503(app, client):
    app.state.redis = None
    response = await client.get("/admin/login")
    assert response.status_code == 503


# =============================================================================
# 조립·설정
# =============================================================================
def test_backend_uses_the_redis_session_middleware_not_signed_cookies(maker):
    backend = admin_module.build_admin_auth_backend(FastAPI(), session_factory=maker)
    names = [m.cls.__name__ for m in backend.middlewares]
    assert names == ["RedisSessionMiddleware", "AdminCsrfMiddleware"]


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"ADMIN_SESSION_MAX_AGE_SECONDS": "59"}, "ADMIN_SESSION_MAX_AGE_SECONDS"),
        ({"ADMIN_SESSION_IDLE_SECONDS": "59"}, "ADMIN_SESSION_IDLE_SECONDS"),
        (
            {"ADMIN_SESSION_MAX_AGE_SECONDS": "600", "ADMIN_SESSION_IDLE_SECONDS": "601"},
            "이하여야",
        ),
    ],
)
def test_session_settings_are_validated(monkeypatch, env, message):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=message):
        config.SessionSettings(_env_file=None)


def test_session_settings_defaults():
    settings = config.SessionSettings(_env_file=None)
    assert settings.ADMIN_SESSION_MAX_AGE_SECONDS == 28800
    assert settings.ADMIN_SESSION_IDLE_SECONDS == 1800
    assert admin_session.ADMIN_COOKIE_PATH == "/admin"
