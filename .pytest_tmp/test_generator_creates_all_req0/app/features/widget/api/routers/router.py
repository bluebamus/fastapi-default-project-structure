"""
widget module router aggregator.

컨벤션: 이 모듈의 ``widget_router`` 를 패키지 ``__init__.py`` 가 ``router`` 로 재노출하고
main.py 가 /api 에 마운트한다. 버전별 서브라우터를 여기에 include 한다. 예:
    from app.features.widget.api.routers.v1 import widget as widget_v1
    widget_router.include_router(widget_v1.router, prefix="/v1/widget", tags=["Widget"])
"""

from fastapi import APIRouter

widget_router = APIRouter()
