"""Test that AppRegistry auto-discovery populates Base.metadata.

This guards the env.py approach: if discovery/import fails to import models,
autogenerate will produce an empty migration.
"""


def test_register_models_populates_all_tables():
    from app.core.db.session import Base
    from app.core.registry import AppRegistry

    reg = AppRegistry()
    reg.discover()
    reg.import_models()

    assert "user_access_logs" in Base.metadata.tables
