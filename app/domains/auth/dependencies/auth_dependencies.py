"""Auth 의존성 — 서비스 구성(트랜잭션 경계) + OAuth2 현재 사용자 해석."""
from collections.abc import AsyncGenerator

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.auth.exceptions import InvalidTokenException
from app.domains.auth.services.auth_service import AuthService
from app.domains.user.models.models import User
from app.utils.authenticator.auth import ACCESS_TOKEN_TYPE, decode_token

# 로그인 엔드포인트에서 access token 을 발급받는다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AuthService, None]:
    """AuthService 를 구성해 제공하고, 요청 성공 시 커밋한다."""
    service = AuthService(session)
    yield service
    await session.commit()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
) -> User:
    """Bearer access token 을 검증해 현재 사용자를 반환한다(실패 시 401)."""
    try:
        payload = decode_token(token, token_type=ACCESS_TOKEN_TYPE)
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenException() from exc

    user_id = payload.get("sub")
    user = await service.get_user_by_id(user_id) if user_id else None
    if user is None or not user.is_active:
        raise InvalidTokenException()
    return user
