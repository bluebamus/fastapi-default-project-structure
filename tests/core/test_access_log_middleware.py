"""접속 로그 미들웨어의 수집 규칙 — service-hardening ADR-006·ADR-007 (F-006·F-007·F-008).

작은 FastAPI 앱에 미들웨어만 달고, sink 를 기록용 가짜로 바꿔 저장될 dict 를 본다.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middlewares import user_info_middleware as middleware_module
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.middlewares.user_info_middleware import (
    UserInfoMiddleware,
    setup_user_info_middleware,
)
from app.core.security.dependencies import CurrentPrincipal
from config import middleware_settings, session_settings
from tests.auth_headers import ALICE, bearer


class _RecordingSink:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save(self, data: dict) -> None:
        self.saved.append(data)


def _app(resolver: ClientIPResolver | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("처리되지 않은 예외")

    @app.get("/me")
    async def me(principal: CurrentPrincipal) -> dict:
        return {"id": principal.id}

    if resolver is None:
        setup_user_info_middleware(app)
    else:
        app.add_middleware(UserInfoMiddleware, ip_resolver=resolver)
    return app


@pytest.fixture
def sink(monkeypatch):
    recording = _RecordingSink()
    monkeypatch.setattr(middleware_module, "get_access_log_sink", lambda: recording)
    monkeypatch.setattr(middleware_settings, "ACCESS_LOG_ENABLED", True)
    return recording


@pytest_asyncio.fixture
async def call(sink):
    async def _call(path: str, *, resolver=None, **kwargs):
        transport = ASGITransport(app=_app(resolver), raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path, **kwargs)
        await access_log_tasks.drain()
        return response

    return _call


async def test_unhandled_exception_is_logged_as_500_and_reraised(call, sink):
    """예외로 끝난 요청도 기록한다 — 예전에는 500 이 접속 로그에서 빠졌다(R-09)."""
    response = await call("/boom")

    assert response.status_code == 500  # 예외는 삼키지 않고 바깥 500 처리로 간다
    assert len(sink.saved) == 1, "500 요청이 접속 로그에 없다"
    assert sink.saved[0]["response_status"] == 500
    assert sink.saved[0]["request_path"] == "/boom"


async def test_successful_request_is_logged_with_its_status(call, sink):
    await call("/ok")
    assert [entry["response_status"] for entry in sink.saved] == [200]


async def test_sensitive_query_values_are_masked(call, sink):
    await call(
        "/ok",
        params=[
            ("page", "2"),
            ("token", "secret-token-value"),
            ("Password", "hunter2"),
            ("code", "oauth-code"),
        ],
    )

    stored = sink.saved[0]["query_string"]
    for secret in ("secret-token-value", "hunter2", "oauth-code"):
        assert secret not in stored, f"민감 값이 저장됐다: {stored}"
    assert stored == "page=2&token=***&Password=***&code=***"


async def test_query_string_without_sensitive_keys_is_kept(call, sink):
    await call("/ok", params={"q": "검색어", "page": "1"})
    assert sink.saved[0]["query_string"] == "q=%EA%B2%80%EC%83%89%EC%96%B4&page=1"


async def test_session_cookie_name_comes_from_settings(call, sink, monkeypatch):
    monkeypatch.setattr(session_settings, "SESSION_COOKIE_NAME", "sid")
    await call("/ok", headers={"Cookie": "sid=abc; session_id=wrong"})
    assert sink.saved[0]["session_id"] == "abc"


async def test_default_wiring_does_not_trust_forwarded_for(call, sink, monkeypatch):
    """설정 기본값(0 홉)으로 조립한 미들웨어는 헤더를 믿지 않는다."""
    monkeypatch.setattr(middleware_settings, "TRUSTED_PROXY_HOPS", 0)
    await call("/ok", headers={"X-Forwarded-For": "6.6.6.6"})

    entry = sink.saved[0]
    assert entry["ip_address"] != "6.6.6.6"
    assert entry["forwarded_for"] == "6.6.6.6"  # 원본 헤더는 감사용으로 남는다


async def test_injected_resolver_is_used(call, sink):
    await call(
        "/ok",
        resolver=ClientIPResolver(1),
        headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"},
    )
    assert sink.saved[0]["ip_address"] == "203.0.113.7"


async def test_authenticated_request_records_user_id(call, sink):
    """인증 의존성이 채운 ``request.state.user_id`` 가 접속 로그에 남는다(service-hardening ADR-017).

    미들웨어가 요청 시작 시점에 읽으면 라우트 의존성이 아직 돌지 않아 항상 None 이다 — 응답 뒤에 읽는다.
    """
    response = await call("/me", headers=bearer(ALICE))

    assert response.status_code == 200
    assert [entry["user_id"] for entry in sink.saved] == [ALICE.id]


async def test_anonymous_and_rejected_requests_record_no_user_id(call, sink):
    await call("/ok")
    await call("/me")  # 토큰 없음 → 401

    assert [(entry["response_status"], entry["user_id"]) for entry in sink.saved] == [
        (200, None),
        (401, None),
    ]
