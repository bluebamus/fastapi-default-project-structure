"""Reports 도메인 예외 정의."""

from enum import StrEnum

from app.core.exception import ValidationException


class ReportErrorCode(StrEnum):
    """Reports 도메인 에러 코드."""

    INVALID_DATE_RANGE = "REPORT_INVALID_DATE_RANGE"
    INVALID_SORT = "REPORT_INVALID_SORT"


class InvalidDateRangeException(ValidationException):
    """조회 기간이 올바르지 않은 경우.

    FastAPI/Pydantic 은 각 필드를 따로 검증하므로 "종료일이 시작일보다 앞" 같은
    **필드 간 규칙**은 잡지 못한다. 그래서 Service 가 도메인 규칙으로 검증한다.
    """

    error_code = ReportErrorCode.INVALID_DATE_RANGE
    message = "조회 기간이 올바르지 않습니다."


class InvalidSortException(ValidationException):
    """정렬 키 또는 방향이 허용 목록에 없는 경우.

    Raw SQL 에서 컬럼명·정렬 방향은 bind parameter 로 넘길 수 없다. 그래서 요청값을
    그대로 SQL 에 넣는 대신 **allowlist 조회에 실패시키고** 422 로 돌려준다
    (RAW-REP-004). 허용 목록을 응답 detail 에 실어 호출자가 고칠 수 있게 한다 —
    이 값은 코드 상수라서 노출해도 새어나갈 정보가 없다.
    """

    error_code = ReportErrorCode.INVALID_SORT
    message = "정렬 조건이 올바르지 않습니다."
