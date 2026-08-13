"""공통 모델 Mixin 계약 — ORM-MDL-001/002/004.

핵심은 **모든 테이블에 같은 컬럼을 강제하지 않는다**는 것이다. 접속 로그처럼 생성 후
변하지 않는 테이블에 ``updated_at`` 을 억지로 붙이면 한 번도 갱신되지 않는 컬럼이
생겨, 읽는 사람에게 "언젠가 갱신될 수 있다"는 잘못된 신호를 준다.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db.models_registry import import_all_models
from app.core.models.models_base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDCreatedModel,
    UUIDPrimaryKeyMixin,
    UUIDTimestampModel,
)

MUTABLE_TABLES = ("blog_posts", "replies", "sns_posts", "users")
IMMUTABLE_LOG_TABLES = ("user_access_logs",)


def test_mixins_are_separately_composable():
    """세 책임이 각각 독립된 Mixin 으로 분리돼 있어야 조합할 수 있다."""
    for mixin, column_name in (
        (UUIDPrimaryKeyMixin, "id"),
        (CreatedAtMixin, "created_at"),
        (UpdatedAtMixin, "updated_at"),
    ):
        assert hasattr(mixin, column_name), f"{mixin.__name__} 이 {column_name} 을 제공하지 않는다"
        # 한 Mixin 이 두 책임을 겸하면 조합의 의미가 없다.
        others = {"id", "created_at", "updated_at"} - {column_name}
        for other in others:
            assert not hasattr(mixin, other), f"{mixin.__name__} 이 {other} 까지 갖고 있다"


def test_composed_bases_are_abstract():
    """조합 Base 는 테이블을 만들지 않는다 — 상속용이다."""
    for model in (UUIDTimestampModel, UUIDCreatedModel):
        assert model.__dict__.get("__abstract__") is True
        assert not hasattr(model, "__table__"), f"{model.__name__} 이 테이블을 만들었다"


def test_immutable_log_has_no_updated_at():
    """불변 로그 모델은 updated_at 을 강제받지 않는다 (ORM-MDL-002)."""
    import_all_models()

    for table_name in IMMUTABLE_LOG_TABLES:
        table = Base.metadata.tables[table_name]
        assert "created_at" in table.columns
        assert (
            "updated_at" not in table.columns
        ), f"{table_name} 은 생성 후 불변인데 updated_at 을 갖고 있다"


def test_mutable_entities_have_both_timestamps():
    import_all_models()

    for table_name in MUTABLE_TABLES:
        table = Base.metadata.tables[table_name]
        assert "created_at" in table.columns
        assert "updated_at" in table.columns, f"{table_name} 에 updated_at 이 없다"
        assert (
            table.columns["updated_at"].onupdate is not None
        ), f"{table_name}.updated_at 에 onupdate 가 없어 자동 갱신되지 않는다"


def test_no_independent_declarative_base_in_features():
    """기능 폴더에 별도 DeclarativeBase 가 있으면 Alembic 이 그 테이블을 못 본다."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    offenders = [
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "app" / "features").rglob("*.py")
        if "__pycache__" not in path.parts and "DeclarativeBase" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"기능 폴더에 독립 DeclarativeBase 가 있습니다: {offenders}"


def test_all_models_inherit_the_shared_base():
    """모든 기능 모델이 공통 Base 계층을 쓴다 (ORM-MDL-001)."""
    import_all_models()

    mapped_tables = set(Base.metadata.tables)
    assert (
        set(MUTABLE_TABLES) | set(IMMUTABLE_LOG_TABLES) <= mapped_tables
    ), f"공통 Base.metadata 에 등록되지 않은 모델이 있다: {mapped_tables}"


def test_column_sort_order_keeps_id_first_and_timestamps_last():
    """Mixin 을 써도 물리 컬럼 순서가 id → 고유 컬럼 → 시각 순이어야 한다.

    지정하지 않으면 Mixin 컬럼이 앞으로 몰려, create_all 로 만든 개발 DB 와
    migration 으로 만든 운영 DB 의 컬럼 순서가 갈린다.
    """
    import_all_models()

    for table_name in MUTABLE_TABLES:
        names = [column.name for column in Base.metadata.tables[table_name].columns]
        assert names[0] == "id", f"{table_name} 의 첫 컬럼이 id 가 아니다: {names}"
        assert names[-2:] == [
            "created_at",
            "updated_at",
        ], f"{table_name} 의 시각 컬럼이 맨 뒤가 아니다: {names}"

    for table_name in IMMUTABLE_LOG_TABLES:
        names = [column.name for column in Base.metadata.tables[table_name].columns]
        assert names[0] == "id"
        assert names[-1] == "created_at"


def test_mixins_work_with_an_external_primary_key():
    """외부 시스템 PK 를 쓰는 모델도 시간 Mixin 만 조합할 수 있어야 한다 (ORM-MDL-003 예외 정책)."""

    class _IsolatedBase(DeclarativeBase):
        pass

    class _ExternalKeyModel(_IsolatedBase, CreatedAtMixin, UpdatedAtMixin):
        __tablename__ = "external_key_probe"

        external_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    columns = [c.name for c in _ExternalKeyModel.__table__.columns]
    assert columns == ["external_id", "created_at", "updated_at"]
    assert _ExternalKeyModel.__table__.primary_key.columns.keys() == ["external_id"]
