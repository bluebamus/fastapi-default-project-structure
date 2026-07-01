"""Auth 도메인 예외.

core 공통 예외(UnauthorizedException, ConflictException)를 상속해 도메인 에러 코드를 부여한다.
"""
from enum import StrEnum

from app.core.exception import ConflictException, UnauthorizedException


class AuthErrorCode(StrEnum):
    """Auth 도메인 에러 코드."""

    INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    USERNAME_DUPLICATE = "AUTH_USERNAME_DUPLICATE"
    INVALID_TOKEN = "AUTH_INVALID_TOKEN"


class InvalidCredentialsException(UnauthorizedException):
    """아이디/비밀번호 불일치."""

    error_code = AuthErrorCode.INVALID_CREDENTIALS
    message = "아이디 또는 비밀번호가 올바르지 않습니다."


class UsernameAlreadyExistsException(ConflictException):
    """이미 존재하는 사용자명."""

    error_code = AuthErrorCode.USERNAME_DUPLICATE
    message = "이미 존재하는 사용자명입니다."


class InvalidTokenException(UnauthorizedException):
    """유효하지 않은/만료된 토큰."""

    error_code = AuthErrorCode.INVALID_TOKEN
    message = "유효하지 않은 인증 토큰입니다."
