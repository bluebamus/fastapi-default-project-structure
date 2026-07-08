"""alpha fakeapp 라우터 — 컨벤션(<name>_router) 검증용."""

from fastapi import APIRouter

alpha_router = APIRouter()


@alpha_router.get("/ping")
def ping():
    return {"ok": True}
