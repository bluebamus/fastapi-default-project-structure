"""Auth 의존성 — 협력 객체 조립(provider) · 레이트 리밋 · 현재 사용자(DB 엔티티) 해석.

모든 협력 객체는 여기 provider 함수가 만들어 생성자로 넘긴다(service-hardening C-1). 테스트는
``app.dependency_overrides`` 로 provider 를 바꿔 끼운다 — Redis 는 ``get_redis`` 하나만 바꾸면
회전 저장소·레이트 리밋이 함께 따라온다.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.core.exception import TooManyRequestsException
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.redis import get_redis
from app.core.security.authorization import Principal
from app.core.security.dependencies import (
    get_current_principal,
    get_password_hasher,
    get_refresh_token_store,
    get_token_service,
)
from app.core.security.password_hasher import PasswordHasher
from app.core.security.rate_limit import RateLimiter
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import InvalidTokenException, TokenService
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from config import jwt_settings, middleware_settings


# =============================================================================
# 협력 객체 provider — 해시·토큰·회전 저장소 provider 는 user 기능도 쓰므로 core
# (``app/core/security/dependencies.py``)에 있다(service-hardening ADR-026).
# =============================================================================
def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    """lifespan 의 Redis 로 레이트 리밋을 만든다."""
    return RateLimiter(redis)


def get_client_ip_resolver() -> ClientIPResolver:
    """접속 로그와 같은 신뢰 프록시 홉 설정으로 클라이언트 IP 를 정한다(ADR-006)."""
    return ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS)


async def get_auth_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
) -> AuthService:
    """AuthService 를 구성해 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다(P1-3).
    """
    return AuthService(db_session, password_hasher, token_service, refresh_store)


# =============================================================================
# 레이트 리밋 (라우트 의존성 — 핸들러 본문이 아니라 주입으로 건다, ADR-016)
# =============================================================================
def _raise_if_denied(*results: tuple[bool, int]) -> None:
    denied = [retry_after for allowed, retry_after in results if not allowed]
    if denied:
        raise TooManyRequestsException(retry_after=max(denied))


async def login_rate_limit(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    limiter: RateLimiter = Depends(get_rate_limiter),
    resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> Callable[[], Awaitable[None]]:
    """로그인 시도를 IP+사용자명·IP 두 키로 센다. 초과면 429.

    ``form`` 은 핸들러와 같은 의존성이라 FastAPI 가 한 번만 파싱한다(요청 내 캐시).
    돌려주는 함수는 로그인 성공 시 핸들러가 불러 IP+사용자명 카운터를 지운다 — 정상 사용자가
    오타 몇 번 뒤 성공했을 때 남은 횟수가 다음 창까지 끌려가지 않게 한다. IP 카운터는 지우지
    않는다(성공 한 번으로 스터핑 한도를 되돌리지 못하게).
    """
    ip = resolver.resolve(request)
    user_key = f"auth:rl:login:{ip}:{form.username.lower()}"
    window = jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
    _raise_if_denied(
        await limiter.hit(user_key, jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS, window),
        await limiter.hit(f"auth:rl:login:{ip}", jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS, window),
    )

    async def reset_attempts() -> None:
        await limiter.reset(user_key)

    return reset_attempts


async def register_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
    resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> None:
    """회원가입 시도를 IP 단위로 센다. 초과면 429."""
    ip = resolver.resolve(request)
    _raise_if_denied(
        await limiter.hit(
            f"auth:rl:register:{ip}",
            jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS,
            jwt_settings.AUTH_REGISTER_WINDOW_SECONDS,
        )
    )


# =============================================================================
# 현재 사용자
# =============================================================================
async def get_current_user(
    principal: Principal = Depends(get_current_principal),
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> User:
    """Bearer access token 의 주체를 DB 에서 읽어 현재 사용자를 반환한다(실패 시 401).

    토큰 검증·``request.state.user_id`` 설정은 core 의 ``get_current_principal`` 이 한다. 이
    의존성은 사용자 **엔티티**가 필요한 곳(``/me``)에서만 쓴다 — 삭제·비활성화된 사용자를 즉시
    401 로 돌려보낸다. 인가만 필요한 라우트는 DB 를 보지 않는 ``CurrentPrincipal`` 을 쓴다
    (service-hardening ADR-017). 회전 저장소(Redis)·해시기가 필요 없으므로 ``AuthService`` 를
    조립하지 않는다 — 조회 하나를 위해 Redis 를 요청 경로에 끌어들이지 않는다.

    세션도 읽기 전용을 쓴다(P4-3). 커밋을 안 하는 것만으로는 조회가 여전히
    writer 로 가서, ``DB_ROUTER_ENABLED`` 를 켜도 인증 조회가 replica 로 분산되지
    않는다. 다른 도메인의 ``get_<name>_service_readonly`` 와 같은 기준이다.

    쓰기 의존성과 함께 쓰이는 라우트가 생기면 세션이 둘로 나뉜다(읽기용·쓰기용).
    커밋 주체가 하나로 유지되므로 의도된 동작이지만, 인증 단계에서 읽은 객체를
    쓰기 세션에서 수정하려 들면 다른 세션의 인스턴스라 반영되지 않는다. 그런
    라우트를 만들 때는 쓰기 세션에서 다시 조회할 것.
    """
    user = await UserRepository(db_session).get_by_id(principal.id)
    if user is None or not user.is_active:
        raise InvalidTokenException()
    return user
