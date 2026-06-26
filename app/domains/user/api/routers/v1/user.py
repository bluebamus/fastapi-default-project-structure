"""User 도메인 v1 엔드포인트 (최소 동작).

DB 없이 동작하는 최소 API: 헬스 핑과 에코. 자동 등록·라우팅 검증용 기준점.
"""
from fastapi import APIRouter

from app.domains.user.schemas.user_schema import (
    EchoRequest,
    EchoResponse,
    PingResponse,
)

router = APIRouter()

_APP_NAME = "user"


@router.get("/ping", response_model=PingResponse, summary="User 헬스 핑")
async def ping() -> PingResponse:
    """앱이 살아있고 라우터가 마운트되었는지 확인한다."""
    return PingResponse(app=_APP_NAME)


@router.post("/echo", response_model=EchoResponse, summary="User 에코")
async def echo(payload: EchoRequest) -> EchoResponse:
    """요청 메시지를 그대로 돌려준다(요청 검증 동작 확인용)."""
    return EchoResponse(app=_APP_NAME, message=payload.message)
