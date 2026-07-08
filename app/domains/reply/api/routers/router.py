"""Reply 모듈 라우터 — v1 프리픽스로 Reply 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.domains.reply.api.routers.v1 import reply as reply_v1

reply_router = APIRouter()

reply_router.include_router(
    reply_v1.router,
    prefix="/v1/reply",
    tags=["Reply"],
)
