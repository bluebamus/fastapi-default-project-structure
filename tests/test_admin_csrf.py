"""로그인 이후 관리 화면 CSRF — 생성·수정·삭제·일괄 삭제·로그아웃 (admin-session-hardening ADR-003·004).

``AdminCsrfMiddleware`` 가 ``/admin`` 의 POST·PUT·PATCH·DELETE 전부에서 세션 토큰과 요청 토큰(헤더
``X-CSRF-Token`` 또는 폼 필드 ``csrf_token``)을 대조한다. 화면은 ``base.html`` 덮어쓰기가 meta 토큰과
인라인 스크립트를 싣고, 로그아웃은 POST 전용이다. sqladmin 원본 템플릿이 바뀌면 드리프트 검사가 실패한다.
"""

from __future__ import annotations

import re
from importlib.resources import files

import httpx
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.routing import Route

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security.admin_session import CSRF_HEADER
from app.core.security.dependencies import get_password_hasher
from app.features import admin as admin_module
from app.features.admin import ADMIN_TEMPLATES_DIR, ADMIN_VIEWS
from app.features.auth import admin_backend
from app.features.catalog.models.models import Product
from app.features.user.models.models import User
from tests.admin_csrf import (
    CSRF_META,
    admin_login,
    admin_page_token,
    admin_session_data,
)

import_all_models()

PASSWORD = "s3cret-pass-word"
SQLADMIN_TEMPLATES = files("sqladmin") / "templates" / "sqladmin"


# =============================================================================
# fixtures
# =============================================================================
@pytest_asyncio.fixture
async def maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'csrf.db'}", poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(
            User(
                username="root",
                email="root@example.com",
                hashed_password=await get_password_hasher().hash(PASSWORD),
                is_superuser=True,
            )
        )
        await session.commit()
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis()
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
        assert (await admin_login(http, "root", PASSWORD)).status_code == 302
        yield http


async def _add_products(maker, *names: str) -> list[str]:
    async with maker() as session:
        products = [Product(name=name, price="1.00") for name in names]
        session.add_all(products)
        await session.commit()
        return [p.id for p in products]


async def _product_names(maker) -> set[str]:
    async with maker() as session:
        return set((await session.execute(select(Product.name))).scalars())


async def _product_count(maker) -> int:
    async with maker() as session:
        return (await session.execute(select(func.count()).select_from(Product))).scalar_one()


# 토큰을 고르는 방법: 없음·틀림·맞음 — 맞음은 폼 필드와 헤더 두 경로.
TOKEN_CASES = [
    pytest.param(None, None, id="missing"),
    pytest.param("form", "wrong", id="wrong-form"),
    pytest.param("header", "wrong", id="wrong-header"),
    pytest.param("form", "right", id="right-form"),
    pytest.param("header", "right", id="right-header"),
]


def _attach(where: str | None, token: str | None, data: dict | None = None):
    """(data, headers) — 토큰을 폼 또는 헤더에 싣는다."""
    data = dict(data or {})
    headers: dict[str, str] = {}
    if where == "form":
        data["csrf_token"] = token
    elif where == "header":
        headers[CSRF_HEADER] = token
    return data, headers


async def _token(client, kind: str | None) -> str | None:
    if kind is None:
        return None
    real = await admin_page_token(client)
    return real if kind == "right" else "wrong-token"


def _assert_rejected(response: httpx.Response) -> None:
    assert response.status_code == 403
    assert admin_backend.CSRF_FAILED_MESSAGE in response.text
    assert 'name="password"' not in response.text  # 로그인 화면이 아니라 관리 화면 오류


# =============================================================================
# 생성·수정·삭제·일괄 삭제
# =============================================================================
@pytest.mark.parametrize(("where", "kind"), TOKEN_CASES)
async def test_create(client, maker, where, kind):
    token = await _token(client, kind)
    data, headers = _attach(where, token, {"name": "new", "price": "9.99", "is_active": "y"})

    response = await client.post("/admin/product/create", data=data, headers=headers)

    if kind == "right":
        assert response.status_code == 302
        assert await _product_names(maker) == {"new"}
    else:
        _assert_rejected(response)
        assert await _product_count(maker) == 0


