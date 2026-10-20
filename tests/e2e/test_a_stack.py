"""하네스 자체 — 안전 검사와 스택 상태(복제·앱·워커)가 기대대로인가."""

from __future__ import annotations

import json

import httpx
import pytest

from tests.e2e.stack import PORTS, StackError, check_targets

pytestmark = pytest.mark.e2e


def _env(**changes: str) -> dict[str, str]:
    env = {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": str(PORTS["mysql-primary"]),
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": str(PORTS["redis"]),
        "MYSQL_REPLICA_HOSTS": json.dumps([f"127.0.0.1:{PORTS['mysql-replica']}"]),
    }
    env.update(changes)
    return env


@pytest.mark.parametrize(
    "changes",
    [
        {"MYSQL_HOST": "115.68.199.140"},
        {"MYSQL_PORT": "3306"},
        {"REDIS_PORT": "6379"},
        {"REDIS_HOST": "localhost"},
        {"MYSQL_REPLICA_HOSTS": '["127.0.0.1:3308"]'},
        {"ALEMBIC_DATABASE_URL": "mysql+pymysql://u:p@10.0.0.1:13321/x"},
    ],
)
def test_target_check_refuses_anything_but_the_e2e_stack(changes):
    with pytest.raises(StackError, match="중단"):
        check_targets(_env(**changes))


def test_target_check_accepts_the_e2e_stack():
    check_targets(_env())


def test_stack_is_replicating_and_serving(stack):
    status = stack.sql(
        "mysql-replica",
        "SELECT (SELECT SERVICE_STATE FROM performance_schema.replication_connection_status),"
        " (SELECT SERVICE_STATE FROM performance_schema.replication_applier_status);",
    )
    assert status.split() == ["ON", "ON"], status
    tables = {
        r["TABLE_NAME"]
        for r in stack.query(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
            ("fastapi_e2e",),
            replica=True,
        )
    }
    assert {"users", "blog_posts", "alembic_version"} <= tables, tables
    assert httpx.get(stack.base_url + "/ready", timeout=10).status_code == 200
    assert stack.worker is not None and stack.worker.alive()
