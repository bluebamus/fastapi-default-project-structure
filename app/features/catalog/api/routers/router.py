"""Catalog 모듈 라우터 — v1 프리픽스로 Catalog 엔드포인트를 통합한다."""

from fastapi import APIRouter

from app.features.catalog.api.routers.v1 import products as products_v1

catalog_router = APIRouter()

catalog_router.include_router(
    products_v1.router,
    prefix="/v1/catalog",
    tags=["Catalog"],
)
