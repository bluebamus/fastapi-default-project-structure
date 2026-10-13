"""``AccessPolicyGuard`` 단위 규칙 (access-policy ADR-001~003).

작은 앱을 그 자리에서 조립해 판정만 본다 — 요청은 보내지 않는다.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette

from app.core.security.access import (
    AccessLevel,
    AccessPolicyError,
    AccessPolicyGuard,
    LoginRequired,
    Public,
    PublicWrite,
    SuperuserRequired,
)
from app.core.security.dependencies import CurrentPrincipal, SuperuserPrincipal

guard = AccessPolicyGuard()


async def _view() -> None:
    return None


def _app(*, docs: bool = False) -> FastAPI:
    if docs:
        return FastAPI()  # /docs·/redoc·/openapi.json 을 FastAPI 가 붙인다
    return FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _levels(app: FastAPI) -> dict[str, set[AccessLevel]]:
    return {label: guard.levels(context.dependant) for label, context in guard.routes(app)}


def test_route_without_declaration_is_a_violation():
    app = _app()
    app.get("/x")(_view)

    assert guard.violations(app) == ["GET /x: 접근 수준 선언 없음"]


def test_two_different_levels_is_a_violation():
    app = _app()
    app.get("/x", dependencies=[Public, LoginRequired])(_view)

    [problem] = guard.violations(app)
    assert problem.startswith("GET /x: 접근 수준을 둘 이상 선언함")


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_public_on_a_write_method_points_to_public_write(method):
    app = _app()
    getattr(app, method)("/x", dependencies=[Public])(_view)

    [problem] = guard.violations(app)
    assert "PublicWrite" in problem


def test_public_write_on_a_safe_method_is_a_violation():
    app = _app()
    app.get("/x", dependencies=[PublicWrite])(_view)

    [problem] = guard.violations(app)
    assert "안전한 메서드에 PublicWrite" in problem


def test_each_level_alone_on_its_methods_passes():
    app = _app()
    app.get("/a", dependencies=[Public])(_view)
    app.post("/b", dependencies=[PublicWrite])(_view)
    app.post("/c", dependencies=[LoginRequired])(_view)
    app.delete("/d", dependencies=[SuperuserRequired])(_view)

    assert guard.violations(app) == []
    assert _levels(app) == {
        "GET /a": {AccessLevel.PUBLIC},
        "POST /b": {AccessLevel.PUBLIC_WRITE},
        "POST /c": {AccessLevel.LOGIN},
        "DELETE /d": {AccessLevel.SUPERUSER},
    }


def test_principal_arguments_count_as_declarations():
    app = _app()

    @app.post("/login")
    async def login_view(principal: CurrentPrincipal) -> None:
        return None

    @app.post("/super")
    async def super_view(principal: SuperuserPrincipal) -> None:
        return None

    assert guard.violations(app) == []
    assert _levels(app) == {
        "POST /login": {AccessLevel.LOGIN},
        "POST /super": {AccessLevel.SUPERUSER},
    }


def test_superuser_absorbs_login_it_uses_internally():
    app = _app()

    @app.post("/x", dependencies=[LoginRequired])
    async def view(principal: SuperuserPrincipal) -> None:
        return None

    assert guard.violations(app) == []
    assert _levels(app) == {"POST /x": {AccessLevel.SUPERUSER}}


def test_router_level_and_include_level_dependencies_count():
    by_router = APIRouter(dependencies=[SuperuserRequired])
    by_router.get("/a")(_view)
    by_include = APIRouter()
    by_include.get("/b")(_view)
    app = _app()
    app.include_router(by_router)
    app.include_router(by_include, dependencies=[Public])

    assert guard.violations(app) == []
    assert _levels(app) == {"GET /a": {AccessLevel.SUPERUSER}, "GET /b": {AccessLevel.PUBLIC}}


def test_routes_hidden_from_the_schema_are_still_checked():
    app = _app()
    app.get("/hidden", include_in_schema=False)(_view)

    assert guard.violations(app) == ["GET /hidden: 접근 수준 선언 없음"]


def test_framework_docs_routes_and_mounts_are_excluded():
    app = _app(docs=True)
    app.mount("/admin", Starlette())

    assert {route.path for route in app.routes} >= {"/docs", "/redoc", "/openapi.json", "/admin"}
    assert list(guard.routes(app)) == []
    assert guard.violations(app) == []


def test_nested_includes_are_expanded_with_their_full_path():
    inner = APIRouter()
    inner.get("/leaf")(_view)
    middle = APIRouter()
    middle.include_router(inner, prefix="/v1/x")
    app = _app()
    app.include_router(middle, prefix="/api")

    assert guard.violations(app) == ["GET /api/v1/x/leaf: 접근 수준 선언 없음"]


def test_verify_raises_with_every_violation_listed():
    app = _app()
    app.get("/one")(_view)
    app.post("/two", dependencies=[Public])(_view)
    app.get("/three", dependencies=[PublicWrite])(_view)
    app.get("/ok", dependencies=[Public])(_view)

    with pytest.raises(AccessPolicyError) as raised:
        guard.verify(app)

    message = str(raised.value)
    assert isinstance(raised.value, RuntimeError)
    for label in ("GET /one", "POST /two", "GET /three"):
        assert label in message
    assert "/ok" not in message


def test_verify_passes_silently_when_every_route_declares():
    app = _app()
    app.get("/ok", dependencies=[Public])(_view)

    guard.verify(app)
