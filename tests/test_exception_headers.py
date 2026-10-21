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


# =============================================================================
# 401 은 전부 ``WWW-Authenticate: Bearer`` (integration-e2e ADR-013, RFC 9110 §15.5.2)
# =============================================================================
def test_rejected_bearer_token_carries_the_challenge():
    """토큰이 **있지만** 틀린 경우(``InvalidTokenException``)도 토큰이 없을 때와 같은 헤더를 낸다."""
    response = TestClient(main.app).post(
        "/api/v1/blog/posts", json={}, headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def _unauthorized_app() -> FastAPI:
    from app.core.exception import UnauthorizedException
    from app.core.security.tokens import InvalidTokenException
    from app.features.auth.exceptions import InvalidCredentialsException

    app = FastAPI()
    main._register_exception_handlers(app)
    raised = {
        "credentials": InvalidCredentialsException(),  # 로그인 실패
        "token": InvalidTokenException(),  # refresh·logout·보호 라우트
        "plain": UnauthorizedException(),
        "app-401": AppException(status_code=401, error_code="X"),
        "http-401": HTTPException(status_code=401, detail="no"),
    }

    @app.get("/{kind}")
    async def boom(kind: str) -> None:
        raise raised[kind]

    return app


@pytest.mark.parametrize("kind", ["credentials", "token", "plain", "app-401", "http-401"])
def test_every_401_carries_www_authenticate_bearer(kind):
    response = TestClient(_unauthorized_app()).get(f"/{kind}")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
