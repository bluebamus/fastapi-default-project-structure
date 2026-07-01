"""Auth 모듈 라우터 — v1 서브라우터를 취합한다."""
from fastapi import APIRouter

from app.domains.auth.api.routers.v1 import auth as auth_v1

auth_router = APIRouter()
auth_router.include_router(auth_v1.router, prefix="/v1/auth", tags=["Auth"])
