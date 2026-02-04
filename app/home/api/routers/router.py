"""
Home 모듈 라우터

v1 프리픽스로 Home 모듈의 모든 엔드포인트를 통합 관리합니다.
"""

from fastapi import APIRouter

from app.home.api.routers.v1 import home as home_v1

# Home 모듈 통합 라우터
home_router = APIRouter()

# v1 라우터 등록
home_router.include_router(
    home_v1.router,
    prefix="/v1/home",
    tags=["Home"],
)
