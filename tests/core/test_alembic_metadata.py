"""Test that AppRegistry populates Base.metadata with all domain models.

This guards the env.py approach: if the registry fails to import models,
autogenerate will produce an empty migration.
"""


def test_registry_populates_all_tables():
    from app.core.registry import AppRegistry
    from app.core.db.session import Base

    reg = AppRegistry()
    reg.discover()
    reg.import_models()

    assert "user_access_logs" in Base.metadata.tables
