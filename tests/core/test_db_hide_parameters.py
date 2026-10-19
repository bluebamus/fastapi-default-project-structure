"""DB 오류 문자열·로그에 바인드 값이 실리지 않는다 — ``hide_parameters=True`` 회귀 (security-ops-hardening ADR-001).

앱의 엔진 생성 지점(writer·replica·background)은 모두 ``app/core/db/session.py`` 에 있고 셋 다
``hide_parameters=True`` 다. 여기서는 (a) 실제 SQLite 무결성 오류의 예외 문자열, (b) 앱 엔진 객체의 계약,
(c) 앱 로그 파이프라인(sql_noise·redact 필터 + 앱 포맷터)으로 ``logger.exception`` 한 출력을 본다.
(a)·(c) 의 엔진은 **앱 writer 엔진의 설정값을 그대로** 받는다 — 앱에서 옵션을 빼면 여기서 값이 드러난다.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import session as session_module
from app.utils.logs.config import LOG_FORMAT
from app.utils.logs.filters import RedactingFilter, SqlNoiseFilter
from app.utils.logs.formatters import TzFormatter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMAIL = "hide-params-7c1e@example.com"
HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2VjcmV0LXNhbHQ$9f8e7d6c5b4a"


def _app_engines():
    return {
        "writer": session_module.engine,
        "background": session_module.background_engine,
        **{f"reader#{i}": e for i, e in enumerate(session_module.read_engines)},
        # 복제가 꺼져 있어도 replica 생성 경로를 본다.
        "reader-factory": session_module._create_read_engine(
            session_module.db_settings.MYSQL_WRITER_URL
        ),
    }


async def _integrity_error() -> IntegrityError:
    """앱 writer 엔진과 같은 ``hide_parameters`` 로 만든 SQLite 에서 고유 제약 위반을 일으킨다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        hide_parameters=session_module.engine.sync_engine.hide_parameters,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (email TEXT UNIQUE, hashed TEXT)"))
            insert = text("INSERT INTO users (email, hashed) VALUES (:email, :hashed)")
            await conn.execute(insert, {"email": EMAIL, "hashed": HASH})
            with pytest.raises(IntegrityError) as exc_info:
                await conn.execute(insert, {"email": EMAIL, "hashed": HASH})
        return exc_info.value
    finally:
        await engine.dispose()


async def test_integrity_error_string_has_sql_but_no_bound_values():
    message = str(await _integrity_error())

    assert EMAIL not in message and HASH not in message, message
    assert "INSERT INTO users" in message  # 진단용 SQL 은 남는다
    assert "hidden due to hide_parameters" in message


def test_every_app_engine_hides_parameters():
    engines = _app_engines()
    assert {"writer", "background", "reader-factory"} <= engines.keys()
    for name, engine in engines.items():
        assert engine.sync_engine.hide_parameters is True, f"{name} 엔진이 바인드 값을 드러낸다"


def test_engines_are_created_only_in_the_session_module():
    """새 엔진 생성 지점이 생기면 이 목록을 갱신하고 ``hide_parameters=True`` 를 함께 단다."""
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted((PROJECT_ROOT / "app").rglob("*.py"))
        if "tests" not in path.parts
        and (
            "create_async_engine(" in (src := path.read_text(encoding="utf-8"))
            or "create_engine(" in src
        )
    ]
    assert offenders == ["app/core/db/session.py"]
    source = (PROJECT_ROOT / "app/core/db/session.py").read_text(encoding="utf-8")
    assert source.count("create_async_engine(") == source.count("hide_parameters=True") == 3


async def test_logger_exception_through_app_pipeline_has_no_bound_values():
    error = await _integrity_error()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TzFormatter(fmt=LOG_FORMAT, use_utc=True, with_ms=False))
    for log_filter in (SqlNoiseFilter(allow_sql_echo=False), RedactingFilter()):
        handler.addFilter(log_filter)
    logger = logging.getLogger("app.core.repositories.hide_params_probe")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        try:
            raise error
        except IntegrityError:
            logger.exception("DB 쓰기 실패")
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    output = stream.getvalue()
    assert "DB 쓰기 실패" in output and "IntegrityError" in output
    assert EMAIL not in output and HASH not in output, output
