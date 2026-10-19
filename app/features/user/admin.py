"""
User 기능 SQLAdmin 설정

SQLAdmin 을 사용한 User 모델의 관리자 인터페이스를 정의한다.

보안 주의:
    ``User`` 는 auth 기능이 쓰는 자격증명(``hashed_password``)을 보유한다.
    sqladmin 은 ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세
    페이지와 수정 폼에 **모델의 모든 컬럼**을 넣는다. 따라서 아무 설정도 하지 않으면
    비밀번호 해시가 관리 화면에 그대로 노출되고, 폼에서 임의 문자열로 덮어쓸 수도 있다.
    아래 두 줄이 그 노출 경로를 차단한다 — 지우지 말 것.

        column_details_exclude_list = [User.hashed_password]
        form_excluded_columns = [..., User.hashed_password]

    ``can_create = False`` 도 같은 이유다. 폼에서 비밀번호를 제외한 채 생성을 허용하면
    ``hashed_password`` 가 비어 있는 계정이 만들어지고, auth 는 그런 계정을 영구히
    거부하므로(로그인 불가) 조용히 깨진 데이터가 쌓인다.
    구조 증거: ``tests/core/test_admin_views.py``.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 끈다 (DEBUG 와 독립적).
    기본(false): /admin 마운트·활성 슈퍼유저 로그인 필요(``app/features/auth/admin_backend.py``),
    true: 마운트 자체가 없다(404). 상세는 ``config.py`` 의 ADMIN_DISABLED 필드 주석 참고.
"""

from typing import Any

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter
from starlette.requests import Request

from app.core.admin_filters import LocalDateFilter
from app.core.security.admin_session import request_session_store
from app.core.security.dependencies import get_refresh_token_store
from app.features.user.models.models import User


class UserAdmin(ModelView, model=User):
    """
    User 관리자 뷰

    사용자를 조회·수정·삭제하는 관리자 인터페이스다. 생성은 지원하지 않는다.
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "사용자"
    name_plural = "사용자"
    icon = "fa-solid fa-user"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # hashed_password 없음. sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도
    # 쓰므로, 여기서 빠지면 내보내기 파일에도 해시가 들어가지 않는다.
    column_list = [
        User.id,
        User.username,
        User.email,
        User.is_active,
        User.created_at,
    ]

    # 기본 정렬 (최신 가입순)
    column_default_sort = [(User.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    column_searchable_list = [
        User.username,
        User.email,
    ]

    # 필터는 sqladmin.filters 객체로 준다 — 컬럼을 그대로 넣으면 목록 화면이 500 이다(admin-login F-005).
    # 생성 시각은 LocalDateFilter(업무 시간대 날짜 → UTC 범위)로 거른다 — sqladmin 연산 필터는 UTCDateTime 을
    # 날짜형으로 보지 못해 500 이었다(security-ops-hardening ADR-005).
    column_filters = [BooleanFilter(User.is_active), LocalDateFilter(User.created_at)]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    # 포함 목록이 아니라 제외 목록을 쓴다. 새 컬럼이 모델에 추가되면 상세에 자동으로
    # 따라 붙되, 자격증명만은 무조건 빠진다.
    column_details_exclude_list = [User.hashed_password]

    # =========================================================================
    # 권한 설정
    # =========================================================================
    # 생성 차단: 폼에서 비밀번호를 제외한 채 생성을 허용하면 hashed_password 가 NULL 인
    # 계정이 만들어진다. 모델이 nullable 이라 DB 는 받아주지만 auth 서비스는 그런 계정을
    # 영구히 거부하므로(로그인 불가), 목록에는 멀쩡해 보이는 죽은 계정이 쌓인다.
    # 가입은 auth 도메인의 API 를 통해서만 이루어진다.
    can_create = False

    can_edit = True
    can_delete = True
    can_view_details = True

    can_export = True
    export_types = ["csv", "json"]

    # =========================================================================
    # 폼 설정
    # =========================================================================
    # 자격증명은 폼에 노출하지 않는다(비밀번호 변경은 auth 도메인 담당).
    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    form_excluded_columns = [
        User.id,
        User.hashed_password,
        User.created_at,
        User.updated_at,
    ]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
    column_labels = {
        User.id: "ID",
        User.username: "사용자명",
        User.email: "이메일",
        User.is_active: "활성 여부",
        User.created_at: "가입 시각",
        User.updated_at: "수정 시각",
    }

    # =========================================================================
    # 관리 세션·refresh 토큰 폐기 (admin-session-hardening ADR-002·ADR-007·ADR-008)
    # =========================================================================
    # 관리 화면에서 비활성화·슈퍼유저 해제·비밀번호 변경·삭제하면 그 사용자의 관리 세션(다른 브라우저
    # 포함)과 API refresh 토큰을 바로 폐기한다 — 폐기는 API 경로(UserService)와 같은
    # ``RefreshTokenStore.revoke_user``·``AdminSessionStore.revoke_user`` 다(같은 Redis).
    # 이름·이메일 같은 일반 수정은 폐기하지 않는다. 저장소는 이 요청의 세션 미들웨어가 준다.
    #
    # after_* 가 아니라 on_* 훅(커밋 **전**, sqladmin 0.32 ``_queries.py`` 의 ``_update_async``·
    # ``_delete_async``)에서 부른다: Redis 가 실패하면 예외가 커밋 전에 나 변경이 저장되지 않는다
    # (fail-closed — 세션이 살아남은 채 비활성화만 되는 일이 없다). UserService 도 커밋 전에 폐기한다.
    # 자기 자신을 강등·비활성화하면 지금 쓰는 세션도 끊긴다(다음 요청은 로그인 화면) — 의도된 동작이다.
    async def on_model_change(
        self, data: dict[str, Any], model: Any, is_created: bool, request: Request
    ) -> None:
        if not is_created and revokes_admin_sessions(model, data):
            await _revoke_credentials(request, model.id)

    async def on_model_delete(self, model: Any, request: Request) -> None:
        await _revoke_credentials(request, model.id)


async def _revoke_credentials(request: Request, user_id: str) -> None:
    """그 사용자의 refresh 토큰 family 와 관리 세션을 모두 폐기한다. 실패하면 예외 — 커밋 전이라 변경도 막힌다."""
    sessions = request_session_store(request)
    await get_refresh_token_store(sessions.redis).revoke_user(user_id)
    await sessions.revoke_user(user_id)


def revokes_admin_sessions(user: Any, data: dict[str, Any]) -> bool:
    """변경 전 ``user`` 와 저장할 ``data`` 를 비교 — 비활성화·슈퍼유저 해제·비밀번호 변경이면 True."""
    return (
        (user.is_active and data.get("is_active") is False)
        or (user.is_superuser and data.get("is_superuser") is False)
        or ("hashed_password" in data and data["hashed_password"] != user.hashed_password)
    )


# 취합기 ``app/features/admin.py`` 가 이 모듈에서 직접 import 해 ADMIN_VIEWS 에 넣는다.
# 패키지 __init__.py 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
# sqladmin 이 딸려 와 ADMIN_DISABLED=true 가 무의미해진다(가드: tests/test_admin_wiring.py).
admin_views: list[type] = [UserAdmin]
