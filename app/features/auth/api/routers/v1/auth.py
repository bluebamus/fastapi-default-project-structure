"""Auth v1 API — 회원가입 / 로그인 / 토큰 회전 / 로그아웃 / 현재 사용자.

뷰는 HTTP 역할만: 입력 수신 → 주입된 AuthService 호출 → 응답 변환.
레이트 리밋은 라우트 의존성(``register_rate_limit``·``login_rate_limit``)으로 건다.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exception import ErrorResponse
from app.core.security.access import PublicWrite
from app.features.auth.dependencies.auth_dependencies import (
    get_auth_service,
    get_current_user,
    login_rate_limit,
    register_rate_limit,
)
from app.features.auth.schemas.auth_schema import (
    AuthUserResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.features.auth.services.auth_service import AuthService, TokenPair
from app.features.user.models.models import User

router = APIRouter()

_UNAUTH: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 실패"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "사용자명 중복"}
}
_TOO_MANY: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorResponse,
        "description": "시도 횟수 초과 — `Retry-After` 헤더(초) 뒤에 다시 시도",
    }
}


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="사용자명·이메일·비밀번호로 사용자를 생성합니다(IP 단위 레이트 리밋).",
    operation_id="authRegister",
    responses={**_CONFLICT, **_TOO_MANY},
    dependencies=[PublicWrite, Depends(register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthUserResponse:
    user = await service.register(payload)
    # 응답 DTO 를 먼저 검증하고 그다음 한 번 커밋한다 — 검증이 실패하면 아무것도 확정되지 않는다.
    response = AuthUserResponse.model_validate(user)
    await service.commit()
    return response


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인(OAuth2 password)",
    description=(
        "username/password(form)로 access·refresh 토큰을 발급합니다. "
        "IP+사용자명·IP 단위 레이트 리밋이 걸리고, 성공하면 IP+사용자명 카운터를 지웁니다."
    ),
    operation_id="authLogin",
    dependencies=[PublicWrite],
    responses={**_UNAUTH, **_TOO_MANY},
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    reset_attempts: Callable[[], Awaitable[None]] = Depends(login_rate_limit),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user, rehashed = await service.authenticate(form.username, form.password)
    response = _token_response(await service.issue_tokens(user))
    if rehashed:
        # 레거시 bcrypt → Argon2 재해시를 저장한다. 그 밖의 로그인은 DB 를 바꾸지 않는다.
        await service.commit()
    await reset_attempts()
    return response


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 회전",
    description=(
        "Refresh Token 을 한 번 쓰고 새 access·refresh 토큰을 발급합니다. "
        "이미 쓴 Refresh Token 을 다시 보내면 그 계열 전체가 폐기됩니다(재사용 탐지)."
    ),
    operation_id="authRefresh",
    dependencies=[PublicWrite],
    responses=_UNAUTH,
)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return _token_response(await service.rotate(payload.refresh_token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="로그아웃",
    description="Refresh Token 의 계열을 폐기합니다. 이미 폐기됐어도 204 입니다(멱등).",
    operation_id="authLogout",
    dependencies=[PublicWrite],
    responses=_UNAUTH,
)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=AuthUserResponse,
    summary="현재 사용자",
    description="Bearer access token 으로 현재 로그인 사용자를 반환합니다(보호 엔드포인트).",
    operation_id="authMe",
    responses=_UNAUTH,
)
async def me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(current_user)
