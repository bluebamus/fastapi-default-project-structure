"""인증·인가 의존성 — 모든 기능이 쓰는 provider 와 ``Principal`` 주입 (service-hardening ADR-017·026).

기능은 서로 import 하지 않으므로(C-2) 여러 기능이 쓰는 협력 객체의 provider 는 core 에 둔다:

- ``get_password_hasher`` — auth(가입·로그인)와 user(관리자의 사용자 생성)가 함께 쓴다.
- ``get_token_service`` — auth 는 발급, 여기 ``get_current_principal`` 은 검증.
- ``get_refresh_token_store`` — auth 는 회전, user 는 비활성화·삭제 시 ``revoke_user``.
- ``get_ownership_policy`` — blog·sns·reply·user 서비스의 수정·삭제 권한.

라우트는 타입 별칭으로 인증을 요구한다::

    async def create(..., principal: CurrentPrincipal): ...         # 로그인 사용자
    @router.post(..., dependencies=[Depends(require_superuser)])    # 슈퍼유저 전용

핸들러 본문은 토큰을 직접 파싱하지 않는다(C-7). 테스트는 ``app.dependency_overrides`` 로
provider 를 바꾸거나, 실제 ``TokenService`` 로 발급한 토큰을 헤더에 싣는다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from app.core.exception import ErrorResponse, ForbiddenException
from app.core.redis import get_redis
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.password_hasher import PasswordHasher
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import InvalidTokenException, TokenService, TokenType
from config import jwt_settings

# 로그인 엔드포인트에서 access token 을 발급받는다(OpenAPI 의 "Authorize" 버튼이 이 경로를 쓴다).
# 토큰이 없으면 FastAPI 가 401 + ``WWW-Authenticate: Bearer`` 를 낸다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# =============================================================================
# 협력 객체 provider
# =============================================================================
@lru_cache
def get_password_hasher() -> PasswordHasher:
    """프로세스에 하나 — 생성 시 더미 Argon2 해시를 한 번 만든다."""
    return PasswordHasher()


def get_token_service() -> TokenService:
    """설정으로 ``TokenService`` 를 만든다(상태 없음)."""
    return TokenService(jwt_settings)


def get_refresh_token_store(redis: Redis = Depends(get_redis)) -> RefreshTokenStore:
    """lifespan 의 Redis 로 회전 저장소를 만든다."""
    return RefreshTokenStore(redis, jwt_settings.refresh_token_ttl_seconds)


def get_ownership_policy() -> OwnershipPolicy:
    """소유권 규칙(상태 없음)."""
    return OwnershipPolicy()


# =============================================================================
# 인증 주체
# =============================================================================
async def get_current_principal(
    request: Request,
    token: str = Depends(oauth2_scheme),
    token_service: TokenService = Depends(get_token_service),
) -> Principal:
    """Bearer access token 을 검증해 ``Principal`` 을 만든다(실패 시 401). DB 를 보지 않는다.

    성공하면 ``request.state.user_id`` 를 채운다 — 접속 로그 미들웨어가 응답 뒤에 읽어 기록한다.
    """
    claims = token_service.decode(token, TokenType.ACCESS)
    username, is_superuser = claims["username"], claims["su"]
    if not isinstance(username, str) or not isinstance(is_superuser, bool):
        raise InvalidTokenException()
    principal = Principal(id=claims["sub"], username=username, is_superuser=is_superuser)
    request.state.user_id = principal.id
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


async def require_superuser(principal: CurrentPrincipal) -> Principal:
    """슈퍼유저가 아니면 403. 토큰이 없거나 틀리면 그 전에 401 이다."""
    if not principal.is_superuser:
        raise ForbiddenException()
    return principal


SuperuserPrincipal = Annotated[Principal, Depends(require_superuser)]


# =============================================================================
# OpenAPI 응답 문서 — 보호 라우트가 ``responses=`` 에 펼쳐 쓴다
# =============================================================================
UNAUTHORIZED_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 필요 — 토큰이 없거나 만료·위조됨"},
}
FORBIDDEN_RESPONSES: dict[int | str, dict[str, Any]] = {
    **UNAUTHORIZED_RESPONSES,
    403: {"model": ErrorResponse, "description": "권한 없음 — 소유자 또는 슈퍼유저만 허용"},
}
