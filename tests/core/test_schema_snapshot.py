"""DB 스키마 불변 안전망 — ORM-MDL-002 / NFR-005.

모델을 Mixin 으로 정리하는 리팩토링은 **스키마를 한 글자도 바꾸지 않아야** 한다.
바뀌면 이미 배포된 DB 와 어긋나고, Alembic 이 뜬금없는 migration 을 만들어낸다.

여기서는 DB 없이 ``Base.metadata`` 에서 지문(fingerprint)을 뽑아 커밋된 스냅샷과
비교한다. 컬럼 **순서**까지 본다 — 순서가 바뀌면 ``create_all`` 로 만든 개발 DB 와
migration 으로 만든 운영 DB 의 물리 구조가 갈라진다.

의도적으로 스키마를 바꿀 때는 migration 을 먼저 쓰고, 그 다음 스냅샷을 갱신한다::

    python tests/core/test_schema_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).with_name("schema_snapshot.json")


def build_schema_fingerprint() -> dict[str, Any]:
    """등록된 모든 테이블의 구조를 결정적인 dict 로 만든다."""
    from app.core.db.models_registry import import_all_models
    from app.core.db.session import Base

    import_all_models()

    fingerprint: dict[str, Any] = {}
    for table_name in sorted(Base.metadata.tables):
        table = Base.metadata.tables[table_name]
        fingerprint[table_name] = {
            # 순서가 의미를 갖는다 — 정렬하지 않는다.
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    # str(DateTime(timezone=True)) 는 "DATETIME" 으로만 찍혀 timezone
                    # 여부가 지문에서 사라진다. 속성을 따로 담는다.
                    "timezone": getattr(column.type, "timezone", None),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "unique": bool(column.unique),
                    "index": bool(column.index),
                    "has_default": column.default is not None,
                    "has_onupdate": column.onupdate is not None,
                    "comment": column.comment,
                }
                for column in table.columns
            ],
            "indexes": sorted(
                (
                    {
                        "name": index.name,
                        "unique": bool(index.unique),
                        "columns": sorted(c.name for c in index.columns),
                    }
                    for index in table.indexes
                ),
                key=lambda spec: spec["name"] or "",
            ),
            "primary_key": [c.name for c in table.primary_key.columns],
        }
    return fingerprint


def test_schema_matches_committed_snapshot():
    """모델 구조가 커밋된 스냅샷과 정확히 일치해야 한다."""
    assert SNAPSHOT_PATH.exists(), (
        f"스키마 스냅샷이 없습니다: {SNAPSHOT_PATH}. "
        "python tests/core/test_schema_snapshot.py 로 생성하세요."
    )

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    actual = build_schema_fingerprint()

    assert set(actual) == set(expected), (
        f"테이블 집합이 달라졌습니다. 추가={sorted(set(actual) - set(expected))} "
        f"제거={sorted(set(expected) - set(actual))}"
    )

    for table_name in sorted(expected):
        assert actual[table_name]["columns"] == expected[table_name]["columns"], (
            f"'{table_name}' 의 컬럼 정의/순서가 달라졌습니다.\n"
            f"  기대: {json.dumps(expected[table_name]['columns'], ensure_ascii=False)}\n"
            f"  실제: {json.dumps(actual[table_name]['columns'], ensure_ascii=False)}\n"
            "스키마를 의도적으로 바꿨다면 migration 을 먼저 쓰고 스냅샷을 갱신하세요."
        )
        assert (
            actual[table_name]["indexes"] == expected[table_name]["indexes"]
        ), f"'{table_name}' 의 인덱스가 달라졌습니다."
        assert (
            actual[table_name]["primary_key"] == expected[table_name]["primary_key"]
        ), f"'{table_name}' 의 기본키가 달라졌습니다."


def test_every_table_has_a_primary_key():
    """PK 없는 테이블은 ORM 이 매핑할 수 없고 복제·백업에서도 문제가 된다."""
    fingerprint = build_schema_fingerprint()
    missing = [name for name, spec in fingerprint.items() if not spec["primary_key"]]
    assert not missing, f"기본키가 없는 테이블: {missing}"


def test_timestamp_columns_are_timezone_aware():
    """시각 컬럼은 timezone-aware 여야 한다 (naive 저장은 TZ 사고의 근원)."""
    fingerprint = build_schema_fingerprint()
    offenders = [
        f"{table}.{column['name']}"
        for table, spec in fingerprint.items()
        for column in spec["columns"]
        if column["name"].endswith("_at") and column["timezone"] is not True
    ]
    assert not offenders, f"timezone 정보가 없는 시각 컬럼: {offenders}"


if __name__ == "__main__":  # pragma: no cover - 스냅샷 갱신 도구
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    SNAPSHOT_PATH.write_text(
        json.dumps(build_schema_fingerprint(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"스키마 스냅샷 갱신: {SNAPSHOT_PATH}")
