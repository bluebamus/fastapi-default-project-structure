"""Reports 모듈 라우터 — v1 프리픽스로 Reports 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.features.reports.api.routers.v1 import sales_reports as sales_reports_v1

reports_router = APIRouter()

reports_router.include_router(
    sales_reports_v1.router,
    prefix="/v1/reports",
    tags=["Reports"],
)
