"""Blog 모듈 라우터 — v1 프리픽스로 Blog 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.domains.blog.api.routers.v1 import blog as blog_v1

blog_router = APIRouter()

blog_router.include_router(
    blog_v1.router,
    prefix="/v1/blog",
    tags=["Blog"],
)
