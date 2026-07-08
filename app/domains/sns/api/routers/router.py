"""SNS 모듈 라우터 — v1 프리픽스로 SNS 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.domains.sns.api.routers.v1 import sns as sns_v1

sns_router = APIRouter()

sns_router.include_router(
    sns_v1.router,
    prefix="/v1/sns",
    tags=["SNS"],
)
