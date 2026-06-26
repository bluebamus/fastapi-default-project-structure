from fastapi import APIRouter

from app.core.registry import AppModule


def test_appmodule_router_convention():
    """router_attr 는 <name>_router 컨벤션을 따른다."""
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    assert m.router_attr == "alpha_router"
    assert m.prefix == "/api"


def test_appmodule_load_router_returns_convention_router():
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    router = m.load_router()
    assert isinstance(router, APIRouter)


def test_appmodule_load_router_missing_returns_none():
    """라우터 모듈이 없으면 None(beta 는 router.py 가 없음)."""
    m = AppModule(name="beta", package="tests.core._fakeapps.beta")
    assert m.load_router() is None


def test_appmodule_load_admin_views():
    m = AppModule(name="beta", package="tests.core._fakeapps.beta")
    views = m.load_admin_views()
    assert len(views) == 2


def test_appmodule_load_admin_views_missing_returns_empty():
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    assert m.load_admin_views() == []
