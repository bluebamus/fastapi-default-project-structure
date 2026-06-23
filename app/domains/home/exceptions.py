"""
Home 도메인 예외 정의

Home 도메인에서 발생하는 비즈니스 예외와 에러 코드를 정의한다.
에러 코드는 Enum으로 중앙 관리하며, 각 예외 클래스가 이를 참조한다.

사용 패턴:
    from app.home.exceptions import InvalidDateRangeException

    if start_date > end_date:
        raise InvalidDateRangeException(
            detail={"start_date": str(start_date), "end_date": str(end_date)}
        )
"""

from enum import StrEnum

from app.core.exception import BadRequestException, NotFoundException


class HomeErrorCode(StrEnum):
    """
    Home 도메인 에러 코드

    네이밍 규칙: HOME_{대상}_{원인}
    """

    INVALID_DATE_RANGE = "HOME_INVALID_DATE_RANGE"
    ACCESS_LOG_NOT_FOUND = "HOME_ACCESS_LOG_NOT_FOUND"


class InvalidDateRangeException(BadRequestException):
    """시작 날짜가 종료 날짜보다 늦은 경우"""

    error_code = HomeErrorCode.INVALID_DATE_RANGE
    message = "시작 날짜는 종료 날짜보다 이전이어야 합니다."


class AccessLogNotFoundException(NotFoundException):
    """접속 로그를 찾을 수 없는 경우"""

    error_code = HomeErrorCode.ACCESS_LOG_NOT_FOUND
    message = "접속 로그를 찾을 수 없습니다."
