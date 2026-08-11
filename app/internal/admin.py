"""중앙 SQLAdmin 설정 (FastAPI 공식 예제의 ``app/internal/admin.py`` 위치).

기능별 ``admin.py`` 자동 수집(Django Admin autodiscovery 유사)을 제거하고, 모든
``ModelView`` 를 이 한 곳에 모아 ``register_admin(app, engine)`` 으로 명시 등록한다.
새 관리 화면은 여기에 ModelView 를 추가하고 ``ADMIN_VIEWS`` 에 넣으면 된다.

Note:
    SQLAdmin 은 ADMIN 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN=True: /admin 접근 가능, ADMIN=False: /admin 접근 차단.
    운영 환경에서는 보안상 ADMIN=False 설정을 권장한다.

보안 주의 (이 저장소 고유):
    ``User`` 는 자격증명(``hashed_password``)을 보유한다. sqladmin 은
    ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세·수정 폼에
    **모델의 모든 컬럼**을 넣으므로, 아래 ``UserAdmin`` 의 제외 설정을 지우면 bcrypt
    해시가 관리 화면·내보내기에 노출된다 — 지우지 말 것.
"""

from typing import Any

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqlalchemy.ext.asyncio import AsyncEngine

from app.features.blog.models.models import Post
from app.features.home.models.models import UserAccessLog
from app.features.reply.models.models import Reply
from app.features.sns.models.models import SnsPost
from app.features.user.models.models import User
from config import app_settings


