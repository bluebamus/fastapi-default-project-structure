"""
Blog 도메인 예외 정의

core 의 공통 예외(NotFoundException 등)를 상속하여 도메인 에러 코드를 부여한다.
"""

from enum import StrEnum

from app.core.exception import NotFoundException


class BlogErrorCode(StrEnum):
    """Blog 도메인 에러 코드 (네이밍: BLOG_{대상}_{원인})."""

    POST_NOT_FOUND = "BLOG_POST_NOT_FOUND"


class PostNotFoundException(NotFoundException):
    """게시글을 찾을 수 없는 경우."""

    error_code = BlogErrorCode.POST_NOT_FOUND
    message = "게시글을 찾을 수 없습니다."
