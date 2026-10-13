"""예외가 실은 응답 헤더 보존 — log-redaction ADR-002.

전역 핸들러가 응답 본문을 ``ErrorResponse`` 형식으로 바꾸면서 예외의 ``headers`` 를 버리면
405 의 ``Allow``(RFC 9110 §15.5.6 은 필수)·401 의 ``WWW-Authenticate``·429 의 ``Retry-After`` 가
사라진다. 세 핸들러(StarletteHTTPException·AppException)가 모두 ``exc.headers`` 를 싣는지 본다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import main
from app.core.exception import AppException


def _error_body(status: int, message: str) -> dict:
    return {"error_code": f"HTTP_{status}", "message": message, "detail": None}


@pytest.mark.parametrize(("method", "path"), [("DELETE", "/health"), ("POST", "/ready")])
def test_405_carries_allow_with_the_route_methods(method, path):
    route = next(r for r in main.app.routes if isinstance(r, APIRoute) and r.path == path)

    response = TestClient(main.app).request(method, path)

    assert response.status_code == 405
    assert set(response.headers["allow"].split(", ")) == route.methods
    assert response.json() == _error_body(405, "Method Not Allowed")


def _app_with_global_handlers() -> FastAPI:
    app = FastAPI()
    main._register_exception_handlers(app)

    @app.get("/http")
    async def raise_http() -> None:
        raise HTTPException(status_code=418, detail="teapot", headers={"X-Probe": "1"})

    @app.get("/app")
    async def raise_app() -> None:
        raise AppException(
            message="busy", error_code="BUSY", status_code=503, headers={"Retry-After": "7"}
        )

    return app


def test_http_exception_headers_reach_the_response():
    response = TestClient(_app_with_global_handlers()).get("/http")

    assert response.status_code == 418
    assert response.headers["x-probe"] == "1"
    assert response.json() == _error_body(418, "teapot")


def test_app_exception_headers_reach_the_response():
    response = TestClient(_app_with_global_handlers()).get("/app")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "7"
    assert response.json()["error_code"] == "BUSY"


def test_401_keeps_www_authenticate():
    response = TestClient(main.app).post("/api/v1/blog/posts", json={})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == _error_body(401, "Not authenticated")
