"""접속 URL 은 어떤 비밀번호·호스트 표기에서도 깨지지 않는다 (service-hardening ADR-004).

예전에는 f-string 으로 조립했다. 비밀번호에 ``@ : / # % ?`` 가 들어가면 구분자로 읽혀
호스트·포트·DB 이름이 엉뚱하게 갈라진다 — 테스트 기본값(빈 비밀번호)으로는 보이지 않고
**운영 비밀번호에서만** 드러나는 실패다. 여기서는 그런 비밀번호가 문자열로 펼쳤다가 다시
읽어도 그대로 돌아오는지(왕복)를 본다.
"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.engine import URL, make_url

from config import DatabaseSettings, RedisSettings

#: URL 구분자를 전부 담은 비밀번호.
NASTY = "p@ss:w/rd%#?"  # noqa: S105 - 테스트 픽스처 값


def _db(**overrides) -> DatabaseSettings:
    return DatabaseSettings(_env_file=None, **overrides)


def _roundtrip(url: URL) -> URL:
    return make_url(url.render_as_string(hide_password=False))


def test_writer_url_round_trips_a_password_with_separators() -> None:
    url = _db(MYSQL_PASSWORD=NASTY, MYSQL_HOST="db", MYSQL_PORT=3307).MYSQL_WRITER_URL

    back = _roundtrip(url)
    assert (back.password, back.host, back.port, back.database) == (NASTY, "db", 3307, "fastapi_db")


def test_replica_urls_round_trip_their_own_password() -> None:
    settings = _db(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["replica-a", "[2001:db8::10]:3307"],
        MYSQL_REPLICA_PASSWORD=NASTY,
    )

    backs = [_roundtrip(url) for url in settings.MYSQL_REPLICA_URLS]
    assert [(b.password, b.host, b.port) for b in backs] == [
        (NASTY, "replica-a", 3306),
        (NASTY, "2001:db8::10", 3307),
    ]


def test_alembic_url_swaps_only_the_driver() -> None:
    url = _db(MYSQL_PASSWORD=NASTY).ALEMBIC_URL

    assert url.drivername == "mysql+pymysql"
    assert _roundtrip(url).password == NASTY


def test_alembic_override_is_parsed_not_copied() -> None:
    url = _db(ALEMBIC_DATABASE_URL="sqlite:///./local.db").ALEMBIC_URL

    assert isinstance(url, URL)
    assert (url.drivername, url.database) == ("sqlite", "./local.db")


def test_masked_rendering_hides_the_password() -> None:
    summary = _db(
        MYSQL_PASSWORD=NASTY,
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["replica-a"],
    ).describe_routing()

    for rendered in [summary["writer"], *summary["readers"]]:
        assert "***" in rendered
        assert "p@ss" not in rendered and "p%40ss" not in rendered


def test_redis_url_round_trips_a_password_with_separators() -> None:
    settings = RedisSettings(
        _env_file=None, REDIS_PASSWORD=NASTY, REDIS_HOST="cache", REDIS_PORT=6380, REDIS_DB=2
    )

    kwargs = Redis.from_url(settings.REDIS_URL).connection_pool.connection_kwargs
    assert (kwargs["password"], kwargs["host"], kwargs["port"], kwargs["db"]) == (
        NASTY,
        "cache",
        6380,
        2,
    )