@pytest.mark.parametrize(("where", "kind"), TOKEN_CASES)
async def test_edit(client, maker, where, kind):
    [pk] = await _add_products(maker, "old")
    token = await _token(client, kind)
    data, headers = _attach(where, token, {"name": "renamed", "price": "1.00", "is_active": "y"})

    response = await client.post(f"/admin/product/edit/{pk}", data=data, headers=headers)

    if kind == "right":
        assert response.status_code == 302
        assert await _product_names(maker) == {"renamed"}
    else:
        _assert_rejected(response)
        assert await _product_names(maker) == {"old"}


@pytest.mark.parametrize("bulk", [False, True], ids=["single", "bulk"])
@pytest.mark.parametrize("kind", [None, "wrong", "right"], ids=["missing", "wrong", "right"])
async def test_delete_and_bulk_delete(client, maker, kind, bulk):
    """삭제 모달·목록 일괄 삭제는 JS 가 DELETE 를 보낸다 — 헤더로 토큰을 싣는다."""
    pks = await _add_products(maker, "a", "b", "c")
    targets = pks[:2] if bulk else pks[:1]
    token = await _token(client, kind)
    headers = {CSRF_HEADER: token} if token else {}

    response = await client.delete(
        f"/admin/product/delete?pks={','.join(targets)}", headers=headers
    )

    if kind == "right":
        assert response.status_code == 200
        assert await _product_count(maker) == 3 - len(targets)
    else:
        _assert_rejected(response)
        assert await _product_count(maker) == 3


async def test_token_of_another_session_is_rejected(app, client, maker):
    async with _browser(app) as other:
        assert (await admin_login(other, "root", PASSWORD)).status_code == 302
        other_token = await admin_page_token(other)
    assert other_token != await admin_page_token(client)

    response = await client.post(
        "/admin/product/create",
        data={"name": "x", "price": "1.00", "csrf_token": other_token},
    )

    _assert_rejected(response)
    assert await _product_count(maker) == 0


async def test_unsafe_request_without_any_session_is_rejected(app, maker):
    async with _browser(app) as anonymous:
        response = await anonymous.post(
            "/admin/product/create", data={"name": "x", "price": "1", "csrf_token": "x"}
        )
    assert response.status_code == 403
    assert await _product_count(maker) == 0


async def test_get_views_need_no_token(client, maker):
    [pk] = await _add_products(maker, "a")
    for path in (
        "/admin/",
        "/admin/product/list",
        f"/admin/product/details/{pk}",
        f"/admin/product/edit/{pk}",
        "/admin/product/create",
        "/admin/product/export/csv",
    ):
        assert (await client.get(path)).status_code == 200, path


async def test_multipart_form_body_still_reaches_sqladmin(client, maker):
    """미들웨어가 본문을 읽은 뒤에도 sqladmin 이 같은 폼을 다시 읽는다(본문 재생)."""
    token = await admin_page_token(client)
    response = await client.post(
        "/admin/product/create",
        data={"name": "multi", "price": "2.50", "is_active": "y", "csrf_token": token},
        files={"unused": ("a.txt", b"x", "text/plain")},
    )
    assert response.status_code == 302
    assert await _product_names(maker) == {"multi"}


# =============================================================================
# 로그아웃 — POST + 토큰
# =============================================================================
@pytest.mark.parametrize(("where", "kind"), TOKEN_CASES)
async def test_logout(client, redis, where, kind):
    token = await _token(client, kind)
    data, headers = _attach(where, token)

    response = await client.post("/admin/logout", data=data, headers=headers)

    if kind == "right":
        assert response.status_code == 302
        assert await admin_session_data(client, redis) == {}
        assert (await client.get("/admin/")).status_code == 302
    else:
        _assert_rejected(response)
        assert "user_id" in await admin_session_data(client, redis)


async def test_get_logout_does_not_log_out(client, redis):
    """다른 사이트의 ``<img src=/admin/logout>`` 로는 로그아웃되지 않는다."""
    response = await client.get("/admin/logout")

    assert response.status_code == 405
    assert "user_id" in await admin_session_data(client, redis)
    assert (await client.get("/admin/")).status_code == 200


