"""
커스텀 예외 클래스 정의

애플리케이션 전체에서 사용되는 예외 클래스들을 정의합니다.
모든 예외는 에러 메시지, HTTP 상태 코드, 상세 정보를 포함합니다.
"""

from typing import Any

from fastapi import status
from pydantic import BaseModel


# =============================================================================
# 예외 응답 스키마
# =============================================================================
class ErrorResponse(BaseModel):
    """API 에러 응답 스키마"""

    error_code: str
    message: str
    detail: Any | None = None

    model_config = {"json_schema_extra": {"example": {"error_code": "NOT_FOUND", "message": "리소스를 찾을 수 없습니다.", "detail": {"resource": "User", "id": 1}}}}


# =============================================================================
# 기본 예외 클래스
# =============================================================================
class AppException(Exception):
    """
    애플리케이션 기본 예외 클래스

    모든 커스텀 예외의 기반이 되는 클래스입니다.

    Attributes:
        status_code: HTTP 상태 코드
        error_code: 애플리케이션 에러 코드
        message: 사용자에게 표시할 에러 메시지
        detail: 추가 에러 상세 정보
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    message: str = "내부 서버 오류가 발생했습니다."

    def __init__(
        self,
        message: str | None = None,
        detail: Any | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        super().__init__(self.message)

    def to_response(self) -> ErrorResponse:
        """에러 응답 객체 생성"""
        return ErrorResponse(
            error_code=self.error_code,
            message=self.message,
            detail=self.detail,
        )


# =============================================================================
# 클라이언트 에러 (4xx)
# =============================================================================
class BadRequestException(AppException):
    """
    잘못된 요청 예외 (400)

    클라이언트가 잘못된 형식이나 유효하지 않은 데이터를 전송한 경우 발생합니다.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"
    message = "잘못된 요청입니다."


class ValidationException(AppException):
    """
    유효성 검증 실패 예외 (422)

    입력 데이터의 유효성 검증에 실패한 경우 발생합니다.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"
    message = "입력 데이터 유효성 검증에 실패했습니다."


class UnauthorizedException(AppException):
    """
    인증 실패 예외 (401)

    인증이 필요하거나 인증에 실패한 경우 발생합니다.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"
    message = "인증이 필요합니다."


class ForbiddenException(AppException):
    """
    권한 부족 예외 (403)

    인증은 되었지만 해당 리소스에 대한 권한이 없는 경우 발생합니다.
    """

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"
    message = "해당 리소스에 대한 접근 권한이 없습니다."


class NotFoundException(AppException):
    """
    리소스 없음 예외 (404)

    요청한 리소스를 찾을 수 없는 경우 발생합니다.
    """

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"
    message = "요청한 리소스를 찾을 수 없습니다."


class ConflictException(AppException):
    """
    리소스 충돌 예외 (409)

    리소스 상태와 충돌이 발생한 경우 (예: 중복 데이터) 발생합니다.
    """

    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"
    message = "리소스 충돌이 발생했습니다."


class DuplicateException(ConflictException):
    """
    중복 데이터 예외 (409)

    이미 존재하는 데이터를 생성하려는 경우 발생합니다.
    """

    error_code = "DUPLICATE"
    message = "이미 존재하는 데이터입니다."


# =============================================================================
# 서버 에러 (5xx)
# =============================================================================
class InternalServerException(AppException):
    """
    내부 서버 에러 예외 (500)

    서버 내부에서 예기치 않은 오류가 발생한 경우 발생합니다.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "INTERNAL_SERVER_ERROR"
    message = "내부 서버 오류가 발생했습니다."


class DatabaseException(AppException):
    """
    데이터베이스 에러 예외 (500)

    데이터베이스 작업 중 오류가 발생한 경우 발생합니다.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "DATABASE_ERROR"
    message = "데이터베이스 오류가 발생했습니다."


class ExternalServiceException(AppException):
    """
    외부 서비스 에러 예외 (502)

    외부 API 호출 등에서 오류가 발생한 경우 발생합니다.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "EXTERNAL_SERVICE_ERROR"
    message = "외부 서비스 오류가 발생했습니다."


class ServiceUnavailableException(AppException):
    """
    서비스 불가 예외 (503)

    서비스가 일시적으로 사용 불가능한 경우 발생합니다.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"
    message = "서비스가 일시적으로 사용 불가능합니다."


# =============================================================================
# 비즈니스 로직 예외
# =============================================================================
class BusinessException(AppException):
    """
    비즈니스 로직 예외 (400)

    비즈니스 규칙 위반 시 발생하는 예외의 기본 클래스입니다.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BUSINESS_ERROR"
    message = "비즈니스 규칙을 위반했습니다."


class InvalidOperationException(BusinessException):
    """
    유효하지 않은 작업 예외 (400)

    현재 상태에서 수행할 수 없는 작업을 시도한 경우 발생합니다.
    """

    error_code = "INVALID_OPERATION"
    message = "현재 상태에서 수행할 수 없는 작업입니다."


class ResourceLockedException(BusinessException):
    """
    리소스 잠금 예외 (423)

    리소스가 잠겨 있어 작업을 수행할 수 없는 경우 발생합니다.
    """

    status_code = status.HTTP_423_LOCKED
    error_code = "RESOURCE_LOCKED"
    message = "리소스가 잠겨 있습니다."


# =============================================================================
# 예외 클래스 목록 export
# =============================================================================
__all__ = [
    # 응답 스키마
    "ErrorResponse",
    # 기본 예외
    "AppException",
    # 클라이언트 에러 (4xx)
    "BadRequestException",
    "ValidationException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "DuplicateException",
    # 서버 에러 (5xx)
    "InternalServerException",
    "DatabaseException",
    "ExternalServiceException",
    "ServiceUnavailableException",
    # 비즈니스 로직 예외
    "BusinessException",
    "InvalidOperationException",
    "ResourceLockedException",
]
