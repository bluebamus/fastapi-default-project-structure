"""Reports 도메인 예외 정의."""

from enum import StrEnum

from app.core.exception import ValidationException


class ReportErrorCode(StrEnum):
    """Reports 도메인 에러 코드."""

    INVALID_DATE_RANGE = "REPORT_INVALID_DATE_RANGE"


class InvalidDateRangeException(ValidationException):
    """조회 기간이 올바르지 않은 경우.

    FastAPI/Pydantic 은 각 필드를 따로 검증하므로 "종료일이 시작일보다 앞" 같은
    **필드 간 규칙**은 잡지 못한다. 그래서 Service 가 도메인 규칙으로 검증한다.
    """

    error_code = ReportErrorCode.INVALID_DATE_RANGE
    message = "조회 기간이 올바르지 않습니다."
