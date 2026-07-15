"""
User 모듈 SQLAdmin 설정

SQLAdmin 을 사용한 User 모델의 관리자 인터페이스를 정의한다.

보안 주의 (이 저장소 고유):
    이 저장소의 ``User`` 는 auth 도메인의 자격증명(``hashed_password``)을 보유한다.
    sqladmin 은 ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세
    페이지와 수정 폼에 **모델의 모든 컬럼**을 넣는다. 따라서 아무 설정도 하지 않으면
    bcrypt 해시가 관리 화면에 그대로 노출되고, 폼에서 임의 문자열로 덮어쓸 수도 있다.
    아래 두 줄이 그 노출 경로를 차단한다 — 지우지 말 것.

        column_details_exclude_list = [User.hashed_password]
        form_excluded_columns = [..., User.hashed_password]

    (active/passive 저장소의 ``User`` 에는 ``hashed_password`` 컬럼 자체가 없으므로
    해당 저장소의 UserAdmin 은 이 차단이 필요 없고 생성도 허용한다.)

Note:
    SQLAdmin 은 ADMIN 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN=True: /admin 접근 가능, ADMIN=False: /admin 접근 차단
    운영 환경에서는 보안상 ADMIN=False 설정을 권장한다.
"""

from sqladmin import ModelView

from app.domains.user.models.models import User


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

    column_filters = [
        User.is_active,
        User.created_at,
    ]

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


# 컨벤션: 패키지 __init__.py 가 이 리스트를 재노출하면 main.py 가 SQLAdmin 에 등록한다.
admin_views: list[type] = [UserAdmin]
