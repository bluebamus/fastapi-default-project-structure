"""
SNS 도메인 예외 정의

core 의 공통 예외(NotFoundException 등)를 상속하여 도메인 에러 코드를 부여한다.
"""

from enum import StrEnum

from app.core.exception import NotFoundException


class SnsErrorCode(StrEnum):
    """SNS 도메인 에러 코드 (네이밍: SNS_{대상}_{원인})."""

    POST_NOT_FOUND = "SNS_POST_NOT_FOUND"


class SnsPostNotFoundException(NotFoundException):
    """피드 게시물을 찾을 수 없는 경우."""

    error_code = SnsErrorCode.POST_NOT_FOUND
    message = "피드 게시물을 찾을 수 없습니다."