# =============================================================================
# Blog — Post
# =============================================================================
class PostAdmin(ModelView, model=Post):
    """블로그 게시글을 조회·생성·수정·삭제하는 관리자 인터페이스."""

    name = "게시글"
    name_plural = "게시글"
    icon = "fa-solid fa-newspaper"

    # 본문(content)은 Text 컬럼이라 목록에서는 제외한다(상세에서 확인).
    # sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도 쓴다.
    column_list = [
        Post.id,
        Post.title,
        Post.author,
        Post.created_at,
        Post.updated_at,
    ]
    column_default_sort = [(Post.created_at, True)]
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [Post.title, Post.content, Post.author]
    column_filters = [Post.author, Post.created_at]

    column_details_list = [
        Post.id,
        Post.title,
        Post.content,
        Post.author,
        Post.created_at,
        Post.updated_at,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    form_excluded_columns = [Post.id, Post.created_at, Post.updated_at]

    column_labels = {
        Post.id: "ID",
        Post.title: "제목",
        Post.content: "본문",
        Post.author: "작성자",
        Post.created_at: "생성 시각",
        Post.updated_at: "수정 시각",
    }


# =============================================================================
# Home — UserAccessLog (불변: 미들웨어 생성, 사후 수정 없음)
# =============================================================================
def _format_is_bot(model: Any, _attr: Any) -> str:
    """봇 여부를 사람이 읽는 문자열로 표시한다."""
    return "봇" if model.is_bot else "사용자"


def _format_response_time(model: Any, _attr: Any) -> str:
    """응답 시간을 'Nms' 형식으로 표시한다(없으면 '-')."""
    return f"{model.response_time_ms}ms" if model.response_time_ms else "-"


class UserAccessLogAdmin(ModelView, model=UserAccessLog):
    """접속 로그를 조회하고 관리하는 관리자 인터페이스."""

    name = "접속 로그"
    name_plural = "접속 로그"
    icon = "fa-solid fa-chart-line"

    column_list = [
        UserAccessLog.id,
        UserAccessLog.ip_address,
        UserAccessLog.os_name,
        UserAccessLog.browser_name,
        UserAccessLog.device_type,
        UserAccessLog.request_path,
        UserAccessLog.request_method,
        UserAccessLog.response_status,
        UserAccessLog.is_bot,
        UserAccessLog.created_at,
    ]
    column_default_sort = [(UserAccessLog.created_at, True)]
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [
        UserAccessLog.ip_address,
        UserAccessLog.user_agent,
        UserAccessLog.request_path,
        UserAccessLog.session_id,
        UserAccessLog.user_id,
    ]
    column_filters = [
        UserAccessLog.ip_address,
        UserAccessLog.os_name,
        UserAccessLog.browser_name,
        UserAccessLog.device_type,
        UserAccessLog.is_bot,
        UserAccessLog.response_status,
        UserAccessLog.request_method,
        UserAccessLog.country,
        UserAccessLog.created_at,
    ]

    column_details_list = [
        UserAccessLog.id,
        UserAccessLog.ip_address,
        UserAccessLog.forwarded_for,
        UserAccessLog.real_ip,
        UserAccessLog.user_agent,
        UserAccessLog.os_name,
        UserAccessLog.os_version,
        UserAccessLog.browser_name,
        UserAccessLog.browser_version,
        UserAccessLog.device_type,
        UserAccessLog.device_brand,
        UserAccessLog.device_model,
        UserAccessLog.is_bot,
        UserAccessLog.country,
        UserAccessLog.country_code,
        UserAccessLog.city,
        UserAccessLog.referer,
        UserAccessLog.request_path,
        UserAccessLog.request_method,
        UserAccessLog.query_string,
        UserAccessLog.response_status,
        UserAccessLog.response_time_ms,
        UserAccessLog.session_id,
        UserAccessLog.user_id,
        UserAccessLog.accept_language,
        UserAccessLog.created_at,
    ]

    # 로그는 미들웨어가 자동 생성하고 불변이다.
    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    column_labels = {
        UserAccessLog.id: "ID",
        UserAccessLog.ip_address: "IP 주소",
        UserAccessLog.forwarded_for: "X-Forwarded-For",
        UserAccessLog.real_ip: "X-Real-IP",
        UserAccessLog.user_agent: "User-Agent",
        UserAccessLog.os_name: "OS",
        UserAccessLog.os_version: "OS 버전",
        UserAccessLog.browser_name: "브라우저",
        UserAccessLog.browser_version: "브라우저 버전",
        UserAccessLog.device_type: "장치 유형",
        UserAccessLog.device_brand: "장치 브랜드",
        UserAccessLog.device_model: "장치 모델",
        UserAccessLog.is_bot: "봇 여부",
        UserAccessLog.country: "국가",
        UserAccessLog.country_code: "국가 코드",
        UserAccessLog.city: "도시",
        UserAccessLog.referer: "유입 경로",
        UserAccessLog.request_path: "요청 경로",
        UserAccessLog.request_method: "HTTP 메서드",
        UserAccessLog.query_string: "쿼리 스트링",
        UserAccessLog.response_status: "응답 코드",
        UserAccessLog.response_time_ms: "응답 시간(ms)",
        UserAccessLog.session_id: "세션 ID",
        UserAccessLog.user_id: "사용자 ID",
        UserAccessLog.accept_language: "Accept-Language",
        UserAccessLog.created_at: "접속 시간",
    }

    column_formatters = {
        UserAccessLog.is_bot: _format_is_bot,
        UserAccessLog.response_time_ms: _format_response_time,
    }


# =============================================================================
# Reply — Reply
# =============================================================================
class ReplyAdmin(ModelView, model=Reply):
    """댓글/답글을 조회·생성·수정·삭제하는 관리자 인터페이스."""

    name = "댓글"
    name_plural = "댓글"
    icon = "fa-solid fa-comments"

    column_list = [
        Reply.id,
        Reply.post_id,
        Reply.author,
        Reply.created_at,
        Reply.updated_at,
    ]
    column_default_sort = [(Reply.created_at, True)]
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [Reply.content, Reply.author, Reply.post_id]
    column_filters = [Reply.author, Reply.post_id, Reply.created_at]

    column_details_list = [
        Reply.id,
        Reply.content,
        Reply.author,
        Reply.post_id,
        Reply.created_at,
        Reply.updated_at,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    form_excluded_columns = [Reply.id, Reply.created_at, Reply.updated_at]

    column_labels = {
        Reply.id: "ID",
        Reply.content: "본문",
        Reply.author: "작성자",
        Reply.post_id: "게시글 ID",
        Reply.created_at: "생성 시각",
        Reply.updated_at: "수정 시각",
    }


# =============================================================================
# SNS — SnsPost
# =============================================================================
class SnsPostAdmin(ModelView, model=SnsPost):
    """SNS 피드 게시물을 조회·생성·수정·삭제하는 관리자 인터페이스."""

    name = "SNS 게시물"
    name_plural = "SNS 게시물"
    icon = "fa-solid fa-share-nodes"

    column_list = [
        SnsPost.id,
        SnsPost.author,
        SnsPost.like_count,
        SnsPost.created_at,
        SnsPost.updated_at,
    ]
    column_default_sort = [(SnsPost.created_at, True)]
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [SnsPost.content, SnsPost.author]
    column_filters = [SnsPost.author, SnsPost.like_count, SnsPost.created_at]

    column_details_list = [
        SnsPost.id,
        SnsPost.content,
        SnsPost.author,
        SnsPost.like_count,
        SnsPost.created_at,
        SnsPost.updated_at,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    form_excluded_columns = [SnsPost.id, SnsPost.created_at, SnsPost.updated_at]

    column_labels = {
        SnsPost.id: "ID",
        SnsPost.content: "본문",
        SnsPost.author: "작성자",
        SnsPost.like_count: "좋아요 수",
        SnsPost.created_at: "생성 시각",
        SnsPost.updated_at: "수정 시각",
    }


# =============================================================================
# User — 자격증명 보유(hashed_password). 노출 차단 필수.
# =============================================================================
class UserAdmin(ModelView, model=User):
    """사용자를 조회·수정·삭제하는 관리자 인터페이스. 생성은 지원하지 않는다."""

    name = "사용자"
    name_plural = "사용자"
    icon = "fa-solid fa-user"

    # hashed_password 없음. sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도
    # 쓰므로, 여기서 빠지면 내보내기 파일에도 해시가 들어가지 않는다.
    column_list = [
        User.id,
        User.username,
        User.email,
        User.is_active,
        User.created_at,
    ]
    column_default_sort = [(User.created_at, True)]
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [User.username, User.email]
    column_filters = [User.is_active, User.created_at]

    # 포함 목록이 아니라 제외 목록을 쓴다. 새 컬럼이 모델에 추가되면 상세에 자동으로
    # 따라 붙되, 자격증명만은 무조건 빠진다.
    column_details_exclude_list = [User.hashed_password]

    # 생성 차단: 폼에서 비밀번호를 제외한 채 생성을 허용하면 hashed_password 가 NULL 인
    # 계정이 만들어진다. 모델이 nullable 이라 DB 는 받아주지만 auth 서비스는 그런 계정을
    # 영구히 거부하므로(로그인 불가), 목록에는 멀쩡해 보이는 죽은 계정이 쌓인다.
    # 가입은 auth 기능의 API 를 통해서만 이루어진다.
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    # 자격증명은 폼에 노출하지 않는다(비밀번호 변경은 auth 담당).
    form_excluded_columns = [
        User.id,
        User.hashed_password,
        User.created_at,
        User.updated_at,
    ]

    column_labels = {
        User.id: "ID",
        User.username: "사용자명",
        User.email: "이메일",
        User.is_active: "활성 여부",
        User.created_at: "가입 시각",
        User.updated_at: "수정 시각",
    }


# 등록 대상 뷰 목록 (SSOT). 새 관리 화면은 위에 ModelView 를 추가하고 여기에 넣는다.
ADMIN_VIEWS: list[type[ModelView]] = [
    PostAdmin,
    UserAccessLogAdmin,
    ReplyAdmin,
    SnsPostAdmin,
    UserAdmin,
]


def register_admin(app: FastAPI, engine: AsyncEngine) -> Admin:
    """SQLAdmin 을 앱에 마운트하고 모든 ModelView 를 등록한다.

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.

    Returns:
        구성된 ``Admin`` 인스턴스(테스트에서 등록 뷰를 검사할 수 있도록 반환).
    """
    admin = Admin(app, engine, title=f"{app_settings.PROJECT_NAME} Admin")
    for view in ADMIN_VIEWS:
        admin.add_view(view)
    return admin
