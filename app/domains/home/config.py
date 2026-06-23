from fastapi import APIRouter
from app.core.registry import AppConfig
from app.core.middlewares.access_log_sink import set_access_log_sink
from app.domains.home.access_log_sink import HomeAccessLogSink

set_access_log_sink(HomeAccessLogSink())


class HomeConfig(AppConfig):
    name = "home"
    category = "domain"
    prefix = "/api"
    order = 10

    def router(self) -> APIRouter:
        from app.domains.home.api.routers.router import home_router
        return home_router

    def admin_views(self) -> list[type]:
        from app.domains.home.api.home_admin import UserAccessLogAdmin
        return [UserAccessLogAdmin]
