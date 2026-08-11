"""
user_profile module router aggregator.

컨벤션: 이 모듈의 ``user_profile_router`` 를 패키지 ``__init__.py`` 가 ``router`` 로 재노출하고
main.py 가 /api 에 마운트한다. 버전별 서브라우터를 여기에 include 한다. 예:
    from app.features.user_profile.api.routers.v1 import user_profile as user_profile_v1
    user_profile_router.include_router(user_profile_v1.router, prefix="/v1/user_profile", tags=["UserProfile"])
"""

from fastapi import APIRouter

user_profile_router = APIRouter()
