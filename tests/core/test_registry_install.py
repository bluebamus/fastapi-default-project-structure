from fastapi import FastAPI

from app.core.registry import AppRegistry


def test_install_routers_mounts_by_convention():
    """alpha 는 alpha_router(컨벤션)를 가지므로 /api 에 마운트되고, beta 는 건너뛴다."""
    reg = AppRegistry()
    reg.discover(package="tests.core._fakeapps")

    app = FastAPI()
    count = reg.install_routers(app)
    assert count == 1                          # alpha 만 라우터 보유
    paths = {route.path for route in app.routes}
    assert "/api/ping" in paths


def test_import_models_skips_apps_without_models():
    """models 패키지가 없어도 예외 없이 통과한다."""
    reg = AppRegistry()
    reg.discover(package="tests.core._fakeapps")
    assert reg.import_models() is None         # 예외 없이 None 반환


def test_install_admin_collects_admin_views():
    """beta 의 admin.py admin_views 가 SQLAdmin 에 등록된다."""

    class _StubAdmin:
        def __init__(self):
            self.collected = []

        def add_view(self, view):
            self.collected.append(view)

    reg = AppRegistry()
    reg.discover(package="tests.core._fakeapps")
    stub = _StubAdmin()
    count = reg.install_admin(stub)
    assert count == 2                          # beta 가 ViewA, ViewB 제공
    assert len(stub.collected) == 2