def test_logout_route_is_post_only(app):
    admin_app = next(r.app for r in app.routes if getattr(r, "name", None) == "admin")
    [logout] = [r for r in admin_app.router.routes if getattr(r, "name", None) == "logout"]
    assert isinstance(logout, Route)
    assert logout.methods == {"POST"}


# =============================================================================
# 화면 — meta 토큰·스크립트
# =============================================================================
async def test_admin_pages_carry_the_session_token_and_script(client, redis):
    html = (await client.get("/admin/product/list")).text

    meta = CSRF_META.search(html)
    assert meta and meta.group(1) == (await admin_session_data(client, redis))["csrf_token"]
    assert "X-CSRF-Token" in html  # fetch/XHR 헤더
    assert "addEventListener('submit'" in html  # POST 폼 hidden 필드
    assert '"http://testserver/admin/logout"' in html  # 로그아웃 링크 → POST 폼
    # 원본 base 의 내용(스크립트·CSS)은 그대로다.
    assert "js/main.js" in html and "css/main.css" in html


async def test_rendering_the_page_twice_keeps_the_token(client):
    assert await admin_page_token(client) == await admin_page_token(client, "/admin/product/list")


# =============================================================================
# sqladmin 원본과의 드리프트 — 올릴 때 덮어쓰기가 어긋나면 여기서 실패한다
# =============================================================================
def test_override_extends_the_original_base_and_only_touches_two_blocks():
    override = (ADMIN_TEMPLATES_DIR / "sqladmin" / "base.html").read_text(encoding="utf-8")
    assert override.startswith('{% extends "sqladmin_original/base.html" %}')
    blocks = re.findall(r"{%\s*block\s+(\w+)\s*%}", override)
    assert blocks == ["head_meta", "tail"]
    assert override.count("{{ super() }}") == 2


def test_original_templates_still_have_what_the_override_relies_on():
    base = (SQLADMIN_TEMPLATES / "base.html").read_text(encoding="utf-8")
    layout = (SQLADMIN_TEMPLATES / "layout.html").read_text(encoding="utf-8")
    for block in ("head_meta", "tail", "tail_js"):
        assert f"{{% block {block} %}}" in base, block
    assert '{% extends "sqladmin/base.html" %}' in layout
    assert "href=\"{{ request.url_for('admin:logout') }}\"" in layout
    # 원본이 sqladmin_original/ 접두사로 여전히 찾아진다.
    assert any(
        loader.__class__.__name__ == "PrefixLoader"
        for loader in admin_module.Admin(FastAPI(), None).templates.env.loader.loaders  # type: ignore[arg-type]
    )


def test_original_logout_route_is_still_get_only():
    """sqladmin 이 로그아웃을 POST 로 바꾸면 ``_logout_post_only`` 는 필요 없어진다 — 그때 다시 본다."""
    admin = admin_module.Admin(FastAPI(), None)  # type: ignore[arg-type]
    [logout] = [r for r in admin.admin.router.routes if getattr(r, "name", None) == "logout"]
    assert logout.methods == {"GET", "HEAD"}


def test_main_js_still_sends_state_changes_the_script_covers():
    """sqladmin 의 상태 변경 요청이 스크립트가 덮는 경로(폼 submit·$.ajax·fetch)로만 나간다."""
    main_js = (files("sqladmin") / "statics" / "js" / "main.js").read_text(encoding="utf-8")
    assert "method: 'DELETE'" in main_js  # 삭제 모달 → $.ajax(XHR)
    assert "fetch(frm.attr('action')" in main_js  # import → fetch
    # 사용자 정의 action 은 GET 링크(window.location)다 — 등록된 것이 없어야 한다(아래 테스트).
    assert "window.location.href = $(this).attr('data-url')" in main_js


