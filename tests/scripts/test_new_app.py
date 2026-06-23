"""Tests for scripts/new_app.py scaffolding generator."""

import pathlib


def test_generator_creates_bootable_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    # run generator pointed at temp root
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert (tmp_path / "app/domains/widget/config.py").exists()
    assert (tmp_path / "app/domains/widget/api/routers/router.py").exists()


def test_generator_config_is_parameterized(tmp_path, monkeypatch):
    """Generated config.py must contain the correct class name and app name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    config_text = (tmp_path / "app/domains/widget/config.py").read_text(encoding="utf-8")
    assert "class WidgetConfig(AppConfig)" in config_text
    assert 'name = "widget"' in config_text


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
    assert (base / "unit_of_work.py").exists()


def test_generator_optional_worker(tmp_path, monkeypatch):
    """--with-worker flag creates worker/tasks.py."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, with_worker=True)

    assert (tmp_path / "app/domains/widget/worker/tasks.py").exists()
    assert (tmp_path / "app/domains/widget/worker/__init__.py").exists()


def test_generator_optional_admin(tmp_path, monkeypatch):
    """--with-admin flag creates admin.py."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, with_admin=True)

    assert (tmp_path / "app/domains/widget/admin.py").exists()


def test_generator_no_worker_by_default(tmp_path, monkeypatch):
    """worker/ is NOT created unless with_worker=True."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path)

    assert not (tmp_path / "app/domains/widget/worker").exists()
