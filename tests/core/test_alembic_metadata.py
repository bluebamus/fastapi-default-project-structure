"""Test that app/apps.py register_models() populates Base.metadata.

This guards the env.py approach: if registration fails to import models,
autogenerate will produce an empty migration.
"""


def test_register_models_populates_all_tables():
    from app.apps import register_models
    from app.core.db.session import Base

    register_models()

    assert "user_access_logs" in Base.metadata.tables
