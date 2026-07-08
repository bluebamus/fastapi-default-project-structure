"""
scripts/new_app.py — FastAPI app scaffolding generator (표준 배선).

Django-style ``startapp`` equivalent. 표준 FastAPI 구조를 따르는 도메인 앱을 생성한다:
각 앱 패키지의 ``__init__.py`` 가 하위 뷰 라우터를 취합한 ``router`` 를 공개하고,
``main.py`` 가 이를 ``include_router`` 로 최종 취합한다.

컨벤션 (생성되는 구조):
    app/domains/<name>/
        __init__.py             →  router(+admin_views) 재노출
        api/routers/router.py   →  <name>_router: APIRouter   (하위 v1 라우터 취합)
        api/routers/v1/         →  버전별 서브라우터 위치
        models/                 →  ORM 모델 (Base.metadata 등록 — __init__ 에서 import)
        schemas/ services/ repositories/ dependencies/ tests/
        admin.py (선택)         →  admin_views: list[type]

생성 후 등록 (수동 — 표준 방식):
    main.py 의 ``from app.domains import ...`` 와 ``APPS`` 목록에 <name> 을 추가한다.
    (모델을 만들었다면 __init__.py 의 models import 주석을 해제한다.)

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

컨벤션: 이 모듈의 ``{name}_router`` 를 패키지 ``__init__.py`` 가 ``router`` 로 재노출하고
main.py 가 /api 에 마운트한다. 버전별 서브라우터를 여기에 include 한다. 예:
    from app.domains.{name}.api.routers.v1 import {name} as {name}_v1
    {name}_router.include_router({name}_v1.router, prefix="/v1/{name}", tags=["{Class}"])
"""

from fastapi import APIRouter

{name}_router = APIRouter()
'''

_INIT_TMPL = '''\
"""{Class} 도메인 패키지.

하위 뷰 라우터를 취합한 ``router`` 를 공개한다. main.py 의 APPS 목록에 이 패키지를
추가하면 ``include_router`` 로 /api 에 취합된다.

모델을 추가하면 아래 import 주석을 해제해 ``Base.metadata`` 에 등록한다:
    from app.domains.{name}.models import models as _models  # noqa: F401
"""
from app.domains.{name}.api.routers.router import {name}_router as router

__all__ = ["router"]
'''

_INIT_ADMIN_TMPL = '''\
"""{Class} 도메인 패키지.

하위 뷰 라우터를 취합한 ``router`` 와 ``admin_views`` 를 공개한다. main.py 의 APPS
목록에 이 패키지를 추가하면 라우터가 /api 에, admin_views 가 SQLAdmin 에 등록된다.

모델을 추가하면 아래 import 주석을 해제해 ``Base.metadata`` 에 등록한다:
    from app.domains.{name}.models import models as _models  # noqa: F401
"""
from app.domains.{name}.admin import admin_views
from app.domains.{name}.api.routers.router import {name}_router as router

__all__ = ["router", "admin_views"]
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

컨벤션: 모듈 레벨 ``admin_views`` 리스트를 패키지 ``__init__.py`` 가 재노출하면
main.py 가 SQLAdmin 에 등록한다.

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
        생성된 앱은 main.py 의 ``APPS`` 목록에 <name> 을 추가해야 취합된다(표준 방식).
    """
    class_name = "".join(part.capitalize() for part in name.split("_"))
    base = root / "app" / "domains" / name

    # Create required directory tree; each segment gets an __init__.py.
    for rel in _REQUIRED_DIRS:
        full = base / rel
        full.mkdir(parents=True, exist_ok=True)
        _touch_init_chain(base, rel)

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

    # App root __init__.py — 라우터(+admin_views) 를 재노출 (router.py/admin.py 작성 후)
    init_tmpl = _INIT_ADMIN_TMPL if with_admin else _INIT_TMPL
    (base / "__init__.py").write_text(
        init_tmpl.format(name=name, Class=class_name),
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
        description="Scaffold a new FastAPI domain app (standard include_router wiring).",
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
    print("등록하려면 main.py 를 수정하세요 (표준 방식):")
    print(f"  1) from app.domains import ... , {name}")
    print(f"  2) APPS = [..., {name}]   # 라우터가 /api 에 취합됨")
    print(f"  - router: api/routers/router.py 의 {name}_router 를 __init__.py 가 재노출")
    print(
        "  - models: models/ 에 ORM 모델 추가 후 __init__.py 의 import 주석 해제 (Base.metadata 등록)"
    )
    if args.with_admin:
        print(
            f"  - admin: admin.py 의 admin_views 에 {class_name}Admin 을 추가하면 SQLAdmin 에 노출"
        )
    print("  - 서버 재시작 시 라우터가 마운트됩니다")
