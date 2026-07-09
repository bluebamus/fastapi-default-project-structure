""".env 파일이 DB 라우터를 실제로 켜고 끄는지, 켠 뒤 읽기/쓰기가 서로 다른 서버로
갈리는지 검증한다.

세션 팩토리는 `app.core.db.session` 을 **import 하는 시점**에 .env 값을 보고 결정된다.
따라서 이미 import 된 프로세스 안에서는 검증할 수 없다. 각 시나리오마다 임시 디렉터리에
.env 를 쓰고 그 디렉터리를 CWD 로 하는 **자식 파이썬 프로세스**를 띄워, 그 안에서 배선
결과와 라우팅 판정을 관찰해 JSON 으로 돌려받는다.

라우팅 판정(`Session.get_bind`)은 커넥션을 열지 않으므로 살아있는 MySQL 서버 없이도
"이 구문이 어느 서버로 나갈지"를 그대로 확인할 수 있다.
"""

import json
import os
import subprocess  # noqa: S404 - 테스트 하네스가 의도적으로 자식 프로세스를 띄운다
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 자식 프로세스에서 실행할 관찰 스크립트.
# import 된 세션 모듈의 배선(엔진·세션 클래스)과, SELECT / INSERT 각각이 바인딩되는
# 엔진을 조사해 리포트로 출력한다.
PROBE = r"""
import json

import sqlalchemy as sa

from app.core.db.session import AsyncSessionLocal, engine, read_engines
from config import db_settings

# 라우팅 판정에만 쓰는 더미 테이블 (실제 DB 접속 없음)
probe = sa.Table("routing_probe", sa.MetaData(), sa.Column("id", sa.Integer))

session = AsyncSessionLocal()
sync = session.sync_session

# 순서가 중요하다: SELECT(→reader) → INSERT(→writer, sticky 설정) → SELECT(→writer 고정)
select_bind = sync.get_bind(clause=sa.select(probe))
insert_bind = sync.get_bind(clause=sa.insert(probe))
sticky_bind = sync.get_bind(clause=sa.select(probe))

report = {
    "mode": db_settings.routing_mode,
    "router_enabled": db_settings.DB_ROUTER_ENABLED,
    "replication_enabled": db_settings.DB_REPLICATION_ENABLED,
    "routing_session": type(sync).__name__ == "RoutingSession",
    "writer": [engine.url.host, engine.url.port],
    "readers": [[e.url.host, e.url.port] for e in read_engines],
    "select": [select_bind.url.host, select_bind.url.port],
    "insert": [insert_bind.url.host, insert_bind.url.port],
    "sticky_select": [sticky_bind.url.host, sticky_bind.url.port],
}
print("__REPORT__" + json.dumps(report))
"""

# 모든 시나리오 공통 .env 머리말 — 로그 출력이 리포트를 어지럽히지 않도록 끈다.
ENV_HEADER = """
LOG_CONSOLE_ENABLED=false
LOG_FILE_ENABLED=false
MYSQL_HOST=primary.example.com
MYSQL_PORT=3306
MYSQL_USER=app
MYSQL_DATABASE=shop
"""


def _run_probe(tmp_path: Path, env_body: str) -> subprocess.CompletedProcess[str]:
    """`env_body` 를 .env 로 쓴 임시 디렉터리에서 관찰 스크립트를 실행한다."""
    (tmp_path / ".env").write_text(ENV_HEADER + env_body, encoding="utf-8")

    child_env = os.environ.copy()
    # 부모(pytest) 프로세스의 DB_* / MYSQL_* 환경변수가 .env 를 덮어쓰지 않도록 제거한다.
    # (환경변수가 .env 보다 우선순위가 높다 — 이 테스트는 .env 만의 효과를 본다)
    for key in list(child_env):
        if key.startswith(("DB_", "MYSQL_")):
            del child_env[key]
    child_env["PYTHONPATH"] = str(PROJECT_ROOT)

    # 인터프리터·스크립트가 모두 이 파일 안에 고정되어 있고 셸을 거치지 않는다.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", PROBE],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _report(tmp_path: Path, env_body: str) -> dict:
    """관찰 스크립트를 실행하고 리포트를 파싱한다."""
    proc = _run_probe(tmp_path, env_body)
    assert proc.returncode == 0, f"자식 프로세스 실패:\n{proc.stdout}\n{proc.stderr}"

    for line in proc.stdout.splitlines():
        if line.startswith("__REPORT__"):
            return json.loads(line.removeprefix("__REPORT__"))
    raise AssertionError(f"리포트를 찾지 못했습니다:\n{proc.stdout}\n{proc.stderr}")


# =============================================================================
# .env 로 라우터를 켜고 끄기
# =============================================================================
def test_env_without_router_uses_single_server(tmp_path):
    """.env 에 라우터 설정이 없으면 모든 쿼리가 단일 서버로 나간다."""
    report = _report(tmp_path, "")

    assert report["mode"] == "single"
    assert report["routing_session"] is False
    assert report["readers"] == []
    # 읽기·쓰기 모두 primary
    assert report["select"] == ["primary.example.com", 3306]
    assert report["insert"] == ["primary.example.com", 3306]


def test_env_router_enabled_without_replication_stays_on_primary(tmp_path):
    """라우터만 켜고 복제를 끄면 라우팅은 동작하되 갈 곳이 primary 뿐이다."""
    report = _report(tmp_path, "DB_ROUTER_ENABLED=true\n")

    assert report["mode"] == "router-single"
    assert report["routing_session"] is True
    assert report["readers"] == []
    assert report["select"] == ["primary.example.com", 3306]
    assert report["insert"] == ["primary.example.com", 3306]


