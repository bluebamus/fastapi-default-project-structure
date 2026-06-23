"""Tests for app/apps.py explicit (manual) app registration SSOT.

Verifies that the manual registration lists/functions wire up the home
domain's router, models, admin views, and Celery package correctly.
"""

from app.domains.home.api.routers.router import home_router


def test_routers_includes_home_router():
    """routers() returns a RouterSpec for the home router under /api."""
    from app.apps import RouterSpec, routers

    specs = routers()
    assert all(isinstance(s, RouterSpec) for s in specs)
    assert any(s.router is home_router and s.prefix == "/api" for s in specs)


def test_routers_registers_access_log_sink():
    """Calling routers() registers the home access-log sink (side effect)."""
    from app.apps import routers
    from app.core.middlewares.access_log_sink import get_access_log_sink
    from app.domains.home.access_log_sink import HomeAccessLogSink

    routers()
    assert isinstance(get_access_log_sink(), HomeAccessLogSink)


def test_register_models_populates_metadata():
    """register_models() imports models so user_access_logs is in Base.metadata."""
    from app.apps import register_models
    from app.core.db.session import Base

    register_models()
    assert "user_access_logs" in Base.metadata.tables


def test_admin_views_includes_user_access_log_admin():
    """admin_views() returns the UserAccessLogAdmin view class."""
    from app.apps import admin_views
    from app.domains.home.admin import UserAccessLogAdmin

    assert UserAccessLogAdmin in admin_views()


def test_celery_task_modules_includes_home():
    """CELERY_TASK_MODULES explicitly lists the home worker tasks module."""
    from app.apps import CELERY_TASK_MODULES

    assert "app.domains.home.worker.tasks" in CELERY_TASK_MODULES
