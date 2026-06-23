"""
scripts/new_app.py — FastAPI app scaffolding generator.

Django-style ``startapp`` equivalent for a uv-based FastAPI project that uses
explicit (manual) app registration. Each new app must be wired up by hand in
``app/apps.py`` (router, models, admin views, Celery package).

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
        category: Reserved for compatibility; no longer affects output.
        with_worker: If True, create ``worker/tasks.py``.
        with_admin: If True, create ``admin.py``.

    Note:
        The generated app is NOT auto-discovered. After scaffolding, register
        it manually in ``app/apps.py`` (router, models, admin, Celery package).
    """
    del category  # reserved for backward compatibility; unused
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
    print(f"created app/domains/{name}")
    print()
    print("다음 단계: app/apps.py 에 이 앱을 수동으로 등록하세요.")
    print(f"  - routers(): app.domains.{name}.api.routers.router 의 {name}_router 를 RouterSpec 으로 추가")
    print(f"  - register_models(): _MODEL_MODULES 에 \"app.domains.{name}.models.models\" 추가")
    if args.with_admin:
        print(f"  - admin_views(): app.domains.{name}.admin 의 ModelView 클래스 추가")
    if args.with_worker:
        print(f"  - CELERY_TASK_MODULES: \"app.domains.{name}.worker.tasks\" 추가 (필요 시 BEAT_SCHEDULE 도)")
