"""SQLAdmin 관리자 뷰 계약 테스트.

이 파일은 세 저장소(default / active / passive)에 **바이트 동일**하게 존재한다.
저장소별 모델 차이(default 의 ``User`` 만 ``hashed_password`` 를 가진다)는
하드코딩하지 않고 모델을 실측해 분기하므로, 같은 파일이 세 곳에서 모두 의미를 갖는다.

검증하는 계약
-------------
A. 모델을 가진 도메인은 모두 ``admin.py`` 에 ``admin_views`` 를 노출한다.
   빈 ``admin.py`` 는 배선이 조용히 건너뛰므로(``getattr(..., [])`` / ``load_admin_views()``)
   테스트로 막지 않으면 "관리 화면이 없다"는 사실이 아무 신호 없이 방치된다.
B. 각 도메인 모델은 정확히 하나의 ModelView 로 관리된다.
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

import importlib
import inspect
from pathlib import Path

import pytest
from sqladmin import ModelView
from sqlalchemy import String
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOMAINS_PACKAGE = "app.domains"
DOMAINS_DIR = Path(__file__).resolve().parents[2] / "app" / "domains"

# 비밀번호 자격증명으로 취급하여 어떤 화면에도 노출을 금지하는 컬럼명.
SECRET_COLUMNS = frozenset({"hashed_password", "password"})

# 콘텐츠 도메인(전체 CRUD 대상). home 의 접속 로그는 불변이므로 제외한다.
CONTENT_DOMAINS = ("blog", "reply", "sns")


# =============================================================================
# 헬퍼
# =============================================================================
def _domains_with_models() -> list[str]:
    """``app/domains/<name>/models/`` 를 가진 도메인 이름(정렬).

    모델이 없는 도메인(예: default 의 auth)은 관리할 대상이 없으므로 제외한다.
    """
    return sorted(
        path.name
        for path in DOMAINS_DIR.iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "models").is_dir()
    )


def _models_of(domain: str) -> list[type]:
    """해당 도메인의 models 모듈에서 *직접 정의된* 매핑 클래스."""
    module = importlib.import_module(f"{DOMAINS_PACKAGE}.{domain}.models.models")
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__ and hasattr(obj, "__tablename__")
    ]


def _admin_views_of(domain: str) -> list[type]:
    """해당 도메인 ``admin.py`` 의 모듈 레벨 ``admin_views``. 없으면 빈 리스트."""
    module = importlib.import_module(f"{DOMAINS_PACKAGE}.{domain}.admin")
    return list(getattr(module, "admin_views", []))


def _view_for(model: type) -> type:
    """주어진 모델을 관리하는 ModelView 를 찾는다(없으면 실패)."""
    for domain in _domains_with_models():
        for view in _admin_views_of(domain):
            if view.model is model:
                return view
    pytest.fail(f"{model.__name__} 를 관리하는 ModelView 가 없습니다")


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


def test_domain_discovery_is_not_vacuous() -> None:
    """실제 도메인을 찾고 있는지 — 스캔이 빈 목록을 반환하면 모든 파라미터 테스트가 사라진다."""
    assert {"blog", "home", "reply", "sns", "user"} <= set(_domains_with_models())


# =============================================================================
# A. 모델이 있는 도메인은 admin_views 를 노출한다
# =============================================================================
@pytest.mark.parametrize("domain", _domains_with_models())
def test_domain_with_models_exposes_admin_views(domain: str) -> None:
    views = _admin_views_of(domain)
    assert views, f"app/domains/{domain}/admin.py 가 admin_views 를 노출하지 않습니다(빈 파일?)"
    for view in views:
        assert issubclass(view, ModelView), f"{view!r} 는 ModelView 가 아닙니다"


# =============================================================================
# B. 각 모델은 정확히 하나의 ModelView 로 관리된다
# =============================================================================
@pytest.mark.parametrize("domain", _domains_with_models())
def test_every_model_has_exactly_one_admin_view(domain: str) -> None:
    managed = [view.model for view in _admin_views_of(domain)]
    for model in _models_of(domain):
        assert managed.count(model) == 1, f"{model.__name__} 의 ModelView 가 0개이거나 중복입니다"


# =============================================================================
# C. 비밀번호 해시는 어떤 화면에도 노출되지 않는다
# =============================================================================
@pytest.mark.parametrize("domain", _domains_with_models())
def test_admin_never_exposes_password_hash(domain: str) -> None:
    """비밀번호 컬럼을 가진 모델의 뷰는 목록·상세·폼·내보내기에서 그 컬럼을 제외한다.

    비밀번호 컬럼이 없는 저장소(active/passive)에서는 검사할 대상이 없다.
    탐지 로직의 유효성은 ``test_exposure_probe_detects_sqladmin_default`` 가 보장한다.
    """
    for view_cls in _admin_views_of(domain):
        secrets = SECRET_COLUMNS & _column_names(view_cls.model)
        if not secrets:
            continue
        leaked = secrets & _exposed_columns(view_cls)
        assert not leaked, f"{view_cls.__name__} 가 {sorted(leaked)} 를 노출합니다"


def test_user_admin_creation_policy_matches_password_column() -> None:
    """비밀번호 컬럼이 있으면 admin 생성을 막고, 없으면 허용한다.

    폼에서 비밀번호를 제외한 채 생성을 허용하면 ``hashed_password IS NULL`` 인 계정이
    만들어진다. 모델이 nullable 이라 DB 는 받아주지만 auth 는 그런 계정을 영구히
    거부하므로(로그인 불가), 조용히 깨진 데이터가 쌓인다. 그래서 생성 자체를 막는다.
    비밀번호 컬럼이 없는 저장소에서는 그런 위험이 없으므로 생성을 허용한다.
    """
    from app.domains.user.models.models import User

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
    from app.domains.home.models.models import UserAccessLog

    view = _view_for(UserAccessLog)
    assert view.can_create is False
    assert view.can_edit is False


@pytest.mark.parametrize("domain", CONTENT_DOMAINS)
def test_content_admin_allows_full_crud(domain: str) -> None:
    (view,) = _admin_views_of(domain)
    assert view.can_create is True
    assert view.can_edit is True
    assert view.can_delete is True
    assert view.can_view_details is True
    assert view.can_export is True