def test_env_router_disabled_ignores_replica_hosts(tmp_path):
    """라우터가 꺼져 있으면 replica 를 적어두어도 엔진을 만들지 않는다."""
    report = _report(
        tmp_path,
        'DB_ROUTER_ENABLED=false\nMYSQL_REPLICA_HOSTS=["10.0.0.11"]\n',
    )

    assert report["mode"] == "single"
    assert report["routing_session"] is False
    assert report["readers"] == []


# =============================================================================
# 라우터 활성화 후 읽기/쓰기 분기 — 서버가 IP 인 경우
# =============================================================================
def test_env_replication_splits_reads_and_writes_by_ip(tmp_path):
    """복제를 켜면 SELECT 는 replica IP 로, 쓰기는 primary 로 나간다."""
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        'MYSQL_REPLICA_HOSTS=["10.0.0.11"]\n',
    )

    assert report["mode"] == "router-replicated"
    assert report["routing_session"] is True
    assert report["readers"] == [["10.0.0.11", 3306]]

    assert report["select"] == ["10.0.0.11", 3306]  # 읽기 → replica
    assert report["insert"] == ["primary.example.com", 3306]  # 쓰기 → primary


# =============================================================================
# 라우터 활성화 후 읽기/쓰기 분기 — 서버가 도메인인 경우
# =============================================================================
def test_env_replication_splits_reads_and_writes_by_domain(tmp_path):
    """replica 를 도메인으로 지정해도 동일하게 분기한다."""
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        'MYSQL_REPLICA_HOSTS=["replica.example.com"]\n',
    )

    assert report["readers"] == [["replica.example.com", 3306]]
    assert report["select"] == ["replica.example.com", 3306]
    assert report["insert"] == ["primary.example.com", 3306]


def test_env_replication_mixes_ip_domain_and_explicit_ports(tmp_path):
    """IP·도메인·명시 포트를 섞어 쓸 수 있다."""
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        'MYSQL_REPLICA_HOSTS=["10.0.0.11", "replica.example.com:3307", "[2001:db8::10]:3308"]\n',
    )

    assert report["readers"] == [
        ["10.0.0.11", 3306],  # 포트 생략 → MYSQL_REPLICA_PORT
        ["replica.example.com", 3307],  # 도메인 + 명시 포트
        ["2001:db8::10", 3308],  # IPv6(대괄호) + 명시 포트
    ]
    # 첫 세션은 라운드로빈 첫 번째 replica 를 받는다
    assert report["select"] == ["10.0.0.11", 3306]
    assert report["insert"] == ["primary.example.com", 3306]


def test_env_replica_default_port_is_configurable(tmp_path):
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        "MYSQL_REPLICA_PORT=4000\n"
        'MYSQL_REPLICA_HOSTS=["10.0.0.11", "replica.example.com"]\n',
    )

    assert report["readers"] == [["10.0.0.11", 4000], ["replica.example.com", 4000]]


# =============================================================================
# 복제 지연 대비 — 쓰기 이후 읽기는 primary 로 고정
# =============================================================================
def test_env_read_after_write_sticks_to_primary(tmp_path):
    """쓰기가 일어난 세션의 이후 SELECT 는 primary 로 고정된다."""
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        'MYSQL_REPLICA_HOSTS=["10.0.0.11"]\n',
    )

    assert report["select"] == ["10.0.0.11", 3306]  # 쓰기 전 읽기 → replica
    assert report["insert"] == ["primary.example.com", 3306]  # 쓰기 → primary
    assert report["sticky_select"] == ["primary.example.com", 3306]  # 쓰기 후 읽기 → primary


def test_env_sticky_can_be_disabled(tmp_path):
    """DB_READ_STICKY_AFTER_WRITE=false 면 쓰기 이후 읽기도 replica 로 돌아간다."""
    report = _report(
        tmp_path,
        "DB_ROUTER_ENABLED=true\n"
        "DB_REPLICATION_ENABLED=true\n"
        "DB_READ_STICKY_AFTER_WRITE=false\n"
        'MYSQL_REPLICA_HOSTS=["10.0.0.11"]\n',
    )

    assert report["insert"] == ["primary.example.com", 3306]
    assert report["sticky_select"] == ["10.0.0.11", 3306]


# =============================================================================
# 잘못된 .env 는 기동 시점에 차단된다
# =============================================================================
@pytest.mark.parametrize(
    ("env_body", "expected"),
    [
        # 복제만 켜고 라우터를 끔
        (
            'DB_REPLICATION_ENABLED=true\nMYSQL_REPLICA_HOSTS=["10.0.0.11"]\n',
            "DB_ROUTER_ENABLED",
        ),
        # 복제를 켰는데 replica 가 없음
        ("DB_ROUTER_ENABLED=true\nDB_REPLICATION_ENABLED=true\n", "MYSQL_REPLICA_HOSTS"),
        # 대괄호 없는 IPv6
        (
            "DB_ROUTER_ENABLED=true\nDB_REPLICATION_ENABLED=true\n"
            'MYSQL_REPLICA_HOSTS=["2001:db8::10"]\n',
            "대괄호",
        ),
    ],
)
def test_invalid_env_fails_fast_at_startup(tmp_path, env_body, expected):
    """모순된 .env 조합은 조용히 무시하지 않고 애플리케이션 기동을 막는다."""
    proc = _run_probe(tmp_path, env_body)

    assert proc.returncode != 0, f"기동이 차단되지 않았습니다:\n{proc.stdout}"
    assert expected in proc.stderr
