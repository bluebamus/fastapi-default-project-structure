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
    - main(수동):    discover() 가 config.INSTALLED_APPS 목록을 읽는다.
결선(install_routers/import_models/install_admin)은 두 브랜치가 동일하게 공유한다.
"""
from __future__ import annotations

import importlib
import pkgutil
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
        """`package` 직계 하위의 도메인 앱을 발견한다(컨벤션 스캔).

        앱 = `package` 바로 아래의 서브패키지(언더스코어로 시작하지 않는 것).
        발견된 각 앱 패키지를 import 하여 import-time 부수효과(__init__.py)를 실행하고,
        이름 알파벳순으로 정렬해 보관한다.

        main 브랜치에서는 이 메서드만 INSTALLED_APPS 기반으로 교체한다.
        """
        root = importlib.import_module(package)
        names: list[str] = []
        for info in pkgutil.iter_modules(root.__path__):
            if not info.ispkg or info.name.startswith("_"):
                continue
            names.append(info.name)

        apps = [AppModule(name=name, package=f"{package}.{name}") for name in sorted(names)]

        # import-time 부수효과(예: home 의 access-log sink 등록)를 위해 패키지 import
        for app in apps:
            importlib.import_module(app.package)

        self._apps = apps
        logger.debug("discovered %d apps: %s", len(apps), [a.name for a in apps])
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
