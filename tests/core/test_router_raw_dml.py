"""Raw ``text()`` DML 의 쓰기 판정 — RAW-REP-007 (F-011).

``TextClause`` 는 ``UpdateBase`` 가 아니라서, 타입만 보면 Raw DML 이 읽기로 분류된다.
그러면 두 가지가 깨진다:

    1. read-only 세션의 쓰기 차단이 뚫린다.
    2. 복제가 켜져 있으면 **UPDATE 가 replica 로 나간다.**

두 번째가 더 위험하다 — 조용히 잘못된 서버로 쓰기가 간다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db.router import _is_write


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "REPLACE INTO t VALUES (1)",
        "TRUNCATE TABLE t",
        "CREATE TABLE t (a INT)",
        "DROP TABLE t",
        "ALTER TABLE t ADD COLUMN b INT",
        "  \n  update t set a = 1",
        "-- 주석\nDELETE FROM t",
        "/* 블록 주석 */ UPDATE t SET a = 1",
        "SELECT * FROM t FOR UPDATE",
    ],
)
def test_raw_write_statements_are_detected(sql):
    assert _is_write(text(sql), flushing=False) is True, f"쓰기로 판정되지 않았다: {sql}"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM t WHERE a = :a",
        "  \n SELECT count(*) FROM t",
        "-- 주석\nSELECT 1",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SHOW TABLES",
    ],
)
def test_read_statements_are_not_detected_as_writes(sql):
    assert _is_write(text(sql), flushing=False) is False, f"읽기가 쓰기로 판정됐다: {sql}"


def test_orm_flush_is_always_a_write():
    assert _is_write(None, flushing=True) is True


def test_core_dml_is_still_detected():
    from sqlalchemy import Column, Integer, MetaData, Table, delete

    table = Table("probe", MetaData(), Column("id", Integer, primary_key=True))
    assert _is_write(delete(table), flushing=False) is True


# ---------------------------------------------------------------------------
# 선두 키워드 집합 보강 — 10억 건(1,022,185,501) 프로덕션 쿼리 덤프 실측 근거.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "LOAD DATA INFILE '/tmp/x.csv' INTO TABLE t",
        "load data local infile '/tmp/x.csv' into table t",
        "PREPARE s FROM 'INSERT INTO t VALUES (1)'",
        "EXECUTE s",
        "DEALLOCATE PREPARE s",
        "LOCK TABLES t WRITE",
        "UNLOCK TABLES",
        "FLUSH TABLES",
        "OPTIMIZE TABLE t",
        "REPAIR TABLE t",
        "ANALYZE TABLE t",
        "CHECK TABLE t",
        "KILL 12345",
        "DO SLEEP(0)",
    ],
)
def test_added_write_keywords_are_detected(sql):
    """추가된 13개 키워드는 쓰기(=writer 필수)로 판정된다."""
    assert _is_write(text(sql), flushing=False) is True, f"쓰기로 판정되지 않았다: {sql}"


def test_upsert_is_not_a_keyword():
    """`UPSERT` 는 MySQL·PostgreSQL 어느 방언에도 없는 구문이라 집합에서 뺐다."""
    from app.core.db.router import _TEXT_WRITE_KEYWORDS

    assert "UPSERT" not in _TEXT_WRITE_KEYWORDS
    assert _is_write(text("UPSERT INTO t VALUES (1)"), flushing=False) is False


def test_explain_analyze_is_still_a_read():
    """`EXPLAIN ANALYZE` 는 EXPLAIN 으로 시작하므로 ANALYZE 추가와 충돌하지 않는다."""
    assert _is_write(text("EXPLAIN ANALYZE SELECT * FROM t"), flushing=False) is False
