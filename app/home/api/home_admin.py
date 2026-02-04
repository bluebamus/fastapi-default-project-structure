"""
Home 모듈 SQLAdmin 설정

SQLAdmin을 사용한 UserAccessLog 모델의 관리자 인터페이스를 정의합니다.

사용 방법:
    main.py에서 Admin 인스턴스를 생성하고 ModelView를 등록합니다.

    from sqladmin import Admin
    from app.home.api.home_admin import UserAccessLogAdmin

    admin = Admin(app, engine)
    admin.add_view(UserAccessLogAdmin)

Note:
    SQLAdmin은 DEBUG 모드에서만 활성화되어야 합니다.
    운영 환경에서는 보안상 비활성화를 권장합니다.
"""

from sqladmin import ModelView

from app.home.models.models import UserAccessLog


class UserAccessLogAdmin(ModelView, model=UserAccessLog):
    """
    UserAccessLog 관리자 뷰

    접속 로그를 조회하고 관리하는 관리자 인터페이스입니다.

    Features:
        - 접속 로그 목록 조회 (페이지네이션)
        - IP, OS, 브라우저, 장치 정보 필터링
        - 상세 정보 조회
        - 로그 삭제 (주의: 운영 환경에서는 비활성화 권장)
    """

    # =========================================================================
    # 기본 설정
    # =========================================================================
    name = "접속 로그"
    name_plural = "접속 로그"
    icon = "fa-solid fa-chart-line"

    # =========================================================================
    # 목록 페이지 설정
    # =========================================================================
    # 목록에 표시할 컬럼
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

    # 기본 정렬 (최신순)
    column_default_sort = [(UserAccessLog.created_at, True)]

    # 페이지당 항목 수
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    # =========================================================================
    # 검색 및 필터 설정
    # =========================================================================
    # 검색 가능한 컬럼
    column_searchable_list = [
        UserAccessLog.ip_address,
        UserAccessLog.user_agent,
        UserAccessLog.request_path,
        UserAccessLog.session_id,
        UserAccessLog.user_id,
    ]

    # 필터 가능한 컬럼
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

    # =========================================================================
    # 상세 페이지 설정
    # =========================================================================
    # 상세 페이지에 표시할 컬럼
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

    # =========================================================================
    # 권한 설정
    # =========================================================================
    # 생성 비활성화 (로그는 자동 생성됨)
    can_create = False

    # 수정 비활성화 (로그는 불변)
    can_edit = False

    # 삭제 허용 (필요 시 False로 변경)
    can_delete = True

    # 상세 보기 허용
    can_view_details = True

    # 내보내기 허용
    can_export = True
    export_types = ["csv", "json"]

    # =========================================================================
    # 컬럼 레이블 (한글화)
    # =========================================================================
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

    # =========================================================================
    # 컬럼 포맷터 (값 표시 형식)
    # =========================================================================
    column_formatters = {
        UserAccessLog.is_bot: lambda m, _: "봇" if m.is_bot else "사용자",
        UserAccessLog.response_time_ms: lambda m, _: f"{m.response_time_ms}ms"
        if m.response_time_ms
        else "-",
    }
