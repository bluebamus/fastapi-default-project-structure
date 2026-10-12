"""로그인한 슈퍼유저에게 등록된 **모든** ModelView 화면이 실제로 그려진다 (admin-login F-005).

sqladmin 0.32 의 ``column_filters`` 는 필터 **객체**(``sqladmin.filters``)를 받는다. 모델 컬럼을 그대로 넘기면
목록 화면이 ``filter_.parameter_name`` 에서 ``AttributeError`` 로 500 이 된다 — 로그인이 없던 시절엔 아무도
목록을 열어 보는 테스트가 없어 드러나지 않았다. 여기서는 뷰마다 목록 화면, 필터마다 그 필터를 건 목록 화면,
그리고 상세 화면 1건을 200 으로 요구한다.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features import admin as admin_module
from app.features.admin import ADMIN_VIEWS
from app.features.user.models.models import User

import_all_models()

PASSWORD = "s3cret-pass-word"


def _filter_params(filter_) -> dict[str, str]:
    """필터 하나를 실제로 걸어 보는 쿼리 파라미터."""
    name = filter_.parameter_name
    if getattr(filter_, "has_operator", False):
        return {name: "1", f"{name}_op": "equals"}
    return {name: "true"}


FILTER_CASES = [
    pytest.param(view, filter_, id=f"{view.identity}-{filter_.parameter_name}")
    for view in ADMIN_VIEWS
    for filter_ in getattr(view, "column_filters", [])
    if hasattr(filter_, "parameter_name")
]


@pytest_asyncio.fixture
async def logged_in(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'views.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user = User(
            username="root",
            email="root@example.com",
            hashed_password=await get_password_hasher().hash(PASSWORD),
            is_superuser=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    app = FastAPI()
    app.state.redis = FakeAsyncRedis()
    backend = admin_module.build_admin_auth_backend(app, session_factory=maker)
    admin = admin_module.create_admin_interface(app, engine, backend)
    admin_module.register_admin_views(admin)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post("/admin/login", data={"username": "root", "password": PASSWORD})
        assert login.status_code == 302
        yield client, user_id
    await app.state.redis.aclose()
    await engine.dispose()


def test_every_view_declares_filters_as_filter_objects():
    """컬럼을 그대로 넣은 정의를 화면을 열기 전에 잡는다."""
    offenders = [
        f"{view.__name__}: {filter_!r}"
        for view in ADMIN_VIEWS
        for filter_ in getattr(view, "column_filters", [])
        if not hasattr(filter_, "parameter_name")
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("view", ADMIN_VIEWS, ids=lambda v: v.identity)
async def test_list_page_renders_for_every_view(logged_in, view):
    client, _ = logged_in
    response = await client.get(f"/admin/{view.identity}/list")
    assert response.status_code == 200, response.text[-500:]


@pytest.mark.parametrize(("view", "filter_"), FILTER_CASES)
async def test_list_page_renders_with_each_filter_applied(logged_in, view, filter_):
    client, _ = logged_in
    response = await client.get(f"/admin/{view.identity}/list", params=_filter_params(filter_))
    assert response.status_code == 200, response.text[-500:]


def test_filter_cases_are_not_vacuous():
    assert len(FILTER_CASES) >= len(ADMIN_VIEWS), "필터 케이스가 너무 적다 — 헛통과 방지"


async def test_detail_page_renders(logged_in):
    client, user_id = logged_in
    response = await client.get(f"/admin/user/details/{user_id}")
    assert response.status_code == 200, response.text[-500:]
    assert "root@example.com" in response.text
