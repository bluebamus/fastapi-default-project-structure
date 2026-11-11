"""마이그레이션 — 빈 DB 에 ``upgrade head`` 가 모델 스키마를 그대로 만들고 ``downgrade base`` 가 전부 지운다.

운영(DEBUG=false)에서는 Alembic 이 유일한 스키마 경로다. SQLite 로 돌려 외부 자원이 필요 없다.
"""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from config import db_settings


def test_upgrade_matches_models_and_downgrade_is_clean(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    # env.py 는 db_settings.ALEMBIC_URL 을 읽는다 — 이 필드가 그 오버라이드다.
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", url)
    import_all_models()
    alembic_cfg = Config("alembic.ini")
    engine = sa.create_engine(url)
    try:
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"

        command.downgrade(alembic_cfg, "base")
        assert set(sa.inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
