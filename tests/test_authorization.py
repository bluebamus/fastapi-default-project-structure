"""라우트 인가 정책 — 401·403·소유권·슈퍼유저 우회 (service-hardening ADR-017·018, ledger F-022~F-024).

앱 전체를 in-memory sqlite + fakeredis 로 띄우고, 실제 ``TokenService`` 로 발급한 토큰(``tests.auth_headers``)
을 싣는다 — 의존성을 가짜로 바꾸지 않으므로 ``OAuth2PasswordBearer`` → ``TokenService`` → ``Principal`` →
``require_superuser``/``OwnershipPolicy`` 경로가 운영과 같다. 클라이언트에는 기본 헤더가 없다.

권한 표(README "권한" 절과 같다):

| 기능 | 조회 | 생성 | 수정·삭제 |
|---|---|---|---|
| blog·sns·reply | 공개 | 로그인 | 작성자 또는 슈퍼유저 |
| catalog | 공개 | 슈퍼유저 | 슈퍼유저 |
| reports·접속 로그 | 슈퍼유저 | 슈퍼유저 | — |
| user | 목록 슈퍼유저, 단건 본인·슈퍼유저 | 슈퍼유저 | 수정 본인·슈퍼유저(`is_active`·`is_superuser` 는 슈퍼유저), 삭제 슈퍼유저 |
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.redis import get_redis
from app.core.security.dependencies import get_refresh_token_store, get_token_service
from app.core.security.tokens import TokenType
from app.features.blog.models.models import Post
from app.features.user.models.models import User
from config import jwt_settings
from main import app
from tests.auth_headers import ALICE, BOB, SUPERUSER, bearer
from tests.session_overrides import override_db_sessions

import_all_models()


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = FakeAsyncRedis()

    override_db_sessions(app, maker)
    app.dependency_overrides[get_redis] = lambda: redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, maker, redis
    app.dependency_overrides.clear()
    await redis.aclose()
    await engine.dispose()


@pytest.fixture
def client(env):
    return env[0]


# =============================================================================
# 소유 리소스(blog·sns·reply) — 같은 규칙을 세 기능에 건다
# =============================================================================
@dataclass(frozen=True)
class Owned:
    collection: str
    create_body: dict
    update_body: dict


OWNED = [
    Owned("/api/v1/blog/posts", {"title": "t", "content": "c"}, {"title": "changed"}),
    Owned("/api/v1/sns/posts", {"content": "c"}, {"content": "changed"}),
    Owned("/api/v1/reply/replies", {"content": "c", "post_id": "p1"}, {"content": "changed"}),
]
OWNED_IDS = ["blog", "sns", "reply"]


async def _create_owned(client, case: Owned, principal=ALICE) -> dict:
    resp = await client.post(case.collection, json=case.create_body, headers=bearer(principal))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _forged_token() -> str:
    """서명 키가 다른 access 토큰 — claim 은 정상이다."""
    now = datetime.now(UTC)
    claims = {
        "sub": ALICE.id,
        "username": ALICE.username,
        "su": True,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "f" * 32,
        "iss": jwt_settings.JWT_ISSUER,
        "aud": jwt_settings.JWT_AUDIENCE,
    }
    return jwt.encode(claims, "x" * 64, algorithm=jwt_settings.JWT_ALGORITHM)


def _signed_access(**overrides) -> str:
    """앱의 진짜 키로 서명한 access 토큰 — claim 만 바꾼다."""
    now = datetime.now(UTC)
    claims = {
        "sub": ALICE.id,
        "username": ALICE.username,
        "su": False,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "a" * 32,
        "iss": jwt_settings.JWT_ISSUER,
        "aud": jwt_settings.JWT_AUDIENCE,
        **overrides,
    }
    claims = {key: value for key, value in claims.items() if value is not None}
    return jwt.encode(
        claims, jwt_settings.ACCESS_TOKEN_SECRET_KEY, algorithm=jwt_settings.JWT_ALGORITHM
    )


# =============================================================================
# 401 — 토큰 없음·만료·위조·종류 혼동·su 누락
# =============================================================================
@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_write_without_token_is_401_with_bearer_challenge(client, case):
    resp = await client.post(case.collection, json=case.create_body)

    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def _bad_tokens() -> dict[str, str]:
    refresh = get_token_service().issue_refresh(ALICE.id, "fam-1").token
    return {
        "expired": _signed_access(exp=datetime.now(UTC) - timedelta(minutes=5)),
        "forged": _forged_token(),
        "refresh-as-access": refresh,
        "missing-su": _signed_access(su=None),
        "su-not-bool": _signed_access(su="yes"),
        "garbage": "not-a-jwt",
    }


@pytest.mark.parametrize("kind", list(_bad_tokens()))
async def test_bad_token_is_401(client, kind):
    token = _bad_tokens()[kind]

    resp = await client.post(
        "/api/v1/blog/posts",
        json={"title": "t", "content": "c"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 401, resp.text
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_signed_token_with_all_claims_is_accepted(client):
    """위 401 들이 서명·형식 탓이 아님을 보이는 대조군 — 같은 생성기로 su 만 있으면 통과한다."""
    resp = await client.post(
        "/api/v1/blog/posts",
        json={"title": "t", "content": "c"},
        headers={"Authorization": f"Bearer {_signed_access()}"},
    )
    assert resp.status_code == 201, resp.text


# =============================================================================
# 작성자는 서버가 채운다 · GET 은 공개
# =============================================================================
@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_author_is_set_from_the_principal_not_the_body(client, case):
    body = {**case.create_body, "author": "mallory", "author_id": BOB.id}

    resp = await client.post(case.collection, json=body, headers=bearer(ALICE))

    assert resp.status_code == 201, resp.text
    assert resp.json()["author"] == ALICE.username
    assert resp.json()["author_id"] == ALICE.id


@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_reads_are_public(client, case):
    created = await _create_owned(client, case)

    assert (await client.get(case.collection)).status_code == 200
    assert (await client.get(f"{case.collection}/{created['id']}")).status_code == 200


# =============================================================================
# 소유권 — 남의 것 403, 내 것 성공, 슈퍼유저 우회
# =============================================================================
@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_other_users_cannot_modify_or_delete(client, case):
    created = await _create_owned(client, case, ALICE)
    item = f"{case.collection}/{created['id']}"

    patched = await client.patch(item, json=case.update_body, headers=bearer(BOB))
    deleted = await client.delete(item, headers=bearer(BOB))

    assert patched.status_code == 403, patched.text
    assert deleted.status_code == 403, deleted.text
    assert patched.json()["error_code"] == "FORBIDDEN"
    still = await client.get(item)
    assert still.status_code == 200
    assert still.json() == created  # 403 요청이 아무것도 바꾸지 않았다


@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_owner_can_modify_and_delete(client, case):
    created = await _create_owned(client, case, ALICE)
    item = f"{case.collection}/{created['id']}"

    patched = await client.patch(item, json=case.update_body, headers=bearer(ALICE))
    assert patched.status_code == 200, patched.text
    assert patched.json()["author_id"] == ALICE.id  # 수정은 소유자를 바꾸지 않는다

    assert (await client.delete(item, headers=bearer(ALICE))).status_code == 204


@pytest.mark.parametrize("case", OWNED, ids=OWNED_IDS)
async def test_superuser_can_modify_and_delete_any(client, case):
    created = await _create_owned(client, case, ALICE)
    item = f"{case.collection}/{created['id']}"

    patched = await client.patch(item, json=case.update_body, headers=bearer(SUPERUSER))
    assert patched.status_code == 200, patched.text
    assert patched.json()["author_id"] == ALICE.id

    assert (await client.delete(item, headers=bearer(SUPERUSER))).status_code == 204


async def test_row_without_owner_is_modifiable_only_by_superuser(env):
    """인가 도입 전 행(author_id NULL)은 슈퍼유저만 고친다(residual-risk R-006)."""
    client, maker, _ = env
    async with maker() as session:
        legacy = Post(title="legacy", content="c", author="someone")
        session.add(legacy)
        await session.commit()
        item = f"/api/v1/blog/posts/{legacy.id}"

    denied = await client.patch(item, json={"title": "x"}, headers=bearer(ALICE))
    allowed = await client.patch(item, json={"title": "x"}, headers=bearer(SUPERUSER))

    assert denied.status_code == 403
    assert allowed.status_code == 200


async def test_missing_resource_is_404_before_ownership(client):
    resp = await client.patch("/api/v1/blog/posts/nope", json={"title": "x"}, headers=bearer(BOB))
    assert resp.status_code == 404


# =============================================================================
# 관리 경로 — 일반 사용자 403, 슈퍼유저 성공, 토큰 없으면 401
# =============================================================================
ADMIN_ROUTES = [
    ("POST", "/api/v1/catalog/products", {"name": "k", "price": "1.00"}),
    ("PATCH", "/api/v1/catalog/products/any-id", {"price": "2.00"}),
    ("DELETE", "/api/v1/catalog/products/any-id", None),
    ("GET", "/api/v1/reports/sales/daily?start_date=2026-08-01&end_date=2026-08-02", None),
    (
        "POST",
        "/api/v1/reports/sales/daily/snapshots",
        {"start_date": "2026-08-01", "end_date": "2026-08-02"},
    ),
    ("GET", "/api/v1/home/access-logs", None),
    ("GET", "/api/v1/home/access-logs/recent", None),
    ("GET", "/api/v1/home/access-logs/by-ip/127.0.0.1", None),
    ("GET", f"/api/v1/home/access-logs/by-user/{ALICE.id}", None),
    ("GET", "/api/v1/home/access-logs/stats", None),
    ("GET", "/api/v1/user/users", None),
    ("POST", "/api/v1/user/users", {"username": "x", "email": "x@x.com", "password": "pw123456"}),
    ("DELETE", f"/api/v1/user/users/{BOB.id}", None),
]
ADMIN_IDS = [f"{method} {path.split('?')[0]}" for method, path, _ in ADMIN_ROUTES]


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ROUTES, ids=ADMIN_IDS)
async def test_admin_routes_are_403_for_normal_users(client, method, path, body):
    resp = await client.request(method, path, json=body, headers=bearer(ALICE))

    assert resp.status_code == 403, resp.text
    assert resp.json()["error_code"] == "FORBIDDEN"


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ROUTES, ids=ADMIN_IDS)
async def test_admin_routes_are_401_without_token(client, method, path, body):
    resp = await client.request(method, path, json=body)

    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/sales/daily?start_date=2026-08-01&end_date=2026-08-02",
        "/api/v1/home/access-logs",
        "/api/v1/home/access-logs/recent",
        "/api/v1/home/access-logs/stats",
        "/api/v1/user/users",
    ],
)
async def test_admin_reads_succeed_for_superuser(client, path):
    resp = await client.get(path, headers=bearer(SUPERUSER))
    assert resp.status_code == 200, resp.text


async def test_catalog_reads_are_public_and_writes_need_superuser(client):
    created = await client.post(
        "/api/v1/catalog/products",
        json={"name": "keyboard", "price": "129.00"},
        headers=bearer(SUPERUSER),
    )
    assert created.status_code == 201, created.text

    assert (await client.get("/api/v1/catalog/products")).status_code == 200
    item = await client.get(f"/api/v1/catalog/products/{created.json()['id']}")
    assert item.status_code == 200


# =============================================================================
# user — 본인 또는 슈퍼유저, 상태 플래그는 슈퍼유저만
# =============================================================================
async def _create_user(client, username: str, *, superuser: bool = False) -> dict:
    resp = await client.post(
        "/api/v1/user/users",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password123",
            "is_superuser": superuser,
        },
        headers=bearer(SUPERUSER),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _as(user: dict, *, superuser: bool = False) -> dict[str, str]:
    from app.core.security.authorization import Principal

    return bearer(Principal(id=user["id"], username=user["username"], is_superuser=superuser))


async def test_superuser_creates_user_with_argon2_hash_and_flag(env):
    client, maker, _ = env
    created = await _create_user(client, "carol", superuser=True)

    assert created["is_superuser"] is True
    assert "password" not in created and "hashed_password" not in created
    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password).where(User.id == created["id"]))
    assert stored.startswith("$argon2id$")


async def test_create_user_requires_password(client):
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "nopass", "email": "nopass@example.com"},
        headers=bearer(SUPERUSER),
    )
    assert resp.status_code == 422


async def test_user_can_read_and_edit_self_but_not_others(client):
    alice = await _create_user(client, "alice")
    bob = await _create_user(client, "bob")

    assert (
        await client.get(f"/api/v1/user/users/{alice['id']}", headers=_as(alice))
    ).status_code == 200
    other = await client.get(f"/api/v1/user/users/{bob['id']}", headers=_as(alice))
    assert other.status_code == 403

    own = await client.patch(
        f"/api/v1/user/users/{alice['id']}", json={"email": "new@example.com"}, headers=_as(alice)
    )
    assert own.status_code == 200, own.text
    assert own.json()["email"] == "new@example.com"

    others = await client.patch(
        f"/api/v1/user/users/{bob['id']}", json={"email": "x@example.com"}, headers=_as(alice)
    )
    assert others.status_code == 403


async def test_unknown_user_id_is_403_for_normal_users(client):
    """남의 ID 는 존재 여부와 관계없이 403 — 404/403 차이로 계정 존재를 캐지 못한다."""
    alice = await _create_user(client, "alice")
    resp = await client.get("/api/v1/user/users/does-not-exist", headers=_as(alice))
    assert resp.status_code == 403


@pytest.mark.parametrize("field", ["is_active", "is_superuser"])
async def test_status_flags_are_superuser_only_even_on_self(client, field):
    alice = await _create_user(client, "alice")
    value = field == "is_superuser"  # 비활성화 또는 자기 승격 시도

    resp = await client.patch(
        f"/api/v1/user/users/{alice['id']}", json={field: value}, headers=_as(alice)
    )

    assert resp.status_code == 403, resp.text
    unchanged = await client.get(f"/api/v1/user/users/{alice['id']}", headers=_as(alice))
    assert unchanged.json()[field] is (not value)


async def test_superuser_can_change_status_flags(client):
    alice = await _create_user(client, "alice")

    resp = await client.patch(
        f"/api/v1/user/users/{alice['id']}",
        json={"is_superuser": True},
        headers=bearer(SUPERUSER),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["is_superuser"] is True


# =============================================================================
# 비활성화·삭제 → refresh 폐기, 로그인 토큰의 su
# =============================================================================
async def _register_and_login(client, username: str = "dave") -> tuple[str, dict]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "password123"},
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    return reg.json()["id"], login.json()


async def _family_revoked(redis, refresh_token: str) -> bool:
    family = get_token_service().decode(refresh_token, TokenType.REFRESH)["fam"]
    return await get_refresh_token_store(redis).is_family_revoked(family)


async def test_deactivation_revokes_refresh_tokens(env):
    """비활성화는 refresh family 를 폐기한다 — 다시 활성화해도 그 토큰으로는 회전할 수 없다.

    회전은 비활성 사용자를 따로 막으므로(F1) 비활성 상태의 401 만으로는 폐기를 증명하지 못한다.
    재활성화 뒤에도 401 이고 저장소에 폐기 표시가 있어야 ``revoke_user`` 가 불린 것이다.
    """
    client, _, redis = env
    user_id, tokens = await _register_and_login(client)
    item = f"/api/v1/user/users/{user_id}"

    deactivated = await client.patch(item, json={"is_active": False}, headers=bearer(SUPERUSER))
    assert deactivated.status_code == 200, deactivated.text
    assert await _family_revoked(redis, tokens["refresh_token"])

    await client.patch(item, json={"is_active": True}, headers=bearer(SUPERUSER))
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_deletion_revokes_refresh_tokens(env):
    client, _, redis = env
    user_id, tokens = await _register_and_login(client)

    deleted = await client.delete(f"/api/v1/user/users/{user_id}", headers=bearer(SUPERUSER))
    assert deleted.status_code == 204
    assert await _family_revoked(redis, tokens["refresh_token"])

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


async def test_login_token_carries_superuser_flag_from_the_database(client):
    user_id, tokens = await _register_and_login(client)
    claims = get_token_service().decode(tokens["access_token"], TokenType.ACCESS)
    assert claims["su"] is False
    assert claims["sub"] == user_id

    await client.patch(
        f"/api/v1/user/users/{user_id}", json={"is_superuser": True}, headers=bearer(SUPERUSER)
    )
    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    promoted = get_token_service().decode(rotated.json()["access_token"], TokenType.ACCESS)
    assert promoted["su"] is True  # 회전이 DB 의 현재 값으로 다시 발급한다
