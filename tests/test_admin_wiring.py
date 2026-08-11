"""SQLAdmin 배선 테스트 (기능 소유 + 명시 취합 기준).

``ModelView`` 는 기능이 소유하고(``app/features/<name>/admin.py``),
``app/features/admin.py`` 가 명시 import 로 ``ADMIN_VIEWS`` 에 취합한다. ``main.py`` 는
``register_admin(app, engine)`` 만 호출한다. 여기서는 (1) 취합 목록이 기대 모델을 모두
포함하는지, (2) 모델을 가진 기능이 빠짐없이 자기 ``admin.py`` 를 갖는지, (3) 부팅된 앱의
SQLAdmin 에 그대로 등록됐는지, (4) /admin 이 마운트됐는지를 확인한다.

(2)가 핵심이다. 과거 기능별 ``admin.py`` 가 0바이트 빈 파일이었을 때 관용적 수집
(``getattr(module, "admin_views", [])``)이 조용히 건너뛰어, ``/admin`` 은 정상 마운트된
채 등록 뷰만 1개인 상태를 아무도 눈치채지 못했다(ADMIN-1). 지금은 취합이 명시 import 라
파일이 없으면 기동이 실패하지만, "모델은 있는데 admin.py 를 안 만든 새 기능"은 여전히
무신호로 지나갈 수 있다 — 그것을 이 테스트가 막는다.
"""

from __future__ import annotations

import importlib

import pytest

from app.core.db.models_registry import iter_model_modules

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}


def _features_with_models() -> list[str]:
    """``models/models.py`` 를 가진 기능 패키지 이름 목록.

    모델 등록과 같은 SSOT(``models_registry``)를 쓴다 — 탐지 기준이 갈라지면
    "모델은 등록됐는데 admin 검사에서는 빠지는" 사각지대가 생긴다.
    """
    # "app.features.<name>.models.models" → "<name>"
    return sorted(dotted.split(".")[2] for dotted in iter_model_modules())


def test_admin_views_cover_expected_models() -> None:
    """취합된 ADMIN_VIEWS 가 모델을 가진 모든 기능의 뷰를 담는다."""
    from app.features.admin import ADMIN_VIEWS

    managed = {view.model.__name__ for view in ADMIN_VIEWS}
    assert managed == EXPECTED_MANAGED_MODELS


def test_feature_list_is_not_vacuous() -> None:
    """탐지 대상이 비어 있으면 아래 테스트가 헛통과한다."""
    assert len(_features_with_models()) >= 5


@pytest.mark.parametrize("feature", _features_with_models())
def test_feature_with_model_owns_admin_module(feature: str) -> None:
    """모델을 가진 기능은 자기 admin.py 에서 admin_views 를 노출한다."""
    module = importlib.import_module(f"app.features.{feature}.admin")
    views = getattr(module, "admin_views", None)
    assert views, f"app/features/{feature}/admin.py 가 admin_views 를 노출하지 않습니다"

    package = importlib.import_module(f"app.features.{feature}")
    assert (
        getattr(package, "admin_views", None) is views
    ), f"app/features/{feature}/__init__.py 가 admin_views 를 재노출하지 않습니다"


def test_main_registers_every_admin_view() -> None:
    """부팅된 앱의 SQLAdmin 에 모든 모델 뷰가 등록된다."""
    import main

    registered = {view.model.__name__ for view in main.admin._views}
    assert registered == EXPECTED_MANAGED_MODELS


def test_admin_page_is_mounted() -> None:
    import main

    assert any(getattr(route, "path", "") == "/admin" for route in main.app.routes)
