# Domains + Registry Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the project to a Django-style auto-discovered architecture where each domain app self-registers (router, models, admin, Celery tasks) so adding an app requires **zero** central-file edits, and stand up the currently-missing Celery and Alembic foundations.

**Architecture:** Apps move under `app/domains/<name>/` and each declares an `AppConfig` in `config.py`. A central `app/core/registry.py` recursively discovers those configs at boot and wires routers, models (for runtime + Alembic), admin views, and Celery task packages. Infrastructure consolidates under `app/core/` (with `core/db`, `core/celery`); pure utilities move to `app/shared/`. The UnitOfWork base becomes declarative (a `repositories` map + a `background` flag) to remove the per-domain 2× duplication.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async (aiomysql), Pydantic v2 / pydantic-settings, Celery 5 (Redis broker/backend), Alembic, SQLAdmin, pytest + pytest-asyncio + aiosqlite.

## Global Constraints

- Python `>=3.12`. Keep dependency version floors already pinned in `pyproject.toml`.
- **Every phase must leave the app bootable and the test suite green.** Phases 1–2 keep old import paths working via re-export shims; shims are deleted only in Phase 8.
- Folder taxonomy is fixed: `app/domains/` (apps), `app/core/` (framework infra apps depend on), `app/shared/` (pure utils, no inward deps). Dependency direction `domains → core → shared` only.
- Naming standard: app config = `config.py`; tasks = `worker/tasks.py`; admin = `admin.py`; exceptions = `exceptions.py`; app deps = `dependencies.py`.
- Auto-discovery is `config.py` (AppConfig subclass) **recursive** scan under `app/domains`.
- Celery = single app in `app/core/celery/app.py` + `autodiscover_tasks(..., related_name="worker.tasks")`.
- Conventional commits. Commit at the end of every task.
- Run tests with: `python -m pytest -q` (async mode is configured in `pyproject.toml`).

---

## File Structure (target)

```
app/
├── core/
│   ├── registry.py          # AppConfig + AppRegistry (NEW)
│   ├── bootstrap.py         # create_app() factory (NEW)
│   ├── db/                  # ← moved from app/database
│   │   ├── session.py
│   │   └── unit_of_work.py
│   ├── celery/              # NEW
│   │   ├── app.py
│   │   └── task.py          # DBTask base (async bridge)
│   ├── models/ repositories/ services/ exceptions/ middlewares/
├── shared/                  # ← moved from app/utils
│   ├── logging/ pagination/
├── domains/                 # ← moved from app/home, app/user, ...
│   └── home/
│       ├── config.py        # HomeConfig(AppConfig) (NEW)
│       ├── api/ models/ repositories/ services/ schemas/
│       ├── unit_of_work.py  # single class, declarative
│       ├── worker/tasks.py
│       ├── admin.py exceptions.py dependencies.py
│       └── tests/
├── main.py                  # thin: app = create_app()
└── migrations/              # Alembic (NEW)
scripts/new_app.py           # scaffolding generator (NEW)
```

---

## Phase 0 — Registry foundation (no behavior change)

### Task 0.1: `AppConfig` base class

**Files:**
- Create: `app/core/registry.py`
- Test: `tests/core/test_registry_appconfig.py`

