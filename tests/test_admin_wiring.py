"""SQLAdmin 배선 테스트 (중앙 admin 기준).

``main.py`` 는 ``app/internal/admin.py`` 의 ``register_admin(app, engine)`` 을 호출해
``ADMIN_VIEWS`` 의 모든 ModelView 를 등록한다. 여기서는 (1) 중앙 목록이 기대 모델을
모두 포함하는지, (2) 부팅된 앱의 SQLAdmin 에 그대로 등록됐는지, (3) /admin 이
마운트됐는지를 확인한다.
"""

from __future__ import annotations

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}


def test_admin_views_cover_expected_models() -> None:
    """중앙 ADMIN_VIEWS 가 모델을 가진 모든 기능의 뷰를 담는다."""
    from app.internal.admin import ADMIN_VIEWS

    managed = {view.model.__name__ for view in ADMIN_VIEWS}
    assert managed == EXPECTED_MANAGED_MODELS


def test_main_registers_every_admin_view() -> None:
    """부팅된 앱의 SQLAdmin 에 모든 모델 뷰가 등록된다."""
    import main

    registered = {view.model.__name__ for view in main.admin._views}
    assert registered == EXPECTED_MANAGED_MODELS


def test_admin_page_is_mounted() -> None:
    import main

    assert any(getattr(route, "path", "") == "/admin" for route in main.app.routes)
