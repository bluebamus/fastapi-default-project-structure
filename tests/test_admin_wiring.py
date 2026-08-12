"""SQLAdmin 배선 테스트 (기능 소유 + 명시 취합 기준).

``ModelView`` 는 기능이 소유하고(``app/features/<name>/admin.py``),
``app/features/admin.py`` 가 명시 import 로 ``ADMIN_VIEWS`` 에 취합한다. ``main.py`` 는
``register_admin(app, engine)`` 만 호출한다. 여기서는 (1) 취합 목록이 기대 모델을 모두
포함하는지, (2) 모델을 가진 기능이 빠짐없이 자기 ``admin.py`` 를 갖는지, (3) 부팅된 앱의
SQLAdmin 에 그대로 등록됐는지, (4) /admin 이 마운트됐는지, (5) ADMIN=false 일 때
관리 계층이 **로드조차 되지 않는지**를 확인한다.

(2)가 핵심이다. 과거 기능별 ``admin.py`` 가 0바이트 빈 파일이었을 때 관용적 수집
(``getattr(module, "admin_views", [])``)이 조용히 건너뛰어, ``/admin`` 은 정상 마운트된
채 등록 뷰만 1개인 상태를 아무도 눈치채지 못했다(ADMIN-1). 지금은 취합이 명시 import 라
파일이 없으면 기동이 실패하지만, "모델은 있는데 admin.py 를 안 만든 새 기능"은 여전히
무신호로 지나갈 수 있다 — 그것을 이 테스트가 막는다.
"""

from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys
from typing import cast

import pytest
from fastapi import FastAPI
from sqladmin import Admin

from app.core.db.models_registry import iter_model_modules
from app.core.db.session import engine as _ENGINE

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}

# main.py 가 있는 저장소 루트 (tests/ 의 부모).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


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


# =============================================================================
# 중앙 registry 완전성
#
# 위 검사는 **고정 목록**(EXPECTED_MANAGED_MODELS)과 대조한다. 그래서 새 기능에
# 모델 + admin.py + admin_views 를 만들고 중앙 취합만 빠뜨리면, 위 검사도
# test_feature_with_model_owns_admin_module 도 전부 통과한다 — 고정 목록에 새 모델이
# 없으니 비교 대상 자체가 안 늘어나기 때문이다. 새 모델만 /admin 에서 조용히 사라진다.
#
# 아래는 기대 목록을 **기능 디렉터리에서 독립적으로 만들어** 중앙 목록과 맞춘다.
# 자동 스캔은 여기(테스트)에만 있고 런타임 registry 는 명시 import 를 유지한다.
# =============================================================================
def _feature_admin_views() -> list[type]:
    """모델을 가진 각 기능의 ``admin.py`` 에서 ``admin_views`` 를 기능명 순으로 모은다.

    중앙 ``ADMIN_VIEWS`` 를 참조하지 않는다 — 참조하면 두 목록이 같은 출처가 되어
    비교가 무의미해진다.
    """
    views: list[type] = []
    for feature in _features_with_models():
        module = importlib.import_module(f"app.features.{feature}.admin")
        views.extend(module.admin_views)
    return views


def _registry_diff(expected: list[type], actual: list[type]) -> dict[str, object]:
    """두 뷰 목록의 차이를 진단 가능한 형태로 돌려주는 **순수 함수**.

    모델 이름이 아니라 **클래스 자체**로 비교한다 — 서로 다른 클래스가 우연히 같은
    모델을 가리키는 경우를 구분하기 위해서다.
    이 함수 자체의 정확성은 아래 ``test_registry_diff_*`` 가 합성 입력으로 검증한다.
    """
    return {
        "missing": [v for v in expected if v not in actual],
        "unexpected": [v for v in actual if v not in expected],
        "duplicated": sorted({v.__name__ for v in actual if actual.count(v) > 1}),
        "order_only": set(expected) == set(actual) and expected != actual,
    }


