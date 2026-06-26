"""앱 자동발견 레지스트리 (컨벤션 기반, gen-2).

도메인 앱은 별도 선언(config.py / AppConfig)이 없다. 디렉터리 구조와 네이밍
컨벤션만으로 라우터·모델·Admin 을 발견·연결한다("convention over configuration").

컨벤션 (app/domains/<name>/):
    api/routers/router.py   →  <name>_router: APIRouter   (있으면 prefix /api 에 마운트)
    models/__init__.py      →  import 시 Base.metadata 에 테이블 등록 (선택)
    admin.py                →  admin_views: list[type]      (선택, SQLAdmin ModelView)
    __init__.py             →  import-time 부수효과(예: 미들웨어 sink 등록) (선택)

브랜치 차이는 오직 "앱 목록의 출처"뿐이다:
    - feature(자동): discover() 가 app/domains/* 를 스캔해 목록을 만든다.
    - main(수동):    discover() 가 config.INSTALLED_APPS 목록을 읽는다.  ← 이 브랜치
결선(install_routers/import_models/install_admin)은 두 브랜치가 동일하게 공유한다.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass

from fastapi import APIRouter

from app.utils.logs import get_logger

logger = get_logger("registry")

DOMAINS_PACKAGE = "app.domains"


@dataclass(frozen=True)
class AppModule:
    """발견된 도메인 앱. 이름·패키지 경로만으로 구성요소를 컨벤션으로 찾는다.

    Attributes:
        name: 앱 이름 (예: "home"). 라우터 변수명 컨벤션의 기준.
        package: 앱 패키지 dotted 경로 (예: "app.domains.home").
        prefix: 라우터 마운트 prefix.
    """

    name: str
    package: str
    prefix: str = "/api"

    @property
    def router_attr(self) -> str:
        """컨벤션 라우터 변수명 (예: home → home_router)."""
        return f"{self.name}_router"

    def load_router(self) -> APIRouter | None:
        """`<package>.api.routers.router` 의 `<name>_router` 를 반환. 없으면 None."""
        try:
            module = importlib.import_module(f"{self.package}.api.routers.router")
        except ModuleNotFoundError:
            return None
        return getattr(module, self.router_attr, None)

    def load_admin_views(self) -> list[type]:
        """`<package>.admin` 의 모듈 레벨 `admin_views` 리스트를 반환. 없으면 []."""
        try:
            module = importlib.import_module(f"{self.package}.admin")
        except ModuleNotFoundError:
            return []
        return list(getattr(module, "admin_views", []))

    def import_models(self) -> None:
        """`<package>.models` 를 import 하여 테이블을 Base.metadata 에 등록한다(있으면)."""
        try:
            importlib.import_module(f"{self.package}.models")
        except ModuleNotFoundError:
            return


class AppRegistry:
    """도메인 앱 자동발견 레지스트리 (컨벤션 기반)."""

    def __init__(self) -> None:
        self._apps: list[AppModule] = []

    @property
    def enabled_apps(self) -> list[AppModule]:
        """마지막 discover() 결과."""
        return self._apps

    def discover(self, package: str = DOMAINS_PACKAGE) -> list[AppModule]:
        """`config.INSTALLED_APPS` 목록을 읽어 도메인 앱을 등록한다(수동 등록).

        앱 = INSTALLED_APPS 에 나열된 이름. `package`(기본 app.domains) 하위에서
        `<package>.<name>` 패키지로 매핑한다. 목록 순서를 그대로 보존하여(정렬 없음)
        명시적 로드 순서 제어를 제공한다. 각 앱 패키지를 import 하여 import-time
        부수효과(__init__.py, 예: home 의 sink 등록)를 실행한다.

        feature 브랜치는 이 메서드만 app/domains/* 자동 스캔으로 교체하고,
        결선 로직(install_routers/import_models/install_admin)은 동일하게 공유한다.
        """
        from config import INSTALLED_APPS

        apps = [AppModule(name=name, package=f"{package}.{name}") for name in INSTALLED_APPS]

        # import-time 부수효과(예: home 의 access-log sink 등록)를 위해 패키지 import
        for app in apps:
            importlib.import_module(app.package)

        self._apps = apps
        logger.debug("installed %d apps: %s", len(apps), [a.name for a in apps])
        return self._apps

    def install_routers(self, app) -> int:
        """발견된 각 앱의 `<name>_router` 를 FastAPI 앱에 마운트한다."""
        count = 0
        for module in self._apps:
            router = module.load_router()
            if router is None:
                logger.warning("앱 '%s' 에 %s 라우터가 없어 건너뜀", module.name, module.router_attr)
                continue
            app.include_router(router, prefix=module.prefix)
            count += 1
        return count

    def import_models(self) -> None:
        """발견된 각 앱의 models 패키지를 import 한다(Base.metadata 등록)."""
        for module in self._apps:
            module.import_models()

    def install_admin(self, admin) -> int:
        """발견된 각 앱의 admin.py `admin_views` 를 SQLAdmin 에 등록한다."""
        count = 0
        for module in self._apps:
            for view in module.load_admin_views():
                admin.add_view(view)
                count += 1
        return count