def test_no_view_registers_a_custom_get_action():
    """sqladmin 의 ``@action`` 은 GET 으로 상태를 바꾼다 — CSRF 미들웨어가 보지 않으므로 쓰지 않는다."""
    offenders = [
        f"{view.__name__}.{name}"
        for view in ADMIN_VIEWS
        for name in dir(view)
        if hasattr(getattr(view, name, None), "_action")
    ]
    assert offenders == []


# =============================================================================
# 버퍼링 상한 — 본문 10 MiB 초과 413, 필드 1 MiB 초과 400 (integration-e2e ADR-015)
# =============================================================================
MIB = 1024 * 1024
FORM = "application/x-www-form-urlencoded"


async def _through_csrf(body: bytes, content_type: str = FORM, content_length: str | None = "auto"):
    """``AdminCsrfMiddleware`` 하나에 요청을 흘려 (상태, 다운스트림 도달 여부, receive 호출 수)를 돌려준다.

    본문은 64 KiB 조각으로 나눠 보낸다. ``content_length`` 가 ``None`` 이면 헤더가 없고, 문자열이면 그 값을 싣는다
    (``"auto"`` 는 실제 길이 — 거짓 값을 실어 누적 판정을 본다).
    """
    from starlette.responses import PlainTextResponse

    from app.core.security.admin_session import AdminCsrfMiddleware

    reached: list[bool] = []

    async def downstream(scope, receive, send):
        reached.append(True)
        await PlainTextResponse("ok")(scope, receive, send)

    async def reject(request):
        return PlainTextResponse("csrf", status_code=403)

    chunks = [body[i : i + 65536] for i in range(0, len(body), 65536)] or [b""]
    messages = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]
    reads = 0

    async def receive():
        nonlocal reads
        reads += 1
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    headers = [(b"content-type", content_type.encode())]
    if content_length is not None:
        value = str(len(body)) if content_length == "auto" else content_length
        headers.append((b"content-length", value.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/admin/login",
        "query_string": b"",
        "headers": headers,
        "session": {"csrf_token": "tok"},
        "app": object(),  # 실제 요청처럼 — Starlette 가 폼 오류를 HTTPException(400)으로 낸다
    }
    await AdminCsrfMiddleware(downstream, reject=reject)(scope, receive, send)
    return sent[0]["status"], bool(reached), reads


async def test_declared_body_over_10_mib_is_413_before_reading():
    status, reached, reads = await _through_csrf(
        b"csrf_token=tok", content_length=str(10 * MIB + 1)
    )
    assert (status, reached, reads) == (413, False, 0)


@pytest.mark.parametrize("content_length", [None, "16"], ids=["no-header", "understated"])
async def test_body_over_10_mib_without_an_honest_length_is_413_while_reading(content_length):
    body = b"csrf_token=tok&pad=" + b"x" * (10 * MIB)
    status, reached, _ = await _through_csrf(body, content_length=content_length)
    assert (status, reached) == (413, False)


async def test_body_of_exactly_10_mib_is_not_capped():
    field = b"&f=" + b"x" * (MIB - 16)
    body = (b"csrf_token=tok" + field * 11)[: 10 * MIB]
    status, reached, _ = await _through_csrf(body)
    assert (status, reached) == (200, True)


def _multipart(fields: dict[str, bytes]) -> tuple[bytes, str]:
    boundary = "csrfboundary"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        + value
        + b"\r\n"
        for name, value in fields.items()
    ]
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.mark.parametrize("kind", ["urlencoded", "multipart"])
async def test_single_field_over_1_mib_is_400_not_a_csrf_rejection(kind):
    big = b"x" * (MIB + 1)
    if kind == "urlencoded":
        body, content_type = b"csrf_token=tok&big=" + big, FORM
    else:
        body, content_type = _multipart({"csrf_token": b"tok", "big": big})
    status, reached, _ = await _through_csrf(body, content_type)
    assert (status, reached) == (400, False)


async def test_field_of_exactly_1_mib_passes():
    # Starlette 는 이름과 값을 합쳐 센다 — 이름 3바이트 + 값 = 정확히 1 MiB
    status, reached, _ = await _through_csrf(b"csrf_token=tok&big=" + b"x" * (MIB - 3))
    assert (status, reached) == (200, True)