**Interfaces:**
- Produces: `class AppConfig` with class attrs `name: str`, `category: str = "domain"`, `prefix: str = "/api"`, `enabled: bool = True`, `order: int = 100`; instance hook methods `router() -> APIRouter | None` (default `None`), `admin_views() -> list[type]` (default `[]`), `beat_schedule() -> dict` (default `{}`). `package` property returns the module package the subclass is defined in (e.g. `app.domains.home`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_registry_appconfig.py
from app.core.registry import AppConfig

class DummyConfig(AppConfig):
    name = "dummy"

def test_appconfig_defaults():
    cfg = DummyConfig()
    assert cfg.name == "dummy"
    assert cfg.category == "domain"
    assert cfg.prefix == "/api"
    assert cfg.enabled is True
    assert cfg.order == 100
    assert cfg.router() is None
    assert cfg.admin_views() == []
    assert cfg.beat_schedule() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_registry_appconfig.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/core/registry.py
"""앱 자동발견 레지스트리.

각 도메인 앱은 이 모듈의 AppConfig를 상속한 클래스를 config.py에 선언한다.
AppRegistry가 부팅 시 app/domains 하위를 재귀 스캔하여 발견한 AppConfig로
라우터·모델·Admin·Celery 패키지를 자동 연결한다.
"""
from __future__ import annotations

from fastapi import APIRouter


class AppConfig:
    """도메인 앱의 자기 선언. 하위 클래스가 클래스 속성/훅을 오버라이드한다."""

    name: str = ""
    category: str = "domain"   # 사용자 정의상 거의 항상 "domain"
    prefix: str = "/api"
    enabled: bool = True
    order: int = 100           # 낮을수록 먼저 로드(앱 간 의존 순서 제어용)

    @property
    def package(self) -> str:
        """이 설정이 정의된 패키지 경로 (예: app.domains.home)."""
        module = type(self).__module__          # app.domains.home.config
        return module.rsplit(".", 1)[0]         # app.domains.home

    def router(self) -> APIRouter | None:
        """앱의 통합 APIRouter. 없으면 None."""
        return None

    def admin_views(self) -> list[type]:
        """SQLAdmin ModelView 클래스 목록."""
        return []

    def beat_schedule(self) -> dict:
        """Celery beat 스케줄 조각. 레지스트리가 병합한다."""
        return {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_registry_appconfig.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/registry.py tests/core/test_registry_appconfig.py
git commit -m "feat(core): add AppConfig base for app self-registration"
```

### Task 0.2: `AppRegistry.discover()` recursive scan

**Files:**
- Modify: `app/core/registry.py`
- Test: `tests/core/test_registry_discover.py`
- Test fixture package: `tests/core/_fakeapps/alpha/config.py`, `tests/core/_fakeapps/beta/sub/config.py` (+ `__init__.py` in each dir)

**Interfaces:**
- Produces: `class AppRegistry` with `discover(package: str = "app.domains") -> list[AppConfig]` (recursive, instantiates each `AppConfig` subclass found in any `config.py`, sorts by `(order, name)`, filters `enabled`), and property `enabled_apps -> list[AppConfig]` (cached result of last discover). Raises `RuntimeError` on duplicate `name`.

- [ ] **Step 1: Create fake app fixtures**

```python
# tests/core/_fakeapps/__init__.py   (empty file)
# tests/core/_fakeapps/alpha/__init__.py   (empty file)
# tests/core/_fakeapps/alpha/config.py
from app.core.registry import AppConfig
class AlphaConfig(AppConfig):
    name = "alpha"
    order = 10
```

```python
# tests/core/_fakeapps/beta/__init__.py        (empty file)
# tests/core/_fakeapps/beta/sub/__init__.py    (empty file)
# tests/core/_fakeapps/beta/sub/config.py
from app.core.registry import AppConfig
class BetaConfig(AppConfig):
    name = "beta"
    order = 20
```

- [ ] **Step 2: Write the failing test**

```python
# tests/core/test_registry_discover.py
from app.core.registry import AppRegistry

def test_discover_is_recursive_and_ordered():
    reg = AppRegistry()
    apps = reg.discover(package="tests.core._fakeapps")
    names = [a.name for a in apps]
    assert names == ["alpha", "beta"]          # sorted by order, recursion found beta/sub
    assert reg.enabled_apps == apps
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/core/test_registry_discover.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'AppRegistry'`

- [ ] **Step 4: Implement `AppRegistry.discover`**

```python
# app/core/registry.py  (append)
import importlib
import pkgutil
import inspect


class AppRegistry:
    def __init__(self) -> None:
        self._apps: list[AppConfig] = []

    @property
    def enabled_apps(self) -> list[AppConfig]:
        return self._apps

    def discover(self, package: str = "app.domains") -> list[AppConfig]:
        root = importlib.import_module(package)
        found: dict[str, AppConfig] = {}

        for mod_info in pkgutil.walk_packages(root.__path__, prefix=f"{package}."):
            if not mod_info.name.endswith(".config"):
                continue
            module = importlib.import_module(mod_info.name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, AppConfig) and obj is not AppConfig and obj.__module__ == mod_info.name:
                    cfg = obj()
                    if not cfg.enabled:
                        continue
                    if cfg.name in found:
                        raise RuntimeError(f"중복된 앱 이름: {cfg.name}")
                    found[cfg.name] = cfg

        self._apps = sorted(found.values(), key=lambda c: (c.order, c.name))
        return self._apps
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/core/test_registry_discover.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/registry.py tests/core/test_registry_discover.py tests/core/_fakeapps
git commit -m "feat(core): add AppRegistry recursive config discovery"
```

### Task 0.3: Registry install helpers (routers / models / admin / celery)

**Files:**
- Modify: `app/core/registry.py`
- Test: `tests/core/test_registry_install.py`

**Interfaces:**
- Produces on `AppRegistry`: `install_routers(app) -> int` (includes each enabled router with its `prefix`, returns count), `import_models() -> None` (imports `<pkg>.models` for each app to populate `Base.metadata`; silently skips apps without a `models` submodule), `install_admin(admin) -> int` (adds each `admin_views()` view), `celery_packages() -> list[str]` (returns each app `package`), `merged_beat_schedule() -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_registry_install.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_registry_install.py -v`
Expected: FAIL — `AttributeError: 'AppRegistry' object has no attribute 'install_routers'`

- [ ] **Step 3: Implement helpers**

```python
# app/core/registry.py  (append to AppRegistry)
    def install_routers(self, app) -> int:
        count = 0
        for cfg in self._apps:
            router = cfg.router()
            if router is not None:
                app.include_router(router, prefix=cfg.prefix)
                count += 1
        return count

    def import_models(self) -> None:
        for cfg in self._apps:
            try:
                importlib.import_module(f"{cfg.package}.models")
            except ModuleNotFoundError:
                continue

    def install_admin(self, admin) -> int:
        count = 0
        for cfg in self._apps:
            for view in cfg.admin_views():
                admin.add_view(view)
                count += 1
        return count

    def celery_packages(self) -> list[str]:
        return [cfg.package for cfg in self._apps]

    def merged_beat_schedule(self) -> dict:
        schedule: dict = {}
        for cfg in self._apps:
            schedule.update(cfg.beat_schedule())
        return schedule
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_registry_install.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/registry.py tests/core/test_registry_install.py
git commit -m "feat(core): add registry install helpers for routers/models/admin/celery"
```

---

## Phase 1 — Consolidate infra: `core/db` + `shared` (shims keep old paths)

### Task 1.1: Move `app/database` → `app/core/db` with re-export shim

**Files:**
- Move: `app/database/session.py` → `app/core/db/session.py`; `app/database/unit_of_work.py` → `app/core/db/unit_of_work.py`; `app/database/redis.py` → `app/core/db/redis.py`; `app/database/__init__.py` → `app/core/db/__init__.py`
- Create: `app/database/__init__.py` (shim re-exporting from `app.core.db`)
- Modify: `app/core/db/session.py` import of Base (it imports `from app.core.models.models_base import Base` — unchanged, still valid)

**Interfaces:**
- Produces: `app.core.db.session` (engine, background_engine, AsyncSessionLocal, BackgroundSessionLocal, get_session, get_background_session, create_db_tables, dispose_engine); `app.core.db.unit_of_work` (BaseUnitOfWork, BaseBackgroundUnitOfWork). Old `app.database.*` paths remain importable via shim.

- [ ] **Step 1: Capture green baseline**

Run: `python -m pytest -q`
Expected: PASS (record the count; this is the characterization baseline).

- [ ] **Step 2: Move files with git**

```bash
mkdir -p app/core/db
git mv app/database/session.py app/core/db/session.py
git mv app/database/unit_of_work.py app/core/db/unit_of_work.py
git mv app/database/redis.py app/core/db/redis.py
git mv app/database/__init__.py app/core/db/__init__.py
git mv app/database/models app/core/db/models   # keep models/__init__ re-export
```

- [ ] **Step 3: Recreate `app/database` as a shim package**

```python
# app/database/__init__.py
"""DEPRECATED 경로. app.core.db 로 이전됨. Phase 8에서 제거 예정."""
from app.core.db import *          # noqa: F401,F403
from app.core.db import session, unit_of_work, redis  # noqa: F401
```

```python
# app/database/session.py
from app.core.db.session import *          # noqa: F401,F403
from app.core.db.session import (          # noqa: F401
    engine, background_engine, AsyncSessionLocal, BackgroundSessionLocal,
    get_session, get_background_session, create_db_tables, dispose_engine,
)
```

```python
# app/database/unit_of_work.py
from app.core.db.unit_of_work import BaseUnitOfWork, BaseBackgroundUnitOfWork  # noqa: F401
```

- [ ] **Step 4: Add a shim regression test**

```python
# tests/core/test_db_shim.py
def test_old_database_paths_still_import():
    from app.database.session import get_session, engine          # noqa: F401
    from app.database.unit_of_work import BaseUnitOfWork          # noqa: F401
    from app.core.db.session import get_session as new_get        # noqa: F401
    assert get_session is new_get
```

- [ ] **Step 5: Run full suite (verify no breakage)**

Run: `python -m pytest -q`
Expected: PASS — same count as Step 1 plus the new shim test.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(core): move app/database to app/core/db with re-export shim"
```

### Task 1.2: Move `app/utils` → `app/shared` with shim

**Files:**
- Move: `app/utils/logger.py` → `app/shared/logging/logger.py`; `app/utils/pagination.py` → `app/shared/pagination/pagination.py`
- Create: `app/shared/__init__.py`, `app/shared/logging/__init__.py` (re-export `get_logger`, `setup_uvicorn_logging`, and the `*_LOGGER` constants), `app/shared/pagination/__init__.py`
- Create: `app/utils/__init__.py`, `app/utils/logger.py`, `app/utils/pagination.py` (shims)

**Interfaces:**
- Produces: `app.shared.logging` exposing `get_logger`, `setup_uvicorn_logging`, `CELERY_LOGGER`, etc. Old `app.utils.logger` / `app.utils.pagination` keep working.

- [ ] **Step 1: Move files**

```bash
mkdir -p app/shared/logging app/shared/pagination
git mv app/utils/logger.py app/shared/logging/logger.py
git mv app/utils/pagination.py app/shared/pagination/pagination.py
```

- [ ] **Step 2: Create shared package re-exports**

```python
# app/shared/__init__.py        (empty)
# app/shared/logging/__init__.py
from app.shared.logging.logger import *          # noqa: F401,F403
from app.shared.logging.logger import get_logger, setup_uvicorn_logging  # noqa: F401
```

```python
# app/shared/pagination/__init__.py
from app.shared.pagination.pagination import *   # noqa: F401,F403
```

- [ ] **Step 3: Create old `app/utils` shims**

```python
# app/utils/__init__.py        (empty)
# app/utils/logger.py
from app.shared.logging.logger import *          # noqa: F401,F403
# app/utils/pagination.py
from app.shared.pagination.pagination import *   # noqa: F401,F403
```

- [ ] **Step 4: Shim test**

```python
# tests/core/test_utils_shim.py
def test_old_utils_paths_still_import():
    from app.utils.logger import get_logger
    from app.shared.logging import get_logger as new_get
    assert get_logger is new_get
```

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(shared): move app/utils to app/shared with shims"
```

---

## Phase 2 — Move apps under `app/domains/` (one app per task)

> Repeat this task once per app. `home` is fully implemented and goes first; `user/blog/reply/sns` are empty scaffolds and are fast. Old `app.<name>` import paths get a shim so other modules (e.g. the middleware importing `app.home`) keep working until Phase 3.

### Task 2.1: Move `home` → `domains/home` (template for all apps)

**Files:**
- Move: `app/home/**` → `app/domains/home/**`
- Create: `app/home/__init__.py` (shim that re-exports the moved subpackages)
- Modify: any intra-`home` imports that used absolute `app.home.*` (update to `app.domains.home.*`)

**Interfaces:**
- Produces: `app.domains.home.*`. `app.home.*` remains importable via shim until Phase 3 rewires consumers.

- [ ] **Step 1: Find inbound references (impact analysis)**

Run: `git grep -n "app\.home" -- '*.py'`
Expected: list includes `main.py`, `app/core/middlewares/user_info_middleware.py`, and intra-home files. Record them.

- [ ] **Step 2: Move the package**

```bash
mkdir -p app/domains
git mv app/home app/domains/home
```

- [ ] **Step 3: Rewrite intra-package absolute imports**

Run: `git grep -ln "from app.home" -- 'app/domains/home/**/*.py'`
For each hit, replace `app.home` → `app.domains.home` (in-file). Example in `app/domains/home/services/user_access_log_service.py`:

```python
# before
from app.home.home_exception import InvalidDateRangeException
from app.home.models.models import UserAccessLog
# after
from app.domains.home.exceptions import InvalidDateRangeException   # note: renamed in Task 5.x; keep home_exception import for now if not yet renamed
from app.domains.home.models.models import UserAccessLog
```

(At this phase keep the existing filename `home_exception.py`; only the package prefix changes. The rename to `exceptions.py` happens in Phase 7 cleanup.)

- [ ] **Step 4: Create `app/home` shim**

```python
# app/home/__init__.py
"""DEPRECATED. app.domains.home 로 이전됨. Phase 3에서 소비자 재배선 후 제거."""
# app/home/unit_of_work/__init__.py
from app.domains.home.unit_of_work import *   # noqa: F401,F403
```

Create matching shim modules for each path still referenced by outside code (from Step 1): at minimum `app/home/unit_of_work/__init__.py` and `app/home/services/user_access_log_service.py`:

```python
# app/home/services/__init__.py
from app.domains.home.services import *   # noqa: F401,F403
# app/home/services/user_access_log_service.py
from app.domains.home.services.user_access_log_service import *   # noqa: F401,F403
```

- [ ] **Step 5: Run full suite + boot smoke**

Run: `python -m pytest -q`
Run: `python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(domains): move home app to app/domains/home with shim"
```

### Task 2.2: Move `user`, `blog`, `reply`, `sns` (empty scaffolds)

**Files:**
- Move: `app/<name>/**` → `app/domains/<name>/**` for each of user, blog, reply, sns
- Create: `app/<name>/__init__.py` shim each (these have no external importers, so a one-line package shim suffices)

- [ ] **Step 1: Move all four**

```bash
for n in user blog reply sns; do git mv app/$n app/domains/$n; done
```

- [ ] **Step 2: Add no-op shim packages (only if any inbound ref exists)**

Run: `git grep -n "app\.\(user\|blog\|reply\|sns\)" -- '*.py'`
For each referenced path, add a shim re-export (same pattern as Task 2.1 Step 4). If grep is empty, skip shims.

- [ ] **Step 3: Run suite + boot**

Run: `python -m pytest -q && python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(domains): move user/blog/reply/sns apps under app/domains"
```

---

## Phase 3 — Wire everything through the registry (remove manual central wiring)

### Task 3.1: Add `HomeConfig` to the home app

**Files:**
- Create: `app/domains/home/config.py`
- Test: `tests/domains/home/test_home_config.py`

**Interfaces:**
- Consumes: `app.core.registry.AppConfig`, `app.domains.home.api.routers.router.home_router`, `app.domains.home.api.home_admin.UserAccessLogAdmin`.
- Produces: `HomeConfig` exposing the home router (prefix `/api`) and the access-log admin view.

- [ ] **Step 1: Write the failing test**

```python
# tests/domains/home/test_home_config.py
from app.domains.home.config import HomeConfig

def test_home_config_exposes_router_and_admin():
    cfg = HomeConfig()
    assert cfg.name == "home"
    assert cfg.package == "app.domains.home"
    assert cfg.router() is not None
    assert len(cfg.admin_views()) == 1
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/domains/home/test_home_config.py -v`
Expected: FAIL — `ModuleNotFoundError: app.domains.home.config`

- [ ] **Step 3: Implement**

```python
# app/domains/home/config.py
from fastapi import APIRouter
from app.core.registry import AppConfig


class HomeConfig(AppConfig):
    name = "home"
    category = "domain"
    prefix = "/api"
    order = 10

    def router(self) -> APIRouter:
        from app.domains.home.api.routers.router import home_router
        return home_router

    def admin_views(self) -> list[type]:
        from app.domains.home.api.home_admin import UserAccessLogAdmin
        return [UserAccessLogAdmin]
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/domains/home/test_home_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/domains/home/config.py tests/domains/home/test_home_config.py
git commit -m "feat(home): declare HomeConfig for auto-discovery"
```

### Task 3.2: `create_app()` factory using the registry

**Files:**
- Create: `app/core/bootstrap.py`
- Test: `tests/core/test_bootstrap.py`

**Interfaces:**
- Consumes: `AppRegistry`, existing middleware setup (`CustomCORSMiddleware`, `setup_user_info_middleware`), existing exception handlers, `app_settings`.
- Produces: `create_app() -> FastAPI` that discovers apps, imports models, installs routers, registers exception handlers, mounts SQLAdmin when `app_settings.ADMIN`, and keeps `/health` + Scalar `/docs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_bootstrap.py
from fastapi.testclient import TestClient

def test_create_app_registers_home_routes_and_health():
    from app.core.bootstrap import create_app
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert any(p.startswith("/api/v1/home") for p in paths)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/core/test_bootstrap.py -v`
Expected: FAIL — `ModuleNotFoundError: app.core.bootstrap`

- [ ] **Step 3: Implement `create_app` (port logic from current `main.py`)**

```python
# app/core/bootstrap.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exception import AppException, ErrorResponse, ValidationException
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.tags_metadata import tags_metadata
from app.core.registry import AppRegistry
from app.core.db.session import create_db_tables, dispose_engine, engine
from app.shared.logging import get_logger
from config import app_settings

logger = get_logger("bootstrap")
registry = AppRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if app_settings.DEBUG:
        await create_db_tables()
    yield
    await dispose_engine()


def _register_exception_handlers(app: FastAPI) -> None:
    # (port the four @app.exception_handler bodies verbatim from current main.py)
    ...


def create_app() -> FastAPI:
    registry.discover()              # app/domains/* 재귀 스캔
    registry.import_models()         # Base.metadata 채움 (create_db_tables/Alembic 공용)

    app = FastAPI(
        title=app_settings.PROJECT_NAME,
        version=app_settings.VERSION,
        description=app_settings.DESCRIPTION,
        openapi_tags=tags_metadata,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url=None, redoc_url=None,
        openapi_url="/openapi.json" if app_settings.DEBUG else None,
    )

    CustomCORSMiddleware(app).configure_cors()
    setup_user_info_middleware(app)
    _register_exception_handlers(app)

    n = registry.install_routers(app)
    logger.info("registered %d app routers", n)

    _add_health_and_docs(app)        # port /health + Scalar /docs from main.py

    if app_settings.ADMIN:
        from sqladmin import Admin
        admin = Admin(app, engine, title=f"{app_settings.PROJECT_NAME} Admin")
        registry.install_admin(admin)

    return app
```

> Implementer note: copy the exact bodies of the 4 exception handlers, `/health`, and the Scalar `/docs` route from the current `main.py` into `_register_exception_handlers` and `_add_health_and_docs`. No logic changes.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/core/test_bootstrap.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/bootstrap.py tests/core/test_bootstrap.py
git commit -m "feat(core): add create_app factory driven by AppRegistry"
```

### Task 3.3: Slim `main.py` + remove manual model registration

**Files:**
- Modify: `main.py` (replace body with factory call)
- Modify: `app/core/db/session.py` (`create_db_tables` uses `Base.metadata.create_all` for all registered tables instead of a hand-maintained import list)
- Test: `tests/test_main.py` (update/confirm app boots and home routes exist)

**Interfaces:**
- Consumes: `app.core.bootstrap.create_app`.
- Produces: `main.app` (unchanged public name, used by uvicorn `main:app`).

- [ ] **Step 1: Write/adjust the failing test**

```python
# tests/test_main.py
from fastapi.testclient import TestClient

def test_main_app_boots_and_serves_health():
    import main
    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    paths = {r.path for r in main.app.routes}
    assert any(p.startswith("/api/v1/home") for p in paths)
```

- [ ] **Step 2: Run to verify current state**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS already (old main) — this is a guard so the refactor can't regress it.

- [ ] **Step 3: Replace `main.py` body**

```python
# main.py
"""FastAPI 진입점. 모든 조립은 create_app() 안에서 레지스트리가 수행한다."""
from app.core.bootstrap import create_app
from config import app_settings

app = create_app()

if __name__ == "__main__":
    import uvicorn
    from app.shared.logging import setup_uvicorn_logging
    uvicorn.run("main:app", host="0.0.0.0", port=8000,
                reload=app_settings.DEBUG, log_config=setup_uvicorn_logging())
```

- [ ] **Step 4: Make `create_db_tables` registry-driven**

```python
# app/core/db/session.py — replace the body of create_db_tables()
async def create_db_tables() -> None:
    import asyncio
    from app.core.registry import AppRegistry
    AppRegistry().discover()           # populate Base.metadata via import_models
    # (bootstrap already imported models; this guard makes the fn self-sufficient)
    from app.core.registry import AppRegistry as _R
    _R().import_models()
    async with asyncio.timeout(30):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
```

> Implementer note: `Base` is already imported at top of `session.py`. Remove the hand-maintained `from app.home.models...` import and `tables_to_create` list.

- [ ] **Step 5: Run suite + boot**

Run: `python -m pytest -q && python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 6: Commit**

```bash
git add main.py app/core/db/session.py tests/test_main.py
git commit -m "refactor: drive app + table creation from registry, slim main.py"
```

### Task 3.4: Break the core→home middleware dependency

**Files:**
- Modify: `app/core/middlewares/user_info_middleware.py` (remove `from app.home...` import)
- Create: `app/core/middlewares/access_log_sink.py` (a Protocol + a registration hook)
- Modify: `app/domains/home/config.py` (register the access-log sink on startup)
- Test: `tests/core/test_access_log_decoupling.py`

**Interfaces:**
- Produces: `AccessLogSink` Protocol with `async def save(self, data: dict) -> None`; `set_access_log_sink(sink)` / `get_access_log_sink()` module functions. Middleware calls the registered sink (no-op if none registered) instead of importing `home` directly. `home` registers its `HomeBackgroundUnitOfWork`-backed sink in `HomeConfig` (e.g. an `on_startup()` hook called by the registry, or import side-effect in `home.config`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_access_log_decoupling.py
import importlib

def test_middleware_does_not_import_home():
    mod = importlib.import_module("app.core.middlewares.user_info_middleware")
    src = importlib.util.find_spec("app.core.middlewares.user_info_middleware").origin
    text = open(src, encoding="utf-8").read()
    assert "app.home" not in text and "app.domains.home" not in text

def test_sink_registration_roundtrip():
    from app.core.middlewares.access_log_sink import set_access_log_sink, get_access_log_sink
    calls = []
    class S:
        async def save(self, data): calls.append(data)
    set_access_log_sink(S())
    assert get_access_log_sink() is not None
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/core/test_access_log_decoupling.py -v`
Expected: FAIL — middleware still references home / sink module missing.

- [ ] **Step 3: Implement the sink module**

```python
# app/core/middlewares/access_log_sink.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class AccessLogSink(Protocol):
    async def save(self, data: dict) -> None: ...

_sink: AccessLogSink | None = None

def set_access_log_sink(sink: AccessLogSink) -> None:
    global _sink
    _sink = sink

def get_access_log_sink() -> AccessLogSink | None:
    return _sink
```

- [ ] **Step 4: Rewire middleware to use the sink**

In `user_info_middleware.py`: delete the `from app.home.unit_of_work import HomeBackgroundUnitOfWork` and `from app.home.services...` imports; in `_save_access_log`, fetch `get_access_log_sink()` and call `await sink.save(request_info)` (skip if `None`).

- [ ] **Step 5: Register the home sink**

```python
# app/domains/home/access_log_sink.py
from app.domains.home.unit_of_work import HomeUnitOfWork
from app.domains.home.services.user_access_log_service import UserAccessLogService

class HomeAccessLogSink:
    async def save(self, data: dict) -> None:
        async with HomeUnitOfWork(background=True) as uow:
            await UserAccessLogService(uow).create_access_log(data)
```

```python
# app/domains/home/config.py — register on import
from app.core.middlewares.access_log_sink import set_access_log_sink
from app.domains.home.access_log_sink import HomeAccessLogSink
set_access_log_sink(HomeAccessLogSink())
```

- [ ] **Step 6: Run suite + boot**

Run: `python -m pytest -q && python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(core): decouple access-log middleware from home via sink protocol"
```

---

## Phase 4 — Celery (single app + autodiscover)

### Task 4.1: Add Celery dependency + core celery app

**Files:**
- Modify: `pyproject.toml` (add `celery[redis] (>=5.4,<6.0)`)
- Create: `app/core/celery/__init__.py`, `app/core/celery/app.py`
- Test: `tests/core/test_celery_app.py`

**Interfaces:**
- Produces: `app.core.celery.app.celery_app` (Celery instance, Redis broker+backend from `redis_settings`), configured with `autodiscover_tasks(registry.celery_packages(), related_name="worker.tasks")` and `beat_schedule = registry.merged_beat_schedule()`.

- [ ] **Step 1: Add dependency + install**

```bash
# pyproject.toml dependencies: add
#   "celery[redis] (>=5.4.0,<6.0.0)",
pip install "celery[redis]>=5.4,<6.0"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/core/test_celery_app.py
def test_celery_app_configured():
    from app.core.celery.app import celery_app
    assert celery_app.conf.broker_url.startswith("redis://")
    # home package is among autodiscover packages
    assert any("home" in p for p in celery_app.conf["__autodiscover_packages__"])
```

- [ ] **Step 3: Run to verify fail**

Run: `python -m pytest tests/core/test_celery_app.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement**

```python
# app/core/celery/app.py
from celery import Celery
from app.core.registry import AppRegistry
from config import redis_settings

registry = AppRegistry()
registry.discover()

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    beat_schedule=registry.merged_beat_schedule(),
)
_packages = registry.celery_packages()
celery_app.conf["__autodiscover_packages__"] = _packages
celery_app.autodiscover_tasks(_packages, related_name="worker.tasks")
```

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/core/test_celery_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/core/celery tests/core/test_celery_app.py
git commit -m "feat(celery): add single Celery app with registry-driven autodiscover"
```

### Task 4.2: Async-aware `DBTask` base + first real home task

**Files:**
- Create: `app/core/celery/task.py`
- Create: `app/domains/home/worker/tasks.py` (replace empty `home_task.py`)
- Delete: `app/domains/home/worker/home_task.py`
- Test: `tests/domains/home/test_home_tasks.py`

**Interfaces:**
- Produces: `run_async(coro)` helper (runs an async coroutine inside a sync Celery worker via `asyncio.run`); `@celery_app.task(name="home.aggregate_access_stats")` task returning a dict of counts.

- [ ] **Step 1: Write the failing test (task is importable + callable in eager mode)**

```python
# tests/domains/home/test_home_tasks.py
def test_aggregate_task_registered():
    from app.core.celery.app import celery_app
    from app.domains.home.worker import tasks   # noqa: F401
    assert "home.aggregate_access_stats" in celery_app.tasks
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/domains/home/test_home_tasks.py -v`
Expected: FAIL — task module missing.

- [ ] **Step 3: Implement bridge + task**

```python
# app/core/celery/task.py
import asyncio
from typing import Any, Coroutine

def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """동기 Celery 워커에서 async 코루틴 실행."""
    return asyncio.run(coro)
```

```python
# app/domains/home/worker/tasks.py
from app.core.celery.app import celery_app
from app.core.celery.task import run_async
from app.domains.home.unit_of_work import HomeUnitOfWork
from app.domains.home.services.user_access_log_service import UserAccessLogService

@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict:
    async def _run() -> dict:
        async with HomeUnitOfWork(background=True) as uow:
            stats = await UserAccessLogService(uow).get_stats()
            return {"total": stats.total_count}
    return run_async(_run())
```

```bash
git rm app/domains/home/worker/home_task.py
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/domains/home/test_home_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(home): add first Celery task + async DBTask bridge"
```

---

## Phase 5 — Alembic (registry-driven autogenerate)

### Task 5.1: Initialize Alembic with registry metadata

**Files:**
- Create: `migrations/` (via `alembic init`), then modify `migrations/env.py`
- Create: `alembic.ini`
- Test: `tests/core/test_alembic_metadata.py`

**Interfaces:**
- Produces: `migrations/env.py` that calls `AppRegistry().discover(); AppRegistry().import_models()` and sets `target_metadata = Base.metadata`; offline+online migration funcs use `db_settings.MYSQL_URL`.

- [ ] **Step 1: Init alembic**

```bash
alembic init migrations
```

- [ ] **Step 2: Write the failing test**

```python
# tests/core/test_alembic_metadata.py
def test_registry_populates_all_tables():
    from app.core.registry import AppRegistry
    from app.core.db.session import Base
    AppRegistry().import_models.__self__  # noqa
    reg = AppRegistry(); reg.discover(); reg.import_models()
    assert "user_access_logs" in Base.metadata.tables
```

- [ ] **Step 3: Run to verify fail/pass**

Run: `python -m pytest tests/core/test_alembic_metadata.py -v`
Expected: PASS once registry import_models works (this guards env.py's approach).

- [ ] **Step 4: Edit `migrations/env.py`**

```python
# migrations/env.py — key edits
from app.core.db.session import Base
from app.core.registry import AppRegistry
from config import db_settings

_reg = AppRegistry(); _reg.discover(); _reg.import_models()
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", db_settings.MYSQL_URL.replace("+aiomysql", "+pymysql"))
```

> Note: Alembic runs sync; use `pymysql` URL for migrations (add `pymysql` to dev deps).

- [ ] **Step 5: Generate baseline migration**

```bash
alembic revision --autogenerate -m "baseline schema"
alembic upgrade head     # against a scratch DB
```

Expected: a migration containing `user_access_logs` is generated and applies cleanly.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations tests/core/test_alembic_metadata.py pyproject.toml
git commit -m "feat(db): initialize Alembic with registry-driven metadata"
```

---

## Phase 6 — Declarative UnitOfWork (remove 2× duplication)

### Task 6.1: Declarative `BaseUnitOfWork` with `background` flag

**Files:**
- Modify: `app/core/db/unit_of_work.py`
- Test: `tests/core/test_uow_declarative.py`

**Interfaces:**
- Produces: `BaseUnitOfWork(session=None, *, background=False)`; class attr `repositories: dict[str, type] = {}`; `__aenter__` selects `BackgroundSessionLocal` when `background` else `AsyncSessionLocal`, instantiates each repo from the map. `BaseBackgroundUnitOfWork` kept as a thin deprecated subclass that sets `background=True` (removed in Phase 8).

- [ ] **Step 1: Write the failing test (sqlite-backed)**

```python
# tests/core/test_uow_declarative.py
import pytest
from app.core.db.unit_of_work import BaseUnitOfWork

class _Repo:
    def __init__(self, session): self.session = session

class _UoW(BaseUnitOfWork):
    things: _Repo
    repositories = {"things": _Repo}

@pytest.mark.asyncio
async def test_repositories_autowired():
    async with _UoW() as uow:
        assert isinstance(uow.things, _Repo)
        assert uow.things.session is uow.session
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/core/test_uow_declarative.py -v`
Expected: FAIL — `repositories` not wired in base.

- [ ] **Step 3: Implement declarative base**

```python
# app/core/db/unit_of_work.py — augment BaseUnitOfWork
class BaseUnitOfWork:
    repositories: dict[str, type] = {}

    def __init__(self, session: AsyncSession | None = None, *, background: bool = False) -> None:
        self._session = session
        self._owns_session = session is None
        self._background = background

    async def __aenter__(self):
        if self._owns_session:
            factory = BackgroundSessionLocal if self._background else AsyncSessionLocal
            self._session = factory()
        for attr, repo_cls in self.repositories.items():
            setattr(self, attr, repo_cls(self._session))
        return self
    # __aexit__, session, commit, rollback, flush unchanged
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/core/test_uow_declarative.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/db/unit_of_work.py tests/core/test_uow_declarative.py
git commit -m "feat(db): declarative repositories map + background flag in BaseUnitOfWork"
```

### Task 6.2: Collapse `HomeUnitOfWork` to one class

**Files:**
- Modify: `app/domains/home/unit_of_work/home_unit_of_work.py` (→ single declarative class)
- Modify: `app/domains/home/unit_of_work/__init__.py` (export `HomeUnitOfWork`; keep `HomeBackgroundUnitOfWork` alias → `partial(HomeUnitOfWork, background=True)` style shim)
- Modify call sites: `app/domains/home/access_log_sink.py`, `app/domains/home/worker/tasks.py` already use `HomeUnitOfWork(background=True)`
- Test: `tests/domains/home/test_home_uow.py`

**Interfaces:**
- Produces: `HomeUnitOfWork` with `repositories = {"user_access_logs": UserAccessLogRepository}`. `HomeBackgroundUnitOfWork` remains importable (deprecated) and behaves as `HomeUnitOfWork(background=True)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/domains/home/test_home_uow.py
import pytest
from app.domains.home.unit_of_work import HomeUnitOfWork

@pytest.mark.asyncio
async def test_home_uow_has_repo():
    async with HomeUnitOfWork(background=True) as uow:
        assert uow.user_access_logs is not None
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/domains/home/test_home_uow.py -v`
Expected: FAIL if current class still overrides `__aenter__` without repositories map (or passes already — if green, still proceed to simplify).

- [ ] **Step 3: Rewrite the class**

```python
# app/domains/home/unit_of_work/home_unit_of_work.py
from app.core.db.unit_of_work import BaseUnitOfWork
from app.domains.home.repositories.user_access_log_repository import UserAccessLogRepository

class HomeUnitOfWork(BaseUnitOfWork):
    user_access_logs: UserAccessLogRepository
    repositories = {"user_access_logs": UserAccessLogRepository}

# deprecated alias (removed in Phase 8)
class HomeBackgroundUnitOfWork(HomeUnitOfWork):
    def __init__(self, session=None):
        super().__init__(session, background=True)
```

- [ ] **Step 4: Run suite + boot**

Run: `python -m pytest -q && python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(home): single declarative HomeUnitOfWork, deprecate background twin"
```

---

## Phase 7 — Scaffolding generator + naming cleanup + docs SSoT

### Task 7.1: `scripts/new_app.py` generator

**Files:**
- Create: `scripts/__init__.py`, `scripts/new_app.py`
- Create: `scripts/_templates/` (config.py, unit_of_work.py, api/routers, models, schemas, services, repositories, tests)
- Test: `tests/scripts/test_new_app.py`

**Interfaces:**
- Produces: CLI `python -m scripts.new_app <name> [--category domain] [--with-worker] [--with-admin]` that writes `app/domains/<name>/` with required files and a `config.py` exposing the router; optional folders added by flags.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_new_app.py
import subprocess, sys, pathlib

def test_generator_creates_bootable_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app/domains").mkdir(parents=True)
    # run generator pointed at temp root
    from scripts.new_app import scaffold
    scaffold("widget", root=tmp_path, category="domain")
    assert (tmp_path / "app/domains/widget/config.py").exists()
    assert (tmp_path / "app/domains/widget/api/routers/router.py").exists()
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/scripts/test_new_app.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `scaffold()` + CLI**

```python
# scripts/new_app.py
import pathlib, argparse

REQUIRED_DIRS = ["api/routers/v1", "models", "schemas", "services", "repositories", "tests"]

def scaffold(name: str, root: pathlib.Path, category: str = "domain",
             with_worker: bool = False, with_admin: bool = False) -> None:
    base = root / "app" / "domains" / name
    for d in REQUIRED_DIRS:
        (base / d).mkdir(parents=True, exist_ok=True)
        (base / d.split("/")[0] / "__init__.py").touch()
    (base / "__init__.py").touch()
    (base / "config.py").write_text(_CONFIG_TMPL.format(name=name, Class=name.capitalize(), category=category), encoding="utf-8")
    (base / "api/routers/router.py").write_text(_ROUTER_TMPL.format(name=name), encoding="utf-8")
    (base / "unit_of_work.py").write_text(_UOW_TMPL.format(Class=name.capitalize()), encoding="utf-8")
    if with_worker:
        (base / "worker").mkdir(exist_ok=True); (base / "worker/__init__.py").touch()
        (base / "worker/tasks.py").write_text(_TASKS_TMPL, encoding="utf-8")
    if with_admin:
        (base / "admin.py").write_text(_ADMIN_TMPL, encoding="utf-8")

# (define _CONFIG_TMPL, _ROUTER_TMPL, _UOW_TMPL, _TASKS_TMPL, _ADMIN_TMPL as string constants
#  mirroring the home app's shape)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("name"); p.add_argument("--category", default="domain")
    p.add_argument("--with-worker", action="store_true"); p.add_argument("--with-admin", action="store_true")
    a = p.parse_args()
    scaffold(a.name, root=pathlib.Path.cwd(), category=a.category, with_worker=a.with_worker, with_admin=a.with_admin)
    print(f"created app/domains/{a.name}")
```

> Implementer note: fill the `_*_TMPL` constants by copying the minimal shape from `app/domains/home` (config.py, an empty APIRouter, a `repositories = {}` UoW).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/scripts/test_new_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts tests/scripts
git commit -m "feat(tooling): add new_app scaffolding generator"
```

### Task 7.2: Filename normalization (`*_exception.py`→`exceptions.py`, etc.)

**Files:**
- Move within `app/domains/home`: `home_exception.py`→`exceptions.py`, `api/home_admin.py`→`admin.py`, `dependency.py`→`dependencies.py`, `worker/home_task.py` already removed
- Modify: imports referencing the old names (e.g. `config.py` admin import, `services/user_access_log_service.py` exception import)
- Test: existing home tests must stay green

- [ ] **Step 1: Rename + fix imports**

```bash
git mv app/domains/home/home_exception.py app/domains/home/exceptions.py
git mv app/domains/home/api/home_admin.py app/domains/home/admin.py
git mv app/domains/home/dependency.py app/domains/home/dependencies.py
git grep -ln "home_exception\|home_admin" -- 'app/domains/home/**/*.py'
# update each hit: home_exception -> exceptions, api.home_admin -> admin
```

Update `app/domains/home/config.py` admin import to `from app.domains.home.admin import UserAccessLogAdmin`.

- [ ] **Step 2: Run suite + boot**

Run: `python -m pytest -q && python -c "import main; print('boot ok')"`
Expected: PASS / `boot ok`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(home): normalize filenames to naming standard"
```

### Task 7.3: Consolidate docs to a single ARCHITECTURE source

**Files:**
- Create: `docs/ARCHITECTURE.md` (authoritative; references `docs/proposer/index.html` as the design rationale)
- Modify: `README.md` (replace the drifted "프로젝트 구조"/"신규 모듈 개발 가이드" sections with a pointer to ARCHITECTURE.md + the registry-based add-app steps)
- Delete: `docs/refactoring/refac.md` content superseded — replace with a one-line "superseded by ARCHITECTURE.md" stub

- [ ] **Step 1: Write ARCHITECTURE.md**

Document: the `domains/core/shared` taxonomy, the AppConfig contract, the new-app flow (`python -m scripts.new_app`), Celery autodiscover, Alembic registry, and the required/optional file table. Copy the verbatim "new app = 0 central edits" guarantee.

- [ ] **Step 2: Update README + stub refac.md**

Replace README structure/guide sections; reduce `docs/refactoring/refac.md` to: `> 이 문서는 docs/ARCHITECTURE.md 로 대체되었습니다.`

- [ ] **Step 3: Commit**

```bash
git add docs/ARCHITECTURE.md README.md docs/refactoring/refac.md
git commit -m "docs: single-source architecture doc, remove drift"
```

---

## Phase 8 — Remove shims, final verification

### Task 8.1: Delete deprecated shims and the background-UoW twin

**Files:**
- Delete: `app/database/` shim package, `app/utils/` shim package, `app/home/` (and `user/blog/reply/sns`) shim packages, `HomeBackgroundUnitOfWork`
- Modify: any remaining importer found by grep to use the canonical path

- [ ] **Step 1: Find remaining shim importers**

Run: `git grep -nE "app\.database|app\.utils|app\.home|HomeBackgroundUnitOfWork" -- '*.py'`
Expected: only the shim files themselves and tests; rewrite any real importer to canonical paths.

- [ ] **Step 2: Delete shims**

```bash
git rm -r app/database app/utils app/home
# remove HomeBackgroundUnitOfWork class + export
```

- [ ] **Step 3: Full verification gate**

Run: `python -m pytest -q`
Run: `python -c "import main; print('boot ok')"`
Run: `python -c "from app.core.celery.app import celery_app; print(len(celery_app.tasks))"`
Run: `alembic upgrade head` (scratch DB)
Expected: all green; home routes, admin, health, celery task, and migration all functional with **no** `app.database/app.utils/app.home` imports remaining.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove deprecated shims and background-UoW twin"
```

---

## Self-Review Notes (coverage map)

| Spec item (proposer §) | Plan task(s) |
|---|---|
| ① 중앙 수정 0 (라우터/모델/admin) | 0.1–0.3, 3.1–3.3 |
| ② core→home 역의존 제거 | 3.4 |
| ③ UoW 2× 제거 | 6.1, 6.2 |
| ④ Celery 실체화 | 4.1, 4.2 |
| ⑤ 스캐폴드 필수/옵션 + 생성기 | 7.1, 7.2 |
| ⑥ Alembic 모델 레지스트리 | 3.3, 5.1 |
| 폴더 domains/core/shared | 1.1, 1.2, 2.1, 2.2 |
| 네이밍 표준 | 7.2 |
| 문서 단일화 | 7.3 |
| 안전성(shim, 단계별 그린) | 1.1–2.2 shims, 8.1 removal |
