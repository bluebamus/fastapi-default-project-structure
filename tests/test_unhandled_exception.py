"""처리기가 없는 예외(버그) — 가장 바깥 사용자 미들웨어가 받는다 (integration-e2e ADR-016).

Starlette 는 ``Exception`` 처리기를 ``ServerErrorMiddleware``(가장 바깥)에 두고, 응답을 보낸 **뒤 예외를 다시
던진다** — uvicorn 이 ``Exception in ASGI application`` traceback 을 한 번 더 남기고 연결을 닫는다. 그 바로 안쪽의
``@app.middleware("http")`` 가 예외를 받아 같은 처리기로 응답을 끝내면 로그 1번·연결 유지·응답 불변이다.
``DEBUG=true`` 는 지금처럼 다시 던진다. 실제 uvicorn 의 연결 유지는 ``tests/integration/test_uvicorn_lifecycle.py``.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

import main

BODY = {
    "error_code": "INTERNAL_SERVER_ERROR",
    "message": "내부 서버 오류가 발생했습니다.",
    "detail": None,
}


def _buggy_app() -> FastAPI:
    app = FastAPI()

    async def inner(
        request, call_next
    ):  # 다른 사용자 미들웨어(CORS·UserInfo 자리) 안에서 나는 예외
        if request.url.path == "/in-middleware":
            raise RuntimeError("bug in middleware")
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=inner)
    main._register_exception_handlers(app)  # main 과 같은 순서 — 다른 미들웨어 다음에 등록

    @app.get("/bug")
    async def bug() -> None:
        raise RuntimeError("bug in endpoint")

    return app


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(main.app_settings, "DEBUG", False)


@pytest.mark.parametrize("path", ["/bug", "/in-middleware"])
def test_unhandled_exception_is_answered_once_without_reraising(production, caplog, path):
    """``raise_server_exceptions=True`` 인데도 예외가 올라오지 않는다 = ``ServerErrorMiddleware`` 까지 가지 않았다."""
    with caplog.at_level(logging.ERROR, logger=main.logger.name):
        response = TestClient(_buggy_app()).get(path)

    assert response.status_code == 500
    assert response.json() == BODY
    unhandled = [r for r in caplog.records if "[UnhandledException]" in r.getMessage()]
    assert len(unhandled) == 1 and unhandled[0].exc_info is not None


def test_debug_keeps_reraising():
    """``DEBUG=true``(pytest-env 기본)는 지금 동작 그대로 — 다시 던진다."""
    assert main.app_settings.DEBUG is True
    with pytest.raises(RuntimeError, match="bug in endpoint"):
        TestClient(_buggy_app()).get("/bug")


def test_catcher_is_the_outermost_user_middleware():
    """가장 바깥(``user_middleware[0]``)이어야 CORS·UserInfo 안에서 난 예외도 받는다 — 등록 순서 고정."""
    outermost = main.app.user_middleware[0]
    assert outermost.cls is BaseHTTPMiddleware
    assert outermost.kwargs["dispatch"].__name__ == "unhandled_exception_middleware"
