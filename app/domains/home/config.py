"""Home 도메인 앱 자기선언(AppConfig).

AppRegistry 가 부팅 시 이 모듈을 자동 발견하여 home 라우터/모델/Admin 을 연결한다.
모듈 import 시점에 access-log sink 를 등록한다(미들웨어 부수효과).
"""
from fastapi import APIRouter

from app.core.registry import AppConfig
from app.domains.home.access_log_sink import register_sink

register_sink()   # import-time 부수효과: 접속 로그 sink 를 미들웨어에 연결


class HomeConfig(AppConfig):
    name = "home"
    category = "domain"
    prefix = "/api"
    order = 10

    def router(self) -> APIRouter:
        from app.domains.home.api.routers.router import home_router
        return home_router

    def admin_views(self) -> list[type]:
        from app.domains.home.admin import UserAccessLogAdmin
        return [UserAccessLogAdmin]
