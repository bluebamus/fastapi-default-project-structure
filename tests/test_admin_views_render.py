"""로그인한 슈퍼유저에게 등록된 **모든** ModelView 화면이 실제로 그려진다 (admin-login F-005).

sqladmin 0.32 의 ``column_filters`` 는 필터 **객체**(``sqladmin.filters``)를 받는다. 모델 컬럼을 그대로 넘기면
목록 화면이 ``filter_.parameter_name`` 에서 ``AttributeError`` 로 500 이 된다 — 로그인이 없던 시절엔 아무도
목록을 열어 보는 테스트가 없어 드러나지 않았다. 여기서는 뷰마다 목록 화면, 필터마다 그 필터를 건 목록 화면,
그리고 상세 화면 1건을 200 으로 요구한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.admin_filters import LocalDateFilter
from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features import admin as admin_module
from app.features.admin import ADMIN_VIEWS
from app.features.user.models.models import User
from tests.admin_csrf import admin_login

import_all_models()

PASSWORD = "s3cret-pass-word"


def _filter_params(filter_) -> dict[str, str]:
    """필터 하나를 실제로 걸어 보는 쿼리 파라미터."""
    name = filter_.parameter_name
    if isinstance(filter_, LocalDateFilter):
        return {name: "2026-10-19", f"{name}_op": "on"}
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
async def views_maker(tmp_path):
    """SQLite 파일 DB 의 세션 팩토리(로그인 사용자를 만들고 기간 필터 테스트가 행을 넣는다)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'views.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def logged_in(views_maker):
    maker = views_maker
    engine = maker.kw["bind"]
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
        login = await admin_login(client, "root", PASSWORD)
        assert login.status_code == 302
        yield client, user_id
    await app.state.redis.aclose()


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


# =============================================================================
# created_at 날짜 필터 (security-ops-hardening ADR-005)
# =============================================================================
DATE_FILTER_VIEWS = [
    view
    for view in ADMIN_VIEWS
    if any(isinstance(f, LocalDateFilter) for f in getattr(view, "column_filters", []))
]


def test_every_view_with_created_at_has_the_date_filter():
    missing = [
        view.__name__
        for view in ADMIN_VIEWS
        if hasattr(view.model, "created_at") and view not in DATE_FILTER_VIEWS
    ]
    assert not missing, f"created_at 날짜 필터가 없는 뷰: {missing}"


@pytest.mark.parametrize("view", DATE_FILTER_VIEWS, ids=lambda v: v.identity)
@pytest.mark.parametrize(
    "params",
    [
        {"created_at": "2026-13-45", "created_at_op": "on"},
        {"created_at": "not-a-date", "created_at_op": "before"},
        {"created_at": "9999-12-31", "created_at_op": "on"},
        {"created_at": "2026-10-19", "created_at_op": "unknown"},
    ],
    ids=["bad-month", "garbage", "overflow", "unknown-op"],
)
async def test_bad_date_filter_input_is_ignored_not_500(logged_in, view, params):
    client, _ = logged_in
    response = await client.get(f"/admin/{view.identity}/list", params=params)
    assert response.status_code == 200, response.text[-500:]


async def test_date_filter_narrows_the_list_and_renders_quick_ranges(logged_in):
    """user 목록 — 오늘 만든 root 는 '오늘 이전'에서 빠지고 '오늘'에서는 보인다."""
    client, _ = logged_in
    today = LocalDateFilter(None, parameter_name="created_at").quick_ranges()[0][2]

    shown = await client.get(
        "/admin/user/list", params={"created_at": today, "created_at_op": "on"}
    )
    hidden = await client.get(
        "/admin/user/list", params={"created_at": today, "created_at_op": "before"}
    )

    assert "root@example.com" in shown.text
    assert "root@example.com" not in hidden.text
    assert 'type="date"' in shown.text and "최근 7일" in shown.text


# =============================================================================
# 기간 필터 (admin-session-hardening ADR-005) — created_at 이 있는 모든 뷰
# =============================================================================
def _seed_values(model, created_at: datetime) -> dict:
    """NOT NULL·기본값 없는 컬럼을 타입별 아무 값으로 채운다(SQLite 는 FK 를 강제하지 않는다)."""
    values: dict = {"created_at": created_at}
    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        if column.server_default is not None or column.primary_key:
            continue
        python_type = column.type.python_type
        if python_type is bool:
            values[column.key] = True
        elif python_type in (int, float, Decimal):
            values[column.key] = 1
        elif python_type is str:
            values[column.key] = f"x{uuid.uuid4().hex[:8]}"
        else:
            raise AssertionError(
                f"{model.__name__}.{column.key}: 시드 값 규칙이 없다 ({python_type})"
            )
    return values


@pytest.mark.parametrize("view", DATE_FILTER_VIEWS, ids=lambda v: v.identity)
async def test_range_filter_narrows_every_created_at_view(logged_in, views_maker, view):
    client, _ = logged_in
    model = view.model
    old_at = datetime(2020, 1, 15, 3, 0, tzinfo=UTC)  # 2020-01-15 12:00 KST
    async with views_maker() as session:
        old = model(**_seed_values(model, old_at))
        new = model(**_seed_values(model, datetime(2021, 6, 1, 3, 0, tzinfo=UTC)))
        session.add_all([old, new])
        await session.commit()
        old_pk, new_pk = str(old.id), str(new.id)

    def listed(response) -> set[str]:
        assert response.status_code == 200, response.text[-500:]
        return {pk for pk in (old_pk, new_pk) if f"/details/{pk}" in response.text}

    async def query(value: str) -> set[str]:
        params = {"created_at": value, "created_at_op": "between"}
        return listed(await client.get(f"/admin/{view.identity}/list", params=params))

    assert await query("2020-01-15~2020-01-15") == {old_pk}  # 양 끝 포함, 하루
    assert await query("2020-01-01~2021-12-31") == {old_pk, new_pk}
    assert await query("2021-01-01~") == {new_pk}  # 시작일만 — 이후
    assert await query("~2020-12-31") == {old_pk}  # 종료일만 — 그날까지
    assert await query("2021-12-31~2020-01-01") == {old_pk, new_pk}  # 역순 — 미적용
    assert await query("2020-01-xx~2020-02-01") == {old_pk, new_pk}  # 형식 오류 — 미적용


async def test_range_filter_form_renders_and_keeps_the_current_range(logged_in):
    client, _ = logged_in
    response = await client.get(
        "/admin/user/list",
        params={"created_at": "2020-01-01~2020-01-31", "created_at_op": "between"},
    )
    html = response.text
    assert response.status_code == 200
    assert 'name="created_at_op" value="between"' in html
    assert 'data-range="start"' in html and 'value="2020-01-01"' in html
    assert 'data-range="end"' in html and 'value="2020-01-31"' in html
    assert "기간(양 끝 포함)" in html
