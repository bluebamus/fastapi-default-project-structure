"""SNS 도메인 스키마 (최소 API용 요청/응답 모델)."""
from pydantic import BaseModel, Field


class PingResponse(BaseModel):
    """헬스 핑 응답."""

    app: str
    status: str = "ok"


class EchoRequest(BaseModel):
    """에코 요청 — message 는 비어 있을 수 없다."""

    message: str = Field(..., min_length=1, description="에코할 메시지")


class EchoResponse(BaseModel):
    """에코 응답."""

    app: str
    message: str
