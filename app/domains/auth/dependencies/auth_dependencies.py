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
    session: AsyncSession = Depends(get_session),
) -> User:
    """Bearer access token 을 검증해 현재 사용자를 반환한다(실패 시 401).

    인증은 읽기 전용이므로 커밋하는 ``get_auth_service`` 대신 세션에서 직접
    Service 를 구성한다. 이렇게 해야 인증+쓰기 의존성을 함께 쓰는 엔드포인트에서
    한 세션에 커밋 주체가 둘이 되는 이중 커밋(부분 저장) 위험이 사라지고,
    인증된 읽기 요청마다 불필요한 COMMIT 왕복도 없앤다(검수 W2/REQ-009).
    """
    service = AuthService(session)
    try:
        payload = decode_token(token, token_type=ACCESS_TOKEN_TYPE)
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenException() from exc

    user_id = payload.get("sub")
    user = await service.get_user_by_id(user_id) if user_id else None
    if user is None or not user.is_active:
        raise InvalidTokenException()
    return user
