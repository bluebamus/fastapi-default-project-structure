"""마이그레이션 체인이 빈 DB에서 끝까지 적용되는지 검증 (2026-08-10 외부 검수 후속 P4-2).

baseline 이 user_access_logs 하나만 만들고 나머지 도메인 테이블을 통째로 빠뜨려,
다음 리비전이 존재하지 않는 users 를 ALTER 하며 체인이 끊겨 있었다. DEBUG 모드의
create_db_tables() 가 이 결함을 가려왔다 — 운영(DEBUG=false)에서는 Alembic 이
유일한 스키마 경로이므로 배포가 불가능한 상태였다.

같은 사고가 다시 나지 않도록, 실제로 빈 DB에 `upgrade head` 를 돌려 결과 스키마가
모델과 일치하는지까지 확인한다. SQLite 로 실행하므로 외부 인프라가 필요 없다.
"""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from config import db_settings

_EXPECTED_TABLES = {
    "user_access_logs",
    "users",
    "blog_posts",
    "replies",
    "sns_posts",
    # 데이터 접근 방식 참조 예제 (Phase 5)
    "catalog_products",
    "sales_orders",
}


def _upgrade_to_head(tmp_path, monkeypatch) -> sa.Engine:
    """빈 SQLite DB를 만들고 마이그레이션을 head 까지 적용한다."""
    url = f"sqlite:///{(tmp_path / 'chain.db').as_posix()}"
    # env.py 가 db_settings.ALEMBIC_URL 을 읽는다. 이 필드를 바꾸면 그대로 반영된다.
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", url)

    command.upgrade(Config("alembic.ini"), "head")
    return sa.create_engine(url)


def test_upgrade_head_succeeds_on_empty_database(tmp_path, monkeypatch):
    """빈 DB에서 upgrade head 가 성공하고, 모든 도메인 테이블이 생성된다."""
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"마이그레이션이 생성하지 않은 테이블: {sorted(missing)}"


def test_hashed_password_column_is_added_by_its_own_revision(tmp_path, monkeypatch):
    """users.hashed_password 는 후속 리비전이 추가한다.

    baseline 에 미리 넣으면 b2f1a9c0d3e4 리비전이 무의미해진다. 보정 시 실수로
    합쳐넣지 않았는지 확인한다.
    """
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        columns = {c["name"] for c in sa.inspect(engine).get_columns("users")}
    finally:
        engine.dispose()

    assert "hashed_password" in columns


def test_migrated_schema_matches_models(tmp_path, monkeypatch):
    """마이그레이션 결과가 모델 metadata 와 일치한다(드리프트 없음).

    테이블이 생기기만 하고 컬럼이 어긋나면 운영에서 늦게 터진다.
    """
    import_all_models()
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"


def test_percent_in_url_survives_alembic_config(tmp_path, monkeypatch):
    """URL 의 `%` 가 Alembic Config(ConfigParser 보간)에서 터지지 않는다 (service-hardening ADR-004).

    퍼센트 인코딩된 비밀번호(`p%40ss`)나 경로의 `%` 를 그대로 `set_main_option` 에 넘기면
    `invalid interpolation syntax` 로 마이그레이션이 시작도 못 한다. `migrations/env.py` 가
    `%%` 로 바꿔 넘기는지를 실제 upgrade 로 확인한다.
    """
    directory = tmp_path / "50%off"
    directory.mkdir()
    engine = _upgrade_to_head(directory, monkeypatch)
    try:
        assert "users" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_alembic_check_reports_no_drift_through_env(tmp_path, monkeypatch):
    """``alembic check`` 가 ``migrations/env.py``(비교·렌더 훅 포함)를 거쳐 드리프트 없음을 낸다.

    ``compare_metadata`` 직접 호출은 env.py 를 지나지 않는다. SQLite 에서는 훅이 없어도 드리프트가
    없으므로, env.py 가 훅을 실제로 넘기는지도 ``configure`` 호출 인자로 확인한다 — MySQL 에서
    ``DATETIME``(fsp 0) 을 드리프트로 잡는 것은 그 훅이다(service-hardening ADR-010).
    """
    from alembic.runtime.environment import EnvironmentContext

    from app.core.models.types import compare_type, render_item

    engine = _upgrade_to_head(tmp_path, monkeypatch)
    engine.dispose()

    seen: dict = {}
    original = EnvironmentContext.configure

    def _spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(EnvironmentContext, "configure", _spy)
    command.check(Config("alembic.ini"))

    assert seen.get("compare_type") is compare_type
    assert seen.get("render_item") is render_item
