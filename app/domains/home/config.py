from fastapi import APIRouter
from app.core.registry import AppConfig


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
