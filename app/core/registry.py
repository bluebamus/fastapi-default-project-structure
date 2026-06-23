"""앱 자동발견 레지스트리.

각 도메인 앱은 이 모듈의 AppConfig를 상속한 클래스를 config.py에 선언한다.
AppRegistry가 부팅 시 app/domains 하위를 재귀 스캔하여 발견한 AppConfig로
라우터·모델·Admin·Celery 패키지를 자동 연결한다.
"""
from __future__ import annotations

from fastapi import APIRouter


class AppConfig:
    """도메인 앱의 자기 선언. 하위 클래스가 클래스 속성/훅을 오버라이드한다."""

    name: str = ""
    category: str = "domain"   # 사용자 정의상 거의 항상 "domain"
    prefix: str = "/api"
    enabled: bool = True
    order: int = 100           # 낮을수록 먼저 로드(앱 간 의존 순서 제어용)

    @property
    def package(self) -> str:
        """이 설정이 정의된 패키지 경로 (예: app.domains.home)."""
        module = type(self).__module__          # app.domains.home.config
        return module.rsplit(".", 1)[0]         # app.domains.home

    def router(self) -> APIRouter | None:
        """앱의 통합 APIRouter. 없으면 None."""
        return None

    def admin_views(self) -> list[type]:
        """SQLAdmin ModelView 클래스 목록."""
        return []

    def beat_schedule(self) -> dict:
        """Celery beat 스케줄 조각. 레지스트리가 병합한다."""
        return {}
