from fastapi import APIRouter, FastAPI
from app.core.registry import AppConfig, AppRegistry

class _Cfg(AppConfig):
    name = "alpha"
    def router(self):
        r = APIRouter()
        @r.get("/ping")
        def ping(): return {"ok": True}
        return r

def test_install_routers_and_celery_packages():
    reg = AppRegistry()
    reg._apps = [_Cfg()]                      # inject directly
    app = FastAPI()
    count = reg.install_routers(app)
    assert count == 1
    paths = {route.path for route in app.routes}
    assert "/api/ping" in paths
    assert reg.celery_packages() == [ _Cfg().package ]


def test_import_models_admin_and_beat():
    # --- import_models: package with no .models submodule must not raise ---
    class _NoCfg(AppConfig):
        name = "nomodels"
        # override package to point at tests.core which has no models.py
        @property
        def package(self) -> str:
            return "tests.core"

    reg = AppRegistry()
    reg._apps = [_NoCfg()]
    result = reg.import_models()   # must return None without raising
    assert result is None

    # --- install_admin: stub admin collects views ---
    class _AdminCfg(AppConfig):
        name = "adminapp"
        def admin_views(self):
            class ViewA: pass
            class ViewB: pass
            return [ViewA, ViewB]

    class _StubAdmin:
        def __init__(self):
            self.collected = []
        def add_view(self, view):
            self.collected.append(view)

    stub = _StubAdmin()
    reg2 = AppRegistry()
    reg2._apps = [_AdminCfg()]
    count = reg2.install_admin(stub)
    assert count == 2
    assert len(stub.collected) == 2

    # --- merged_beat_schedule: two configs merge without collision ---
    class _BeatA(AppConfig):
        name = "beata"
        def beat_schedule(self):
            return {"a": 1}

    class _BeatB(AppConfig):
        name = "beatb"
        def beat_schedule(self):
            return {"b": 2}

    reg3 = AppRegistry()
    reg3._apps = [_BeatA(), _BeatB()]
    merged = reg3.merged_beat_schedule()
    assert merged == {"a": 1, "b": 2}