def test_central_registry_contains_every_feature_admin_view() -> None:
    """중앙 ADMIN_VIEWS 가 기능별 admin_views 전량과 **순서까지** 일치한다.

    순서를 계약에 넣는 이유: SQLAdmin 사이드바 메뉴가 ``add_view()`` 호출 순서를
    따르므로 순서가 사용자에게 보인다. 의도적으로 메뉴 순서를 바꾸고 싶다면
    ``ADMIN_VIEWS`` 와 함께 이 계약(기능명 사전순)을 먼저 고쳐야 한다.
    """
    from app.features.admin import ADMIN_VIEWS

    expected = _feature_admin_views()
    actual = list(ADMIN_VIEWS)
    diff = _registry_diff(expected, actual)

    assert not diff["missing"], (
        f"기능에는 있는데 중앙 ADMIN_VIEWS 에 없는 뷰: "
        f"{[v.__name__ for v in cast(list, diff['missing'])]}. "
        "app/features/admin.py 의 import 와 ADMIN_VIEWS 에 한 줄씩 추가하세요."
    )
    assert not diff["unexpected"], (
        f"중앙 ADMIN_VIEWS 에만 있는 뷰: " f"{[v.__name__ for v in cast(list, diff['unexpected'])]}"
    )
    assert not diff["duplicated"], f"중앙 ADMIN_VIEWS 에 중복 등록된 뷰: {diff['duplicated']}"
    assert not diff["order_only"], (
        f"구성은 같으나 순서가 다릅니다. 기대(기능명 사전순): "
        f"{[v.__name__ for v in expected]} / 실제: {[v.__name__ for v in actual]}"
    )
    assert actual == expected


# --- 위 검사가 쓰는 비교 로직 자체의 유효성 (헛통과 방지) ---
class _VA:
    pass


class _VB:
    pass


class _VC:
    pass


def test_registry_diff_detects_missing_view() -> None:
    """기능에는 있는데 중앙에 없는 뷰를 잡는다 — 이 계획의 핵심 사각지대."""
    diff = _registry_diff([_VA, _VB], [_VA])
    assert diff["missing"] == [_VB]
    assert diff["unexpected"] == []


def test_registry_diff_detects_unexpected_and_duplicate() -> None:
    diff = _registry_diff([_VA], [_VA, _VB, _VB])
    assert diff["unexpected"] == [_VB, _VB]
    assert diff["duplicated"] == ["_VB"]


def test_registry_diff_detects_order_only_difference() -> None:
    """구성이 같고 순서만 다른 경우를 별도로 식별한다."""
    diff = _registry_diff([_VA, _VB], [_VB, _VA])
    assert diff["order_only"] is True
    assert diff["missing"] == [] and diff["unexpected"] == []


def test_registry_diff_reports_nothing_when_identical() -> None:
    diff = _registry_diff([_VA, _VB, _VC], [_VA, _VB, _VC])
    assert diff == {"missing": [], "unexpected": [], "duplicated": [], "order_only": False}


def test_feature_list_is_not_vacuous() -> None:
    """탐지 대상이 비어 있으면 아래 테스트가 헛통과한다."""
    assert len(_features_with_models()) >= 5


@pytest.mark.parametrize("feature", _features_with_models())
def test_feature_with_model_owns_admin_module(feature: str) -> None:
    """모델을 가진 기능은 자기 admin.py 에서 admin_views 를 노출한다."""
    module = importlib.import_module(f"app.features.{feature}.admin")
    views = getattr(module, "admin_views", None)
    assert views, f"app/features/{feature}/admin.py 가 admin_views 를 노출하지 않습니다"


