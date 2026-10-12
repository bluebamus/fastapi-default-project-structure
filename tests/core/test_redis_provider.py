"""Redis 주입 provider ``get_redis`` — service-hardening ADR-011 (F-017).

클라이언트는 lifespan 이 ``app.state.redis`` 에 둔다. provider 는 그것을 돌려주고, 없으면
(lifespan 밖·종료 후) 503 으로 막는다 — ``None`` 을 넘기면 호출자가 ``AttributeError`` 로 500 을 낸다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.core.exception import ServiceUnavailableException
from app.core.redis import get_redis


def _request(app: FastAPI) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "app": app})


def test_get_redis_returns_the_lifespan_client():
    app = FastAPI()
    client = object()
    app.state.redis = client

    assert get_redis(_request(app)) is client


@pytest.mark.parametrize("state", ["unset", "none"])
def test_get_redis_without_client_is_503(state):
    app = FastAPI()
    if state == "none":
        app.state.redis = None

    with pytest.raises(ServiceUnavailableException) as exc_info:
        get_redis(_request(app))

    assert exc_info.value.status_code == 503
