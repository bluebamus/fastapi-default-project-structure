"""SQLAdmin 배선 테스트 (표준 FastAPI 구조).

``main.py`` 는 도메인 **패키지 모듈**에서 ``getattr(_app, "admin_views", [])`` 로 뷰를
읽는다. 따라서 ``admin.py`` 에 뷰를 정의하는 것만으로는 부족하고, 각 도메인
``__init__.py`` 가 그 리스트를 재노출해야 한다. 재노출을 빠뜨리면 예외 없이 조용히
등록에서 누락되므로 여기서 막는다.

(active/passive 저장소는 AppRegistry 가 ``app.domains.<name>.admin`` 을 직접 import
하므로 재노출이 필요 없다 — 그래서 이 파일은 저장소마다 다르다.)
"""

from __future__ import annotations

import importlib

import pytest

DOMAINS_WITH_ADMIN = ("blog", "home", "reply", "sns", "user")

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}


@pytest.mark.parametrize("domain", DOMAINS_WITH_ADMIN)
def test_domain_package_reexports_admin_views(domain: str) -> None:
    """main.py 가 읽는 위치(패키지 모듈)에서 admin_views 가 보여야 한다."""
    package = importlib.import_module(f"app.domains.{domain}")
    views = getattr(package, "admin_views", None)
    assert views, (
        f"app/domains/{domain}/__init__.py 가 admin_views 를 재노출하지 않습니다. "
        f"main.py 는 패키지에서 읽으므로 이 도메인의 관리 화면이 조용히 누락됩니다."
    )


def test_main_registers_every_domain_admin_view() -> None:
    """부팅된 앱의 SQLAdmin 에 모든 도메인 모델 뷰가 등록된다."""
    import main

    registered = {view.model.__name__ for view in main.admin._views}
    assert registered == EXPECTED_MANAGED_MODELS


def test_admin_page_is_mounted() -> None:
    import main

    assert any(getattr(route, "path", "") == "/admin" for route in main.app.routes)
