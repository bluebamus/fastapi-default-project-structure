"""SQLAdmin ModelView 계약 테스트.

``ModelView`` 정의는 기능이 소유하고(``app/features/<name>/admin.py``),
``app/features/admin.py`` 가 명시 import 로 취합한다. 등록 뷰의 진실의 원천은
``ADMIN_VIEWS`` 다 — 어느 파일에 정의됐든 여기 모이지 않으면 등록되지 않는다.

검증하는 계약
-------------
B. 각 모델은 정확히 하나의 ModelView 로 관리된다.
C. 비밀번호 해시는 목록·상세·폼·내보내기 **어디에도** 나타나지 않는다.
D. 접속 로그는 불변(생성·수정 불가), 콘텐츠 모델은 전체 CRUD.

주의(sqladmin 0.24.0 기본 동작)
-------------------------------
``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세 페이지와 수정 폼은
**모델의 모든 컬럼**을 사용한다. 따라서 비밀번호 컬럼을 명시적으로 제외하지 않으면
bcrypt 해시가 화면에 그대로 노출된다. ``test_exposure_probe_detects_sqladmin_default``
가 이 기본 동작을 실제로 재현하여, 아래 탐지 로직이 살아 있음을 증명한다.
"""

from __future__ import annotations

import pytest
from sqladmin import ModelView
from sqlalchemy import String
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.features.admin import ADMIN_VIEWS

# 비밀번호 자격증명으로 취급하여 어떤 화면에도 노출을 금지하는 컬럼명.
SECRET_COLUMNS = frozenset({"hashed_password", "password"})


# =============================================================================
# 헬퍼
# =============================================================================
def _column_names(model: type) -> set[str]:
    return {column.key for column in sa_inspect(model).columns}


def _exposed_columns(view_cls: type) -> set[str]:
    """뷰가 사용자에게 실제로 드러내는 모든 컬럼(목록·상세·폼·내보내기 합집합)."""
    view = view_cls()
    return (
        set(view.get_list_columns())
        | set(view.get_details_columns())
        | set(view.get_form_columns())
        | set(view.get_export_columns())
    )


def _view_for(model: type) -> type:
    """주어진 모델을 관리하는 ModelView 를 찾는다(없으면 실패)."""
    for view in ADMIN_VIEWS:
        if view.model is model:
            return view
    pytest.fail(f"{model.__name__} 를 관리하는 ModelView 가 ADMIN_VIEWS 에 없습니다")


# =============================================================================
# 탐지 로직 자체의 유효성 (헛통과 방지)
# =============================================================================
class _ProbeBase(DeclarativeBase):
    """앱 메타데이터를 오염시키지 않기 위한 독립 Base."""


class _ProbeSecretive(_ProbeBase):
    __tablename__ = "probe_secretive"

    id: Mapped[int] = mapped_column(primary_key=True)
    hashed_password: Mapped[str] = mapped_column(String(255))


class _ProbeUnguardedAdmin(ModelView, model=_ProbeSecretive):
    """아무 설정도 하지 않은 뷰 — sqladmin 기본값이 해시를 노출한다."""


def test_exposure_probe_detects_sqladmin_default() -> None:
    """설정 없는 ModelView 는 비밀번호 컬럼을 노출한다 — 탐지 로직이 살아 있음을 증명."""
    exposed = _exposed_columns(_ProbeUnguardedAdmin)
    assert "hashed_password" in exposed, (
        "sqladmin 기본 동작이 바뀌었거나 _exposed_columns 가 고장났습니다. "
        "이 테스트가 통과하지 못하면 아래 노출 금지 테스트는 헛통과합니다."
    )


# =============================================================================
# 등록 자체가 비어 있지 않은지 (파라미터 테스트가 사라지는 헛통과 방지)
# =============================================================================
def test_admin_views_is_not_vacuous() -> None:
    managed = {view.model.__name__ for view in ADMIN_VIEWS}
    assert {"Post", "Reply", "SnsPost", "User", "UserAccessLog"} <= managed


# =============================================================================
# B. 각 모델은 정확히 하나의 ModelView 로 관리된다
# =============================================================================
def test_every_model_has_exactly_one_admin_view() -> None:
    models = [view.model for view in ADMIN_VIEWS]
    duplicates = {m.__name__ for m in models if models.count(m) > 1}
    assert not duplicates, f"모델이 둘 이상의 ModelView 로 중복 관리됩니다: {sorted(duplicates)}"


# =============================================================================
# C. 비밀번호 해시는 어떤 화면에도 노출되지 않는다
# =============================================================================
@pytest.mark.parametrize("view_cls", ADMIN_VIEWS, ids=lambda v: v.__name__)
def test_admin_never_exposes_password_hash(view_cls: type) -> None:
    """비밀번호 컬럼을 가진 모델의 뷰는 목록·상세·폼·내보내기에서 그 컬럼을 제외한다."""
    secrets = SECRET_COLUMNS & _column_names(view_cls.model)
    if not secrets:
        return  # 비밀번호 컬럼이 없는 모델은 검사 대상 아님
    leaked = secrets & _exposed_columns(view_cls)
    assert not leaked, f"{view_cls.__name__} 가 {sorted(leaked)} 를 노출합니다"


def test_user_admin_creation_policy_matches_password_column() -> None:
    """비밀번호 컬럼이 있으면 admin 생성을 막고, 없으면 허용한다.

    폼에서 비밀번호를 제외한 채 생성을 허용하면 ``hashed_password IS NULL`` 인 계정이
    만들어진다. 모델이 nullable 이라 DB 는 받아주지만 auth 는 그런 계정을 영구히
    거부하므로(로그인 불가), 조용히 깨진 데이터가 쌓인다. 그래서 생성 자체를 막는다.
    """
    from app.features.user.models.models import User

    view = _view_for(User)
    has_secret = bool(SECRET_COLUMNS & _column_names(User))
    assert view.can_create is (not has_secret)
    assert view.can_edit is True
    assert view.can_delete is True


# =============================================================================
# D. 쓰기 권한 정책
# =============================================================================
def test_access_log_admin_stays_immutable() -> None:
    """접속 로그는 미들웨어가 생성하고 사후 수정되지 않는다."""
    from app.features.home.models.models import UserAccessLog

    view = _view_for(UserAccessLog)
    assert view.can_create is False
    assert view.can_edit is False


@pytest.mark.parametrize("model_path", ["blog.Post", "reply.Reply", "sns.SnsPost"])
def test_content_admin_allows_full_crud(model_path: str) -> None:
    import importlib

    feature, class_name = model_path.split(".")
    module = importlib.import_module(f"app.features.{feature}.models.models")
    model = getattr(module, class_name)
    view = _view_for(model)
    assert view.can_create is True
    assert view.can_edit is True
    assert view.can_delete is True
    assert view.can_view_details is True
    assert view.can_export is True
