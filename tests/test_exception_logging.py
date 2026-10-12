"""예외 핸들러의 로그 레벨 — service-hardening ADR-008 ④ (F-013).

4xx 는 클라이언트 입력이 원인이라 WARNING 이고 detail(요청 값이 들어 있을 수 있다)을
싣지 않는다. ERROR 로 쌓으면 경보가 흐려진다. 5xx 만 ERROR.
"""

from __future__ import annotations

import logging

import pytest
from starlette.requests import Request

from app.core.exception import (
    AppException,
    DatabaseException,
    DuplicateException,
    NotFoundException,
    ValidationException,
)
from main import app
from main import logger as main_logger

SECRET = "secret-detail-9c1e"


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": []})


async def _handle(exc: AppException, caplog) -> list[logging.LogRecord]:
    handler = app.exception_handlers[AppException]
    with caplog.at_level(logging.DEBUG, logger=main_logger.name):
        response = await handler(_request(), exc)
    assert response.status_code == exc.status_code
    return [r for r in caplog.records if r.name == main_logger.name]


@pytest.mark.parametrize(
    "exc",
    [
        NotFoundException(detail={"value": SECRET}),
        DuplicateException(detail={"value": SECRET}),
        ValidationException(detail={"value": SECRET}),
    ],
    ids=["404", "409", "422"],
)
async def test_client_errors_log_warning_without_detail(exc, caplog):
    records = await _handle(exc, caplog)

    assert [r.levelno for r in records] == [logging.WARNING]
    assert not hasattr(records[0], "detail"), "4xx 로그에 detail 이 실렸다"
    assert SECRET not in records[0].getMessage()


async def test_server_errors_log_error_with_detail(caplog):
    records = await _handle(DatabaseException(detail={"model": "T"}), caplog)

    assert [r.levelno for r in records] == [logging.ERROR]
    assert records[0].detail == {"model": "T"}