def test_admin_layer_is_not_loaded_when_disabled() -> None:
    """ADMIN=false 면 sqladmin 을 아예 로드하지 않는다.

    기능 패키지 ``__init__.py`` 가 ``admin_views`` 를 재노출하면, ``main.py`` 가 라우터를
    얻으려고 패키지를 import 하는 것만으로 sqladmin 과 ModelView 가 전부 올라온다. 그러면
    ADMIN=false 는 "라우트만 안 붙임" 이 되어 설정의 의미가 실제와 어긋나고, sqladmin 을
    선택적 의존성으로 분리할 수도 없다(ADMIN-2).

    별도 프로세스로 확인한다 — 이 테스트 세션은 다른 테스트가 이미 ``main`` 을 import 해
    ``sys.modules`` 가 오염돼 있어, 같은 프로세스에서는 판별이 불가능하다.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys;"
            " os.environ['ADMIN'] = 'false'; os.environ['DEBUG'] = 'false';"
            " import main;"
            " print('SQLADMIN_LOADED=' + str('sqladmin' in sys.modules))",
        ],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=_REPO_ROOT,
    )
    assert (
        "SQLADMIN_LOADED=" in result.stdout
    ), f"ADMIN=false 로 앱을 띄우지 못했습니다.\nstderr:\n{result.stderr[-2000:]}"
    assert "SQLADMIN_LOADED=False" in result.stdout, (
        "ADMIN=false 인데 sqladmin 이 로드됐습니다. 기능 패키지 __init__.py 가 "
        "admin 모듈을 import(재노출)하고 있지 않은지 확인하세요."
    )


def test_main_registers_every_admin_view() -> None:
    """부팅된 앱의 SQLAdmin 에 모든 모델 뷰가 등록된다."""
    import main

    registered = {view.model.__name__ for view in main.admin._views}
    assert registered == EXPECTED_MANAGED_MODELS


def test_admin_page_is_mounted() -> None:
    import main

    assert any(getattr(route, "path", "") == "/admin" for route in main.app.routes)


# =============================================================================
# 조립 함수의 책임 분리
#
# register_admin() 은 두 내부 함수에 위임한다. 아래 검사는 "둘이 각자 하나씩만
# 한다"를 강제한다 — 책임이 섞이면(생성 함수가 뷰를 등록하거나, 등록 함수가 앱을
# 건드리면) 실패한다. 이 함수들은 SQLAdmin 공식 API 가 아니라 프로젝트 내부
# 조립 함수다.
# =============================================================================
def _fresh_app() -> FastAPI:
    """부팅된 main.app 을 오염시키지 않도록 매번 새 앱을 쓴다."""
    return FastAPI()


def test_create_admin_interface_mounts_but_registers_nothing() -> None:
    """생성 함수는 /admin 을 붙이되 ModelView 는 하나도 등록하지 않는다."""
    from app.features.admin import create_admin_interface

    app = _fresh_app()
    admin = create_admin_interface(app, _ENGINE)

    assert isinstance(admin, Admin)
    assert any(
        getattr(route, "path", "") == "/admin" for route in app.routes
    ), "create_admin_interface() 가 /admin 을 마운트하지 않았습니다"
    assert (
        list(admin._views) == []
    ), "create_admin_interface() 가 뷰를 등록했습니다 — 등록은 register_admin_views() 의 책임입니다"


def test_register_admin_views_registers_every_view_once_in_order() -> None:
    """등록 함수는 ADMIN_VIEWS 를 선언 순서대로 정확히 한 번씩 등록한다."""
    from app.features.admin import ADMIN_VIEWS, register_admin_views

    calls: list[type] = []

    class _Recorder:
        def add_view(self, view: type) -> None:
            calls.append(view)

    assert register_admin_views(cast(Admin, _Recorder())) is None
    assert calls == list(ADMIN_VIEWS), "등록 순서 또는 구성이 ADMIN_VIEWS 와 다릅니다"
    assert len(calls) == len(set(calls)), f"중복 등록된 뷰가 있습니다: {calls}"


def test_register_admin_views_does_not_touch_app_or_engine() -> None:
    """등록 함수는 Admin 의 add_view 외에 아무것도 요구하지 않는다.

    앱·엔진·설정을 참조하면 이 스텁으로는 통과할 수 없다 — 그 의존이 생기면
    단독 검증이 불가능해지므로 여기서 막는다.
    """
    from app.features.admin import register_admin_views

    class _OnlyAddView:
        """add_view 하나만 가진 최소 스텁."""

        def __init__(self) -> None:
            self.count = 0

        def add_view(self, view: type) -> None:
            self.count += 1

    stub = _OnlyAddView()
    register_admin_views(cast(Admin, stub))
    assert stub.count > 0


def test_register_admin_creates_then_registers_and_returns_same_admin(monkeypatch) -> None:
    """조합 함수는 생성 → 등록 순서로 부르고, 생성된 Admin 을 그대로 돌려준다.

    순서가 뒤집히면 등록 대상 Admin 이 아직 없다. monkeypatch 로 두 함수를 갈아끼워
    호출 순서와 인자 전달을 직접 확인한다.
    """
    from app.features import admin as admin_module

    order: list[str] = []
    sentinel = object()

    def fake_create(app_arg, engine_arg):
        order.append("create")
        return sentinel

    def fake_register(admin_arg):
        order.append("register")
        assert admin_arg is sentinel, "생성된 Admin 이 등록 함수로 전달되지 않았습니다"

    monkeypatch.setattr(admin_module, "create_admin_interface", fake_create)
    monkeypatch.setattr(admin_module, "register_admin_views", fake_register)

    returned = admin_module.register_admin(_fresh_app(), _ENGINE)

    assert order == ["create", "register"], f"호출 순서가 생성→등록이 아닙니다: {order}"
    assert returned is sentinel, "register_admin() 이 생성된 Admin 을 반환하지 않았습니다"


def test_register_admin_end_to_end_matches_expected_models() -> None:
    """조합 결과가 기대 모델 전체를 담는다(위임이 실제로 동작하는지)."""
    from app.features.admin import register_admin

    admin = register_admin(_fresh_app(), _ENGINE)
    assert {view.model.__name__ for view in admin._views} == EXPECTED_MANAGED_MODELS
