"""
scripts/new_app.py — FastAPI app scaffolding generator (컨벤션 기반, gen-2).

Django-style ``startapp`` equivalent. 앱은 별도 선언(config.py) 없이 디렉터리
구조와 네이밍 컨벤션만으로 AppRegistry 에 자동 발견된다.

컨벤션 (생성되는 구조):
    app/domains/<name>/
        api/routers/router.py   →  <name>_router: APIRouter   (/api 에 자동 마운트)
        api/routers/v1/         →  버전별 서브라우터 위치
        models/                 →  ORM 모델 (Base.metadata 자동 등록)
        schemas/ services/ repositories/ dependencies/ tests/
        admin.py (선택)         →  admin_views: list[type]

Usage (CLI):
    python -m scripts.new_app <name> [--with-admin]

Usage (API):
    from pathlib import Path
    from scripts.new_app import scaffold
    scaffold("orders", root=Path.cwd())
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

컨벤션: AppRegistry 가 이 모듈의 ``{name}_router`` 를 발견해 /api 에 마운트한다.
버전별 서브라우터를 여기에 include 한다. 예:
    from app.domains.{name}.api.routers.v1 import {name} as {name}_v1
    {name}_router.include_router({name}_v1.router, prefix="/v1/{name}", tags=["{Class}"])
"""

from fastapi import APIRouter

{name}_router = APIRouter()
'''

_DEPS_TMPL = '''\
"""
{Class} 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합해 view 에 제공한다.
yield 후 성공 시 커밋 — 트랜잭션 경계를 담당한다(UnitOfWork 대체).

예시:
    from collections.abc import AsyncGenerator
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.db.session import get_session
    from app.domains.{name}.services.{name}_service import {Class}Service

    async def get_{name}_service(
        session: AsyncSession = Depends(get_session),
    ) -> AsyncGenerator[{Class}Service, None]:
        service = {Class}Service(session)
        yield service
        await session.commit()
"""
'''

_ADMIN_TMPL = '''\
"""
{Class} domain SQLAdmin views.

컨벤션: 모듈 레벨 ``admin_views`` 리스트를 두면 AppRegistry.install_admin 이
자동으로 SQLAdmin 에 등록한다(중앙 파일 수정 불필요).

활성화하려면 placeholder 를 실제 모델 기반 ModelView 로 교체한다:
    from sqladmin import ModelView
    from app.domains.{name}.models.models import {Class}Model

    class {Class}Admin(ModelView, model={Class}Model):
        column_list = "__all__"

    admin_views = [{Class}Admin]
"""

# 아직 등록된 뷰 없음 — 위에 ModelView 를 추가하고 admin_views 에 넣으세요.
admin_views: list[type] = []
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
    "dependencies",
    "tests",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold(
    name: str,
    root: pathlib.Path,
    category: str = "domain",
    with_admin: bool = False,
) -> None:
    """Generate ``app/domains/<name>/`` scaffolding under *root*.

    Args:
        name: Snake-case app name (e.g. ``"orders"``).
        root: Project root directory (the one containing ``app/``).
        category: 예약(미사용) — 호환을 위해 시그니처만 유지.
        with_admin: If True, create ``admin.py`` (with empty ``admin_views``).

    Note:
        생성된 앱은 디렉터리 컨벤션만으로 AppRegistry 에 자동 발견된다.
        중앙 파일(config.py / app/apps.py 등) 수정이 필요 없다.
    """
    class_name = "".join(part.capitalize() for part in name.split("_"))
    base = root / "app" / "domains" / name

    # Create required directory tree; each segment gets an __init__.py.
    for rel in _REQUIRED_DIRS:
        full = base / rel
        full.mkdir(parents=True, exist_ok=True)
        _touch_init_chain(base, rel)

    # App root __init__.py (import-time 부수효과가 필요하면 여기에 추가)
    (base / "__init__.py").touch()

    # Core files
    (base / "api" / "routers" / "router.py").write_text(
        _ROUTER_TMPL.format(name=name, Class=class_name),
        encoding="utf-8",
    )
    (base / "dependencies" / f"{name}_dependencies.py").write_text(
        _DEPS_TMPL.format(name=name, Class=class_name),
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
        description="Scaffold a new FastAPI domain app (convention-based).",
    )
    p.add_argument("name", help="Snake-case app name (e.g. orders)")
    p.add_argument("--category", default="domain", help="Reserved (unused; kept for compatibility)")
    p.add_argument("--with-admin", action="store_true", help="Create admin.py")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    scaffold(
        args.name,
        root=pathlib.Path.cwd(),
        category=args.category,
        with_admin=args.with_admin,
    )
    name = args.name
    class_name = "".join(part.capitalize() for part in name.split("_"))
    print(f"created app/domains/{name}")
    print()
    print("이 앱은 디렉터리 컨벤션으로 자동 발견됩니다 — 중앙 파일 수정 불필요.")
    print(f"  - router: api/routers/router.py 의 {name}_router 가 /api 에 자동 마운트")
    print("  - models: models/ 에 ORM 모델을 두면 Base.metadata 에 자동 등록")
    if args.with_admin:
        print(f"  - admin: admin.py 의 admin_views 에 {class_name}Admin 을 추가하면 자동 노출")
    print("  - 서버 재시작 시 라우터가 마운트됩니다")
