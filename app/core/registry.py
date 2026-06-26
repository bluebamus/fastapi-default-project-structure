"""앱 자동발견 레지스트리.

각 도메인 앱은 이 모듈의 AppConfig를 상속한 클래스를 config.py에 선언한다.
AppRegistry가 부팅 시 app/domains 하위를 재귀 스캔하여 발견한 AppConfig로
라우터·모델·Admin·Celery 패키지를 자동 연결한다.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

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


class AppRegistry:
    """도메인 앱 자동발견 레지스트리."""

    def __init__(self) -> None:
        self._apps: list[AppConfig] = []

    @property
    def enabled_apps(self) -> list[AppConfig]:
        """마지막 discover() 호출 결과(활성화된 앱 목록)."""
        return self._apps

    def discover(self, package: str = "app.domains") -> list[AppConfig]:
        """패키지 하위를 재귀 스캔하여 AppConfig 서브클래스를 수집한다.

        각 config.py 모듈에서 AppConfig의 직접·간접 하위 클래스를 찾고,
        enabled=True인 것만 (order, name) 순으로 정렬하여 반환한다.
        이름 중복 시 RuntimeError를 발생시킨다.
        """
        root = importlib.import_module(package)
        found: dict[str, AppConfig] = {}

        for mod_info in pkgutil.walk_packages(root.__path__, prefix=f"{package}."):
            if not mod_info.name.endswith(".config"):
                continue
            module = importlib.import_module(mod_info.name)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, AppConfig) and obj is not AppConfig and obj.__module__ == mod_info.name:
                    cfg = obj()
                    if not cfg.enabled:
                        continue
                    if cfg.name in found:
                        raise RuntimeError(f"중복된 앱 이름: {cfg.name}")
                    found[cfg.name] = cfg

        self._apps = sorted(found.values(), key=lambda c: (c.order, c.name))
        return self._apps

    def install_routers(self, app) -> int:
        count = 0
        for cfg in self._apps:
            router = cfg.router()
            if router is not None:
                app.include_router(router, prefix=cfg.prefix)
                count += 1
        return count

    def import_models(self) -> None:
        for cfg in self._apps:
            try:
                importlib.import_module(f"{cfg.package}.models")
            except ModuleNotFoundError:
                continue

    def install_admin(self, admin) -> int:
        count = 0
        for cfg in self._apps:
            for view in cfg.admin_views():
                admin.add_view(view)
                count += 1
        return count

    def celery_packages(self) -> list[str]:
        return [cfg.package for cfg in self._apps]

    def merged_beat_schedule(self) -> dict:
        schedule: dict = {}
        for cfg in self._apps:
            schedule.update(cfg.beat_schedule())
        return schedule
