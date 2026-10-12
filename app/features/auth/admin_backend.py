"""SQLAdmin 로그인 — ``AdminAuthBackend`` (admin-login ADR-001~003).

``/admin`` 은 **활성 슈퍼유저**만 쓴다. 자격 확인은 API 로그인과 같은 ``AuthService.authenticate``
(사용자명 + 비밀번호, 레거시 bcrypt → Argon2 재해시 포함)를 그대로 쓰고, 레이트 리밋도 같은
``RateLimiter`` 와 한도 설정(``AUTH_LOGIN_*``)을 쓰되 키 접두사만 ``admin:rl:login:`` 으로 나눈다 —
API 로그인 실패가 관리 화면 한도를 깎지 않게.

세션은 서명된 쿠키(``admin_session``, starlette ``SessionMiddleware`` — itsdangerous)이고 사용자 id
하나만 담는다. ``authenticate`` 는 **요청마다** DB 에서 그 사용자를 다시 읽어, 강등·비활성화·삭제가
다음 요청부터 바로 반영된다(access 토큰의 R-014 와 다르다).

협력 객체는 생성자로 받는다(service-hardening C-1). 조립은 ``app/features/admin.py`` 의
``build_admin_auth_backend`` 가 기존 provider(``get_password_hasher``·``get_token_service``·
``get_refresh_token_store``·``get_rate_limiter``)로 한다. 이 모듈은 sqladmin 을 import 하므로
``ADMIN=false`` 에서 로드되지 않도록 auth 패키지 ``__init__`` 으로 재노출하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqladmin.authentication import AuthenticationBackend
from sqladmin.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.rate_limit import RateLimiter
from app.features.auth.exceptions import InvalidCredentialsException
from app.features.auth.services.auth_service import AuthService
from app.features.user.repositories.user_repository import UserRepository
from app.utils.logs import get_logger
from config import jwt_settings

logger = get_logger("admin_auth")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# 기존 세션 쿠키(SESSION_COOKIE_NAME, 기본 "session")와 겹치지 않는 이름.
ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
ADMIN_COOKIE_PATH = "/admin"
SESSION_USER_KEY = "user_id"
RATE_LIMIT_PREFIX = "admin:rl:login"
# 로그에 싣는 사용자명 길이 상한 — 폼 값은 공격자가 정한다.
LOG_USERNAME_MAX = 64
LOGIN_TEMPLATE = "sqladmin/login.html"
INVALID_LOGIN_MESSAGE = "사용자명 또는 비밀번호가 올바르지 않습니다."
TOO_MANY_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."


class AdminAuthBackend(AuthenticationBackend):
    """SQLAdmin 의 로그인·세션 확인·로그아웃."""

    def __init__(
        self,
        *,
        secret_key: str,
        https_only: bool,
        session_factory: SessionFactory,
        auth_service_factory: Callable[[Request, AsyncSession], AuthService],
        rate_limiter_factory: Callable[[Request], RateLimiter],
        client_ip_resolver: ClientIPResolver,
        max_age: int = ADMIN_SESSION_MAX_AGE_SECONDS,
    ) -> None:
        """
        Args:
            secret_key: 세션 쿠키 서명 키(``SESSION_SECRET_KEY``).
            https_only: 쿠키에 ``Secure`` 를 붙일지(staging/production 이면 True).
            session_factory: 요청 밖 DB 세션 컨텍스트(``background_db_session``).
            auth_service_factory: 세션으로 ``AuthService`` 를 만든다(해시기·토큰·회전 저장소 provider 조립).
            rate_limiter_factory: 요청의 앱이 연 Redis 로 ``RateLimiter`` 를 만든다.
            client_ip_resolver: 레이트 리밋·로그의 IP(``TRUSTED_PROXY_HOPS``).
            max_age: 세션 쿠키 수명(초).
        """
        super().__init__(
            secret_key,
            session_cookie=ADMIN_SESSION_COOKIE,
            max_age=max_age,
            path=ADMIN_COOKIE_PATH,
            same_site="strict",
            https_only=https_only,
        )
        self._session_factory = session_factory
        self._auth_service_factory = auth_service_factory
        self._rate_limiter_factory = rate_limiter_factory
        self._client_ip = client_ip_resolver
        # 429·400 화면을 SQLAdmin 과 같은 템플릿 환경으로 그린다. Admin 이 이 백엔드를 생성 인자로
        # 받으므로 생성 뒤에 연결한다(``create_admin_interface``).
        self.templates: Jinja2Templates | None = None

    async def login(self, request: Request) -> Response | bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        ip = self._client_ip.resolve(request)
        log_name = username[:LOG_USERNAME_MAX]

        limiter = self._rate_limiter_factory(request)
        user_key = f"{RATE_LIMIT_PREFIX}:{ip}:{username.lower()}"
        window = jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
        results = (
            await limiter.hit(user_key, jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS, window),
            await limiter.hit(
                f"{RATE_LIMIT_PREFIX}:{ip}", jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS, window
            ),
        )
        denied = [r.retry_after for r in results if not r.allowed]
        if denied:
            logger.warning("[admin] 로그인 한도 초과: username=%r ip=%s", log_name, ip)
            response = await self._render_login(request, TOO_MANY_MESSAGE, 429)
            response.headers["Retry-After"] = str(max(denied))
            return response

        user_id: str | None = None
        async with self._session_factory() as db_session:
            service = self._auth_service_factory(request, db_session)
            try:
                user, rehashed = await service.authenticate(username, password)
            except InvalidCredentialsException:
                user, rehashed = None, False
            # 사유(없는 사용자·틀린 비밀번호·비활성·일반 사용자)는 화면에서 구분하지 않는다.
            if user is not None and user.is_superuser:
                user_id = user.id
                if rehashed:
                    await db_session.commit()
        if user_id is None:
            logger.warning("[admin] 로그인 실패: username=%r ip=%s", log_name, ip)
            return await self._render_login(request, INVALID_LOGIN_MESSAGE, 400)

        await limiter.reset(user_key)
        # 세션 고정 방지 — 로그인 전 세션에 무엇이 있었든 버리고 id 하나만 남긴다.
        request.session.clear()
        request.session[SESSION_USER_KEY] = user_id
        logger.info("[admin] 로그인 성공: username=%r ip=%s", log_name, ip)
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        user_id = request.session.get(SESSION_USER_KEY)
        if not isinstance(user_id, str):
            return False
        async with self._session_factory() as db_session:
            user = await UserRepository(db_session).get_by_id(user_id)
            allowed = user is not None and user.is_active and user.is_superuser
        if not allowed:
            request.session.clear()
        return allowed

    async def logout(self, request: Request) -> Response | bool:
        request.session.clear()
        return True

    async def _render_login(self, request: Request, error: str, status_code: int) -> Response:
        if self.templates is None:
            raise RuntimeError("AdminAuthBackend.templates 가 연결되지 않았습니다.")
        return await self.templates.TemplateResponse(
            request, LOGIN_TEMPLATE, {"error": error}, status_code=status_code
        )
