"""응답 직렬화 계약 고정 (계획서 P6).

`default_response_class=ORJSONResponse` 를 제거하고 FastAPI 기본 경로(Pydantic 이
JSON 바이트를 직접 생성)로 전환했다. 전환 전후 응답 바이트가 같아야 하므로, 형식이
바뀌면 즉시 드러나도록 **raw 바이트**를 고정한다.

status code 나 필드 존재 여부만 보는 테스트는 이 변화를 놓친다. datetime 표기가
"...Z" 에서 "...+00:00" 으로 바뀌는 식의 차이는 클라이언트 파싱을 깨뜨리면서도
기존 엔드포인트 테스트는 전부 통과시킨다.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.exception import AppException


class _Payload(BaseModel):
    id: UUID
    aware_at: datetime
    naive_at: datetime
    amount: Decimal
    ratio: float
    note: str | None
    tags: list[str]


_SAMPLE = _Payload(
    id=UUID("12345678-1234-5678-1234-567812345678"),
    aware_at=datetime(2026, 8, 10, 12, 34, 56, 789012, tzinfo=UTC),
    naive_at=datetime(2026, 8, 10, 12, 34, 56, 789012),
    amount=Decimal("10.50"),
    ratio=0.5,
    note=None,
    tags=["가", "b"],
)

# ORJSONResponse 를 쓰던 시점에 실측한 바이트. 전환 후에도 동일해야 한다.
_EXPECTED = (
    b'{"id":"12345678-1234-5678-1234-567812345678",'
    b'"aware_at":"2026-08-10T12:34:56.789012Z",'
    b'"naive_at":"2026-08-10T12:34:56.789012",'
    b'"amount":"10.50",'
    b'"ratio":0.5,'
    b'"note":null,'
    b'"tags":["\xea\xb0\x80","b"]}'
)


def test_response_bytes_are_unchanged():
    """response_model 이 있는 응답의 raw 바이트가 이전 직렬화와 동일하다."""
    app = FastAPI()

    @app.get("/x", response_model=_Payload)
    async def x() -> _Payload:
        return _SAMPLE

    resp = TestClient(app).get("/x")

    assert resp.headers["content-type"] == "application/json"
    assert resp.content == _EXPECTED


@pytest.mark.parametrize(
    "detail",
    [
        pytest.param({"id": "abc"}, id="primitive"),
        pytest.param({"when": datetime(2026, 8, 10, tzinfo=UTC)}, id="datetime"),
        pytest.param({"id": UUID(int=1)}, id="uuid"),
    ],
)
def test_error_handler_survives_non_primitive_detail(detail: Any):
    """에러 응답의 detail 은 Any 라 원시 타입이 아닐 수 있다.

    예전에는 ORJSONResponse 가 datetime/UUID 를 알아서 처리해줬다. 기본
    JSONResponse 는 그렇지 않아 `model_dump(mode="json")` 로 Pydantic 이 먼저
    JSON 안전 값으로 바꿔야 한다. 그 단계를 빠뜨리면 핸들러가 TypeError 로 터진다.

    **실제 등록된 예외 핸들러를 태운다.** 모델만 따로 검사하면 핸들러가 mode="json"
    을 빠뜨려도 통과해버린다(전환 중 실제로 그랬다).
    """
    from main import _register_exception_handlers

    app = FastAPI()
    _register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppException(detail=detail)

    resp = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert resp.status_code == 500, "핸들러가 응답을 만들지 못했다(직렬화 실패 가능)"
    body = resp.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    for value in body["detail"].values():
        assert isinstance(value, str), "JSON 안전 값으로 변환되지 않았다"


def test_app_does_not_use_deprecated_response_class():
    """앱이 deprecated 된 커스텀 응답 클래스를 다시 들이지 않는지 고정한다."""
    from fastapi.responses import ORJSONResponse

    from main import app

    assert app.router.default_response_class.__class__ is not ORJSONResponse
    assert "ORJSONResponse" not in repr(app.router.default_response_class)
