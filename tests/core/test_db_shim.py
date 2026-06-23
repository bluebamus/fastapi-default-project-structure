"""Regression test: old app.database.* import paths must still work via shim."""
import os
import importlib
import sys


def test_old_database_paths_still_import(monkeypatch):
    # config.py requires ENV in ('development', 'staging', 'production');
    # pyproject.toml sets ENV=test for pytest — override before any import
    # that chains into config.py.
    monkeypatch.setenv("ENV", "development")

    # Force reload of config and dependent modules so the patched ENV is seen.
    # Only needed if config was already imported with ENV=test in this session.
    for mod_name in list(sys.modules.keys()):
        if mod_name == "config" or mod_name.startswith("app.core.db") or mod_name.startswith("app.database"):
            sys.modules.pop(mod_name, None)

    from app.database.session import get_session, engine          # noqa: F401
    from app.database.unit_of_work import BaseUnitOfWork          # noqa: F401
    from app.core.db.session import get_session as new_get        # noqa: F401
    assert get_session is new_get
