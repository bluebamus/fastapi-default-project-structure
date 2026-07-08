"""User 모듈 라우터 — v1 프리픽스로 User 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.domains.user.api.routers.v1 import user as user_v1

user_router = APIRouter()

user_router.include_router(
    user_v1.router,
    prefix="/v1/user",
    tags=["User"],
)
