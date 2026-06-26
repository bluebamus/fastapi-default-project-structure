"""Tests for scripts/new_app.py scaffolding generator."""



def test_generator_creates_bootable_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    # run generator pointed at temp root
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    assert (tmp_path / "app/domains/widget/api/routers/router.py").exists()


def test_generator_creates_config(tmp_path, monkeypatch):
    """config.py with an AppConfig subclass is generated for auto-discovery."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "domains").mkdir(parents=True)
    from scripts.new_app import scaffold

    scaffold("widget", root=tmp_path, category="domain")

    config_path = tmp_path / "app/domains/widget/config.py"
    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    assert "class WidgetConfig(AppConfig):" in config_text
    assert 'name = "widget"' in config_text


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
