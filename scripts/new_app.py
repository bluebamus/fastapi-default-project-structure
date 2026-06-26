"""
scripts/new_app.py — FastAPI app scaffolding generator.

Django-style ``startapp`` equivalent for a uv-based FastAPI project that uses
registry auto-discovery. Each new app exposes a ``config.py`` with an
``AppConfig`` subclass; AppRegistry discovers it at boot — no central edits.

Usage (CLI):
    python -m scripts.new_app <name> [--category domain] [--with-worker] [--with-admin]

Usage (API):
    from pathlib import Path
    from scripts.new_app import scaffold
    scaffold("orders", root=Path.cwd(), category="domain")
"""

from __future__ import annotations

import argparse
import pathlib

# ---------------------------------------------------------------------------
# Template constants
# ---------------------------------------------------------------------------

_CONFIG_TMPL = '''\
"""
{Class} 도메인 앱 자기선언(AppConfig).

AppRegistry 가 부팅 시 이 모듈을 자동 발견하여 라우터/모델/Admin 을 연결한다.
admin/worker 를 쓰면 admin_views()/beat_schedule() 훅을 아래에 추가한다.
"""
from fastapi import APIRouter

from app.core.registry import AppConfig


class {Class}Config(AppConfig):
    name = "{name}"
    category = "{category}"
    prefix = "/api"
    order = 100

    def router(self) -> APIRouter:
        from app.domains.{name}.api.routers.router import {name}_router
        return {name}_router
'''

_ROUTER_TMPL = '''\
"""
{name} module router aggregator.

Add versioned sub-routers here, e.g.:
    from app.domains.{name}.api.routers.v1 import {name} as {name}_v1
    {name}_router.include_router({name}_v1.router, prefix="/v1/{name}", tags=["{Class}"])
"""

from fastapi import APIRouter

{name}_router = APIRouter()
'''

_UOW_TMPL = '''\
"""
{Class} domain UnitOfWork.

Declare domain repositories in the ``repositories`` map; BaseUnitOfWork
will initialise them automatically on ``async with``.

Example:
    class {Class}UnitOfWork(BaseUnitOfWork):
        items: ItemRepository
        repositories = {{"items": ItemRepository}}
"""

from app.core.db.unit_of_work import BaseUnitOfWork


class {Class}UnitOfWork(BaseUnitOfWork):
    """Declarative UnitOfWork for the {name} domain."""

    repositories: dict = {{}}
'''

_TASKS_TMPL = '''\
"""
{Class} domain Celery tasks.

Register tasks here. For recurring schedules, add entries to BEAT_SCHEDULE
in app/apps.py.
"""

from app.core.celery.app import celery_app
from app.core.celery.task import run_async


@celery_app.task(name="{name}.example_task")
def example_task() -> dict:
    async def _run() -> dict:
        return {{"ok": True}}
    return run_async(_run())
'''

_ADMIN_TMPL = '''\
"""
{Class} domain SQLAdmin views.

Register ModelView subclasses here and add them to admin_views() in
app/apps.py so the app mounts them.

To activate, uncomment and replace the placeholder with a real model:
    from sqladmin import ModelView
    from app.domains.{name}.models.models import {Class}Model

    class {Class}Admin(ModelView, model={Class}Model):
        column_list = "__all__"
"""

# No views registered yet — add ModelView subclasses above.
'''

# ---------------------------------------------------------------------------
# Required directory structure (relative to app root)
# ---------------------------------------------------------------------------

_REQUIRED_DIRS = [
    "api/routers/v1",
    "models",
    "schemas",
    "services",
    "repositories",
    "tests",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold(
    name: str,
    root: pathlib.Path,
    category: str = "domain",
    with_worker: bool = False,
    with_admin: bool = False,
) -> None:
    """Generate ``app/domains/<name>/`` scaffolding under *root*.

    Args:
        name: Snake-case app name (e.g. ``"orders"``).
        root: Project root directory (the one containing ``app/``).
        category: AppConfig ``category`` written into the generated config.py.
        with_worker: If True, create ``worker/tasks.py``.
        with_admin: If True, create ``admin.py``.

    Note:
        The generated app IS auto-discovered via its ``config.py`` — AppRegistry
        picks it up at boot. No central-file edits required.
    """
    class_name = "".join(part.capitalize() for part in name.split("_"))
    base = root / "app" / "domains" / name

    # Create required directory tree; each leaf gets an __init__.py, and so
    # does every intermediate directory (api/, api/routers/, etc.).
    for rel in _REQUIRED_DIRS:
        full = base / rel
        full.mkdir(parents=True, exist_ok=True)
        # Touch __init__.py for every path segment under base
        _touch_init_chain(base, rel)

    # App root __init__.py
    (base / "__init__.py").touch()

    # Core files
    (base / "config.py").write_text(
        _CONFIG_TMPL.format(name=name, Class=class_name, category=category),
        encoding="utf-8",
    )
    (base / "api" / "routers" / "router.py").write_text(
        _ROUTER_TMPL.format(name=name, Class=class_name),
        encoding="utf-8",
    )
    (base / "unit_of_work.py").write_text(
        _UOW_TMPL.format(name=name, Class=class_name),
        encoding="utf-8",
    )

    # Optional: worker
    if with_worker:
        worker_dir = base / "worker"
        worker_dir.mkdir(exist_ok=True)
        (worker_dir / "__init__.py").touch()
        (worker_dir / "tasks.py").write_text(
            _TASKS_TMPL.format(name=name, Class=class_name),
            encoding="utf-8",
        )

    # Optional: admin
    if with_admin:
        (base / "admin.py").write_text(
            _ADMIN_TMPL.format(name=name, Class=class_name),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _touch_init_chain(base: pathlib.Path, rel: str) -> None:
    """Create ``__init__.py`` in every directory segment of *rel* under *base*."""
    parts = pathlib.PurePosixPath(rel).parts
    current = base
    for part in parts:
        current = current / part
        init = current / "__init__.py"
        if not init.exists():
            init.touch()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.new_app",
        description="Scaffold a new FastAPI domain app.",
    )
    p.add_argument("name", help="Snake-case app name (e.g. orders)")
    p.add_argument("--category", default="domain", help="Reserved (unused; kept for compatibility)")
    p.add_argument("--with-worker", action="store_true", help="Create worker/tasks.py")
    p.add_argument("--with-admin", action="store_true", help="Create admin.py")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    scaffold(
        args.name,
        root=pathlib.Path.cwd(),
        category=args.category,
        with_worker=args.with_worker,
        with_admin=args.with_admin,
    )
    name = args.name
    class_name = "".join(part.capitalize() for part in name.split("_"))
    print(f"created app/domains/{name}")
    print()
    print("이 앱은 config.py 로 자동 발견됩니다 — app/apps.py 등 중앙 파일 수정 불필요.")
    print(f"  - config.py: {class_name}Config(AppConfig) 가 생성됨(라우터 자동 연결)")
    if args.with_admin:
        print("  - admin: config.py 에 admin_views() 훅을 추가해 ModelView 를 노출하세요")
    if args.with_worker:
        print("  - worker: worker/tasks.py 의 태스크는 autodiscover_tasks 가 자동 등록(필요 시 config.py 에 beat_schedule())")
    print("  - 서버 재시작 시 /api 경로에 라우터가 마운트됩니다")
