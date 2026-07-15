"""
Blog 모듈 SQLAdmin 설정

SQLAdmin 을 사용한 Post 모델의 관리자 인터페이스를 정의한다.

Note:
    SQLAdmin 은 ADMIN 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN=True: /admin 접근 가능, ADMIN=False: /admin 접근 차단
    운영 환경에서는 보안상 ADMIN=False 설정을 권장한다.
"""

from sqladmin import ModelView

from app.domains.blog.models.models import Post


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

    column_filters = [
        Post.author,
        Post.created_at,
    ]

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


# 컨벤션: 패키지 __init__.py 가 이 리스트를 재노출하면 main.py 가 SQLAdmin 에 등록한다.
admin_views: list[type] = [PostAdmin]
