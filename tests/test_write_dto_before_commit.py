"""쓰기 핸들러는 응답 DTO 검증을 커밋보다 **먼저** 한다 — 전 기능 공통 규칙.

커밋 뒤에 검증하면 직렬화가 실패했을 때 데이터는 이미 확정됐는데 클라이언트는 500 을
받는다(재시도하면 중복 생성). 그래서 규칙은 하나다::

    obj = await service.<use_case>(...)
    response = XResponse.model_validate(obj)   # 먼저 검증
    await service.commit()                     # 그다음 확정
    return response

여기서는 각 뷰 모듈이 참조하는 응답 DTO 를 ``model_validate`` 가 실패하는 클래스로
바꿔 끼우고 **500 · 커밋 0회 · DB 변화 없음** 을 확인한다. 쓰기 핸들러를 추가하면
``CASES`` 에 한 줄을 더한다.

``POST /api/v1/reports/sales/daily/snapshots`` 는 응답 DTO 를 Service 가 커밋 전에 만들어
돌려주므로(뷰에는 ``model_validate`` 호출이 없다) 이 교체 방식의 대상이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from main import app

import_all_models()


@dataclass(frozen=True)
class Case:
    id: str
    module: str  # 뷰 모듈 import 경로
    dto: str  # 뷰 모듈 안의 응답 DTO 이름
    table: str
    create_path: str
    create_body: dict[str, Any]
    update_path: str | None = None  # "{id}" 를 생성 결과 id 로 치환
    update_body: dict[str, Any] = field(default_factory=dict)


_BLOG = "app.features.blog.api.routers.v1.blog"
_REPLY = "app.features.reply.api.routers.v1.reply"
_SNS = "app.features.sns.api.routers.v1.sns"
_USER = "app.features.user.api.routers.v1.user"
_CATALOG = "app.features.catalog.api.routers.v1.products"
_AUTH = "app.features.auth.api.routers.v1.auth"

_BASE: list[Case] = [
    Case(
        "blog",
        _BLOG,
        "PostResponse",
        "blog_posts",
        "/api/v1/blog/posts",
        {"title": "t", "content": "c", "author": "kim"},
        "/api/v1/blog/posts/{id}",
        {"title": "changed"},
    ),
    Case(
        "reply",
        _REPLY,
        "ReplyResponse",
        "replies",
        "/api/v1/reply/replies",
        {"content": "c", "author": "lee", "post_id": "p1"},
        "/api/v1/reply/replies/{id}",
        {"content": "changed"},
    ),
    Case(
        "sns",
        _SNS,
        "SnsPostResponse",
        "sns_posts",
        "/api/v1/sns/posts",
        {"content": "c", "author": "park"},
        "/api/v1/sns/posts/{id}",
        {"content": "changed"},
    ),
    Case(
        "user",
        _USER,
        "UserResponse",
        "users",
        "/api/v1/user/users",
        {"username": "alice", "email": "alice@example.com"},
        "/api/v1/user/users/{id}",
        {"is_active": False},
    ),
    Case(
        "catalog",
        _CATALOG,
        "ProductResponse",
        "catalog_products",
        "/api/v1/catalog/products",
        {"name": "keyboard", "price": "129.00"},
        "/api/v1/catalog/products/{id}",
        {"price": "119.00"},
    ),
    Case(
        "auth",
        _AUTH,
        "AuthUserResponse",
        "users",
        "/api/v1/auth/register",
        {"username": "bob", "email": "bob@example.com", "password": "password123"},
    ),
]

# (case, "create" | "update") — auth 는 생성(회원가입)만 있다.
CASES = [pytest.param(c, "create", id=f"{c.id}-create") for c in _BASE] + [
    pytest.param(c, "update", id=f"{c.id}-update") for c in _BASE if c.update_path
]


class _Boom(RuntimeError):
    pass


def _failing_dto(original: type) -> type:
    class Failing(original):  # type: ignore[misc, valid-type]
        @classmethod
        def model_validate(cls, *args: Any, **kwargs: Any) -> Any:
            raise _Boom("injected response DTO failure")

    return Failing


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
    calls = {"commit": 0}

    async def _session():
        async with maker() as session:
            original = session.commit

            async def _counting_commit(*args: Any, **kwargs: Any) -> None:
                calls["commit"] += 1
                await original(*args, **kwargs)

            session.commit = _counting_commit  # type: ignore[method-assign]
            yield session

    async def snapshot(table: str) -> list[tuple]:
        # table 은 위 CASES 의 테스트 상수다(외부 입력 아님).
        async with engine.connect() as conn:
            rows = await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))
            return [tuple(row) for row in rows]

    app.dependency_overrides[get_writer_db_session] = _session
    app.dependency_overrides[get_read_only_db_session] = _session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, calls, snapshot
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.parametrize(("case", "action"), CASES)
async def test_dto_failure_happens_before_commit(env, monkeypatch, case: Case, action: str):
    client, calls, snapshot = env
    module = __import__(case.module, fromlist=[case.dto])

    if action == "create":
        method, path, body = "POST", case.create_path, case.create_body
    else:
        created = await client.post(case.create_path, json=case.create_body)
        assert created.status_code == 201, created.text
        assert case.update_path is not None
        method, path = "PATCH", case.update_path.format(id=created.json()["id"])
        body = case.update_body

    before = await snapshot(case.table)
    calls["commit"] = 0
    monkeypatch.setattr(module, case.dto, _failing_dto(getattr(module, case.dto)))

    resp = await client.request(method, path, json=body)

    assert resp.status_code == 500, resp.text
    assert calls["commit"] == 0, "응답 DTO 검증 전에 커밋했다 — 저장은 됐는데 클라이언트는 500"
    assert await snapshot(case.table) == before, "실패한 요청이 DB 를 바꿨다"
