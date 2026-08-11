"""Tests for scripts/new_app.py scaffolding generator (convention-based, gen-2)."""

import pytest

_MAIN_STUB = """\
from fastapi import FastAPI

from app.domains import auth, blog, home

APPS = [home, blog, auth]

app = FastAPI()
"""


def _make_root(tmp_path):
    (tmp_path / "app" / "domains").mkdir(parents=True)
    (tmp_path / "main.py").write_text(_MAIN_STUB, encoding="utf-8")
    return tmp_path


def test_generator_creates_bootable_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    # run generator pointed at temp root
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert (tmp_path / "app/domains/widget/api/routers/router.py").exists()


def test_generator_no_config_py(tmp_path, monkeypatch):
    """컨벤션 기반이므로 config.py 는 생성하지 않는다(디렉터리=앱 선언)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert not (tmp_path / "app/domains/widget/config.py").exists()


def test_generator_router_is_parameterized(tmp_path, monkeypatch):
    """Generated router.py must contain the correct router variable name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    router_text = (tmp_path / "app/domains/widget/api/routers/router.py").read_text(
        encoding="utf-8"
    )
    assert "widget_router = APIRouter()" in router_text


def test_generator_creates_all_required_dirs(tmp_path, monkeypatch):
    """All required subdirectories and __init__.py files are created."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path)

    base = tmp_path / "app" / "domains" / "widget"
    assert (base / "__init__.py").exists()
    assert (base / "models" / "__init__.py").exists()
    assert (base / "schemas" / "__init__.py").exists()
    assert (base / "services" / "__init__.py").exists()
    assert (base / "repositories" / "__init__.py").exists()
    assert (base / "tests" / "__init__.py").exists()
    assert (base / "api" / "routers" / "v1" / "__init__.py").exists()
    assert (base / "dependencies" / "__init__.py").exists()
    assert (base / "dependencies" / "widget_dependencies.py").exists()


def test_generator_optional_admin(tmp_path, monkeypatch):
    """--with-admin flag creates admin.py with an admin_views list."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, with_admin=True)

    admin_path = tmp_path / "app/domains/widget/admin.py"
    assert admin_path.exists()
    assert "admin_views" in admin_path.read_text(encoding="utf-8")


def test_generator_no_worker_dir(tmp_path, monkeypatch):
    """worker/ 는 더 이상 생성하지 않는다(app/celery 가 대체)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path)

    assert not (tmp_path / "app/domains/widget/worker").exists()


def test_generator_multiword_pascal_case(tmp_path, monkeypatch):
    """Multi-word snake_case names are converted to proper PascalCase class names."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("user_profile", root=tmp_path, category="domain", with_admin=True)

    admin_text = (tmp_path / "app/domains/user_profile/admin.py").read_text(encoding="utf-8")
    assert "UserProfileModel" in admin_text
    assert "UserProfileAdmin" in admin_text
    router_text = (tmp_path / "app/domains/user_profile/api/routers/router.py").read_text(
        encoding="utf-8"
    )
    assert "user_profile_router = APIRouter()" in router_text


# ---------------------------------------------------------------------------
# --register (P2-2)
# ---------------------------------------------------------------------------


def test_register_adds_import_and_apps_entry(tmp_path):
    """--register 는 main.py 의 import 와 APPS 양쪽을 갱신한다."""
    root = _make_root(tmp_path)
    from scripts.new_app import register_app

    assert register_app("orders", root=root) is True

    text = (root / "main.py").read_text(encoding="utf-8")
    assert "from app.domains import auth, blog, home, orders" in text
    assert "APPS = [home, blog, auth, orders]" in text


def test_register_is_idempotent(tmp_path):
    """두 번 실행해도 중복 등록되지 않는다 — 계획서 P2-2 완료 조건."""
    root = _make_root(tmp_path)
    from scripts.new_app import register_app

    register_app("orders", root=root)
    first = (root / "main.py").read_text(encoding="utf-8")

    assert register_app("orders", root=root) is False
    assert (root / "main.py").read_text(encoding="utf-8") == first
    assert first.count("orders") == 2  # import 1회 + APPS 1회


def test_register_keeps_imports_sorted(tmp_path):
    """import 목록은 정렬 상태를 유지한다(ruff isort 게이트 통과용)."""
    root = _make_root(tmp_path)
    from scripts.new_app import register_app

    register_app("aardvark", root=root)

    text = (root / "main.py").read_text(encoding="utf-8")
    assert "from app.domains import aardvark, auth, blog, home" in text


def test_register_fails_loudly_on_unknown_wiring(tmp_path):
    """등록 지점을 못 찾으면 조용히 넘어가지 않고 멈춘다."""
    root = tmp_path
    (root / "app" / "domains").mkdir(parents=True)
    (root / "main.py").write_text("app = FastAPI()\n", encoding="utf-8")
    from scripts.new_app import register_app

    with pytest.raises(RuntimeError, match="찾지 못했다"):
        register_app("orders", root=root)
