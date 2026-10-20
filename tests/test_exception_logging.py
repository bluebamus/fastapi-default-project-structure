"""예외 핸들러의 로그 레벨 — service-hardening ADR-008 ④ (F-013).

4xx 는 클라이언트 입력이 원인이라 WARNING 이고 detail(요청 값이 들어 있을 수 있다)을
싣지 않는다. ERROR 로 쌓으면 경보가 흐려진다. 5xx 만 ERROR.
"""

from __future__ import annotations

import logging

import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.exception import (
    AppException,
    DatabaseException,
    DuplicateException,
    NotFoundException,
    ValidationException,
)
from app.core.redis import get_redis
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


def test_redis_connection_error_is_503_logged_once(caplog):
    """Redis 연결 오류 → 503 ``SERVICE_UNAVAILABLE``, traceback 한 번 (integration-e2e F-004).

    ``Exception`` 핸들러는 Starlette 의 ``ServerErrorMiddleware`` 에 걸려 응답 뒤 예외를 다시
    던진다 — uvicorn 이 traceback 을 한 번 더 남기고 연결을 닫는다. TestClient 는 그 재전파를
    예외로 올리므로, 여기서 응답이 돌아오면 재전파가 없다는 뜻이다.
    """
    server = FakeServer()
    server.connected = False  # 모든 명령이 redis.ConnectionError
    app.dependency_overrides[get_redis] = lambda: FakeAsyncRedis(server=server)
    try:
        with caplog.at_level(logging.DEBUG, logger=main_logger.name):
            resp = TestClient(app).post(
                "/api/v1/auth/login", data={"username": "u", "password": "p"}
            )
    finally:
        app.dependency_overrides.pop(get_redis)

    assert resp.status_code == 503
    assert resp.json()["error_code"] == "SERVICE_UNAVAILABLE"
    assert "redis" not in resp.text.lower()
    tracebacks = [r for r in caplog.records if r.exc_info]
    assert len(tracebacks) == 1, [r.getMessage() for r in tracebacks]
