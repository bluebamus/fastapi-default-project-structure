"""SNS 도메인 앱 자기선언(AppConfig).

AppRegistry 가 부팅 시 이 모듈을 자동 발견하여 sns 라우터를 연결한다.
"""
from fastapi import APIRouter

from app.core.registry import AppConfig


class SnsConfig(AppConfig):
    name = "sns"
    category = "domain"
    prefix = "/api"
    order = 100

    def router(self) -> APIRouter:
        from app.domains.sns.api.routers.router import sns_router
        return sns_router
