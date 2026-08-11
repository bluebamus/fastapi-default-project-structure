"""Auth 의존성 — 서비스 구성(트랜잭션 경계) + OAuth2 현재 사용자 해석."""

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_session, get_session
from app.features.auth.exceptions import InvalidTokenException
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User
from app.utils.authenticator.auth import ACCESS_TOKEN_TYPE, decode_token

# 로그인 엔드포인트에서 access token 을 발급받는다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
) -> AuthService:
    """AuthService 를 구성해 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다(P1-3).
    """
    return AuthService(session)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_read_session),
) -> User:
    """Bearer access token 을 검증해 현재 사용자를 반환한다(실패 시 401).

    인증은 읽기 전용이므로 커밋하는 ``get_auth_service`` 대신 세션에서 직접
    Service 를 구성한다. 이렇게 해야 인증+쓰기 의존성을 함께 쓰는 엔드포인트에서
    한 세션에 커밋 주체가 둘이 되는 이중 커밋(부분 저장) 위험이 사라지고,
    인증된 읽기 요청마다 불필요한 COMMIT 왕복도 없앤다(검수 W2/REQ-009).

    세션도 읽기 전용을 쓴다(P4-3). 커밋을 안 하는 것만으로는 조회가 여전히
    writer 로 가서, ``DB_ROUTER_ENABLED`` 를 켜도 인증 조회가 replica 로 분산되지
    않는다. 다른 도메인의 ``get_<name>_service_readonly`` 와 같은 기준이다.

    쓰기 의존성과 함께 쓰이는 라우트가 생기면 세션이 둘로 나뉜다(읽기용·쓰기용).
    커밋 주체가 하나로 유지되므로 의도된 동작이지만, 인증 단계에서 읽은 객체를
    쓰기 세션에서 수정하려 들면 다른 세션의 인스턴스라 반영되지 않는다. 그런
    라우트를 만들 때는 쓰기 세션에서 다시 조회할 것.
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
