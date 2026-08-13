"""SQL 파라미터 로그 유출 방지 — NFR-001 (F-008).

이 프로젝트의 기본값은 ``DEBUG=true`` 이고, 그러면 유효 로그 레벨이 DEBUG 가 된다.
그 상태에서 SQLAlchemy·드라이버(aiosqlite·aiomysql)는 **실행한 SQL 과 바인딩된
파라미터를 그대로** 로그로 내보낸다. 파라미터에는 비밀번호 해시·토큰·사용자 식별자가
들어 있고, 로그는 보통 외부 collector 로 흘러간다.

ADR-019(앱별 로거를 등록하지 않는다)는 유지한다. ``loggers`` 키를 추가하는 대신
queue 핸들러에 필터를 달아 해당 로거의 저레벨 레코드를 떨어뜨린다 — 핸들러는
여전히 root 에만 붙고, 경로 기반 appname 판별도 그대로다.

SQL 을 보고 싶은 개발자는 ``LOG_SQL_ECHO_ENABLED=true`` 로 명시적으로 연다.
"""

from __future__ import annotations

import logging

import pytest

from app.utils.logs.filters import SQL_NOISE_LOGGER_PREFIXES, SqlNoiseFilter


def _record(logger_name: str, level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name=logger_name,
        level=level,
        pathname="/x/app/core/db/session.py",
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


@pytest.mark.parametrize("logger_name", sorted(SQL_NOISE_LOGGER_PREFIXES))
def test_sql_emitting_loggers_are_dropped_below_warning(logger_name):
    """SQL 을 내보내는 로거의 DEBUG/INFO 레코드는 버린다."""
    log_filter = SqlNoiseFilter(allow_sql_echo=False)

    for level in (logging.DEBUG, logging.INFO):
        record = _record(logger_name, level, "INSERT INTO t VALUES ('SECRET')")
        assert log_filter.filter(record) is False, f"{logger_name} 의 {level} 레코드가 통과했다"


@pytest.mark.parametrize("logger_name", sorted(SQL_NOISE_LOGGER_PREFIXES))
def test_warnings_and_errors_from_those_loggers_still_pass(logger_name):
    """연결 실패 같은 경고·오류까지 막으면 장애를 못 본다."""
    log_filter = SqlNoiseFilter(allow_sql_echo=False)

    for level in (logging.WARNING, logging.ERROR, logging.CRITICAL):
        record = _record(logger_name, level, "connection lost")
        assert log_filter.filter(record) is True, f"{logger_name} 의 {level} 레코드가 막혔다"


def test_application_loggers_are_untouched():
    """우리 코드의 DEBUG 로그까지 막으면 안 된다."""
    log_filter = SqlNoiseFilter(allow_sql_echo=False)

    for name in ("app", "repository", "raw_repository", "database", "main"):
        record = _record(name, logging.DEBUG, "디버그 메시지")
        assert log_filter.filter(record) is True, f"{name} 로거가 막혔다"


def test_opt_in_flag_restores_sql_echo():
    """명시적으로 켠 개발자에게는 그대로 보여준다."""
    log_filter = SqlNoiseFilter(allow_sql_echo=True)

    record = _record("sqlalchemy.engine.Engine", logging.DEBUG, "SELECT 1")
    assert log_filter.filter(record) is True


def test_queue_handler_carries_the_filter():
    """필터가 dictConfig 의 queue 핸들러에 실제로 붙어 있어야 한다."""
    from app.utils.logs.config import build_dictconfig

    config = build_dictconfig()

    assert "sql_noise" in config["filters"], "sql_noise 필터가 선언되지 않았다"
    assert (
        "sql_noise" in config["handlers"]["queue"]["filters"]
    ), "queue 핸들러에 sql_noise 필터가 붙지 않았다"
    # ADR-019 는 그대로 지킨다.
    assert "loggers" not in config, "필터로 해결해야 하며 앱별 로거를 등록하지 않는다"


async def test_end_to_end_parameters_do_not_reach_handlers(caplog):
    """실제 쿼리를 돌려 파라미터가 우리 출력 경로로 흘러나오지 않는지 본다."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.logs.filters import SqlNoiseFilter

    secret = "SUPER-SECRET-TOKEN"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # 애플리케이션의 출력 경로와 같은 조건: root DEBUG + sql_noise 필터.
    caplog.handler.addFilter(SqlNoiseFilter(allow_sql_echo=False))
    try:
        with caplog.at_level(logging.DEBUG):
            async with engine.begin() as connection:
                await connection.execute(text("CREATE TABLE t (secret TEXT)"))
                await connection.execute(
                    text("INSERT INTO t (secret) VALUES (:secret)"),
                    {"secret": secret},
                )
    finally:
        await engine.dispose()

    captured = " ".join(record.getMessage() for record in caplog.records)
    assert secret not in captured, f"바인딩 파라미터가 로그로 유출됐다: {captured[:400]}"
