"""
Reply 도메인 예외 정의

core 의 공통 예외(NotFoundException 등)를 상속하여 도메인 에러 코드를 부여한다.
"""

from enum import StrEnum

from app.core.exception import NotFoundException


class ReplyErrorCode(StrEnum):
    """Reply 도메인 에러 코드 (네이밍: REPLY_{대상}_{원인})."""

    REPLY_NOT_FOUND = "REPLY_NOT_FOUND"


class ReplyNotFoundException(NotFoundException):
    """댓글을 찾을 수 없는 경우."""

    error_code = ReplyErrorCode.REPLY_NOT_FOUND
    message = "댓글을 찾을 수 없습니다."
