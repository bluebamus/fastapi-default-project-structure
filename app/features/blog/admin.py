"""
Blog 기능 SQLAdmin 설정

SQLAdmin 을 사용한 Post 모델의 관리자 인터페이스를 정의한다.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 끈다 (DEBUG 와 독립적).
    기본(false): /admin 마운트·슈퍼유저 로그인 필요, true: 마운트 자체가 없다(404).
    관리 화면을 쓰지 않는 배포는 ADMIN_DISABLED=true 를 권장한다.
"""

from sqladmin import ModelView
from sqladmin.filters import OperationColumnFilter

from app.features.blog.models.models import Post


class PostAdmin(ModelView, model=Post):
    """
    Post 관리자 뷰

    블로그 게시글을 조회·생성·수정·삭제하는 관리자 인터페이스다.
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "게시글"
    name_plural = "게시글"
    icon = "fa-solid fa-newspaper"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # 본문(content)은 Text 컬럼이라 목록에서는 제외한다(상세에서 확인).
    # sqladmin 은 목록 컬럼을 내보내기(csv/json)의 기본값으로도 쓴다.
    column_list = [
        Post.id,
        Post.title,
        Post.author,
        Post.created_at,
        Post.updated_at,
    ]

    # 기본 정렬 (최신순)
    column_default_sort = [(Post.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    column_searchable_list = [
        Post.title,
        Post.content,
        Post.author,
    ]

    # 필터는 sqladmin.filters 객체로 준다 — 컬럼을 그대로 넣으면 목록 화면이 500 이다(admin-login F-005).
    # 생성 시각은 필터하지 않는다: 연산 필터가 UTCDateTime(TypeDecorator)을 날짜 형으로 보지 못해 입력 문자열을
    # 그대로 바인딩한다(500). 시각은 목록 정렬로 본다.
    column_filters = [OperationColumnFilter(Post.author)]

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    column_details_list = [
        Post.id,
        Post.title,
        Post.content,
        Post.author,
        Post.created_at,
        Post.updated_at,
    ]

    # =========================================================================
    # 권한 설정
    # =========================================================================
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    can_export = True
    export_types = ["csv", "json"]

    # =========================================================================
    # 폼 설정
    # =========================================================================
    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    # 손으로 넣으면 일관성이 깨지므로 폼에서 제외한다.
    form_excluded_columns = [Post.id, Post.created_at, Post.updated_at]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
    column_labels = {
        Post.id: "ID",
        Post.title: "제목",
        Post.content: "본문",
        Post.author: "작성자",
        Post.created_at: "생성 시각",
        Post.updated_at: "수정 시각",
    }


# 취합기 ``app/features/admin.py`` 가 이 모듈에서 직접 import 해 ADMIN_VIEWS 에 넣는다.
# 패키지 __init__.py 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
# sqladmin 이 딸려 와 ADMIN_DISABLED=true 가 무의미해진다(가드: tests/test_admin_wiring.py).
admin_views: list[type] = [PostAdmin]
