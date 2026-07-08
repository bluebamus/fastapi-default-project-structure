"""Auth v1 API — 회원가입 / 로그인 / 토큰 재발급 / 현재 사용자.

뷰는 HTTP 역할만: 입력 수신 → 주입된 AuthService 호출 → 응답 변환.
"""

from typing import Any

import jwt
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exception import ErrorResponse
from app.core.rate_limit import limiter
from app.domains.auth.dependencies.auth_dependencies import (
    get_auth_service,
    get_current_user,
)
from app.domains.auth.exceptions import InvalidTokenException
from app.domains.auth.schemas.auth_schema import (
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.domains.auth.services.auth_service import AuthService
from app.domains.user.models.models import User
from app.utils.authenticator.auth import REFRESH_TOKEN_TYPE, decode_token
from config import middleware_settings

router = APIRouter()

_UNAUTH: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 실패"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "사용자명 중복"}
}


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="사용자명·이메일·비밀번호로 사용자를 생성합니다.",
    operation_id="authRegister",
    responses=_CONFLICT,
)
@limiter.limit(middleware_settings.RATE_LIMIT_DEFAULT)
async def register(
    request: Request,
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    user = await service.register(payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인(OAuth2 password)",
    description="username/password(form)로 access·refresh 토큰을 발급합니다.",
    operation_id="authLogin",
    responses=_UNAUTH,
)
@limiter.limit(middleware_settings.RATE_LIMIT_DEFAULT)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = await service.authenticate(form.username, form.password)
    access, refresh = service.issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 재발급",
    description="Refresh Token 으로 새 access·refresh 토큰을 발급합니다.",
    operation_id="authRefresh",
    responses=_UNAUTH,
)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, token_type=REFRESH_TOKEN_TYPE)
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenException() from exc

    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise InvalidTokenException()
    user = await service.get_user_by_id(subject)
    if user is None or not user.is_active:
        raise InvalidTokenException()
    access, new_refresh = service.issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="현재 사용자",
    description="Bearer access token 으로 현재 로그인 사용자를 반환합니다(보호 엔드포인트).",
    operation_id="authMe",
    responses=_UNAUTH,
)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
