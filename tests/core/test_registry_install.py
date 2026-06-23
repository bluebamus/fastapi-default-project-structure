from fastapi import APIRouter, FastAPI
from app.core.registry import AppConfig, AppRegistry

class _Cfg(AppConfig):
    name = "alpha"
    def router(self):
        r = APIRouter()
        @r.get("/ping")
        def ping(): return {"ok": True}
        return r

def test_install_routers_and_celery_packages(monkeypatch):
    reg = AppRegistry()
    reg._apps = [_Cfg()]                      # inject directly
    app = FastAPI()
    count = reg.install_routers(app)
    assert count == 1
    paths = {route.path for route in app.routes}
    assert "/api/ping" in paths
    assert reg.celery_packages() == [ _Cfg().package ]
