"""Auth 서비스 — 회원가입/인증/토큰 발급·회전·로그아웃.

user 도메인의 `User` 모델·`UserRepository` 에 대해 인증한다(자격증명은 users.hashed_password).
auth 는 횡단 관심사라 user 식별 모델에 의존하는 것을 허용한다.

협력 객체(해시·토큰·회전 저장소)는 생성자로 받는다 — 조립은 ``get_auth_service`` provider 가
한다(service-hardening C-1). 커밋은 핸들러가 한다.
"""

import uuid
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import InvalidTokenException, TokenService, TokenType
from app.core.services.services_base import BaseService
from app.features.auth.exceptions import (
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from app.features.auth.schemas.auth_schema import RegisterRequest
from app.features.auth.services.password_hasher import PasswordHasher
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository


class TokenPair(NamedTuple):
    """발급한 토큰 한 쌍과 access 유효 시간(초)."""

    access_token: str
    refresh_token: str
    expires_in: int


class AuthService(BaseService):
    """인증 비즈니스 로직(세션 기반). 커밋은 핸들러가 담당."""

    def __init__(
        self,
        db_session: AsyncSession,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        refresh_store: RefreshTokenStore,
    ) -> None:
        super().__init__(db_session)
        self.users = UserRepository(db_session)
        self.password_hasher = password_hasher
        self.tokens = token_service
        self.refresh_store = refresh_store

    async def register(self, data: RegisterRequest) -> User:
        """사용자를 생성한다(사용자명 중복 시 409)."""
        if await self.users.get_by_username(data.username) is not None:
            raise UsernameAlreadyExistsException()
        hashed = await self.password_hasher.hash(data.password)
        return await self.users.create(
            {
                "username": data.username,
                "email": data.email,
                "hashed_password": hashed,
            }
        )

    async def authenticate(self, username: str, password: str) -> tuple[User, bool]:
        """사용자명/비밀번호를 검증한다(실패 시 401).

        Returns:
            ``(사용자, 재해시 여부)``. 재해시면(레거시 bcrypt → Argon2) 새 해시를 flush 까지
            해 두었으므로 호출자가 커밋해야 저장된다.
        """
        user = await self.users.get_by_username(username)
        # 사용자 부재/비밀번호 미설정이어도 해시기가 더미 해시로 같은 비용을 치른다(타이밍 균등화).
        stored = user.hashed_password if user else None
        password_ok, new_hash = await self.password_hasher.verify_and_update(
            password, stored or None
        )
        if user is None or not user.is_active or not password_ok:
            raise InvalidCredentialsException()
        if new_hash is None:
            return user, False
        await self.users.update_by_id(user.id, {"hashed_password": new_hash})
        return user, True

    async def issue_tokens(self, user: User) -> TokenPair:
        """새 family 로 access/refresh 토큰을 발급한다(로그인)."""
        return await self._issue_pair(user, family=uuid.uuid4().hex)

    async def rotate(self, refresh_token: str) -> TokenPair:
        """refresh 토큰을 한 번 쓰고 같은 family 의 새 쌍을 발급한다.

        이미 쓰인 토큰이 다시 오면(재사용) 탈취로 보고 family 전체를 폐기한다 — 정상 사용자와
        공격자 중 누가 먼저 썼는지 서버는 모르므로 둘 다 다시 로그인하게 한다(OAuth 2.0 Security
        BCP §4.14).
        """
        claims = self.tokens.decode(refresh_token, TokenType.REFRESH)
        family = claims.get("fam")
        if not isinstance(family, str):
            raise InvalidTokenException()
        if await self.refresh_store.is_family_revoked(family):
            raise InvalidTokenException()

        record = await self.refresh_store.consume(claims["jti"])
        if record is None or record.get("fam") != family or record.get("sub") != claims["sub"]:
            await self.refresh_store.revoke_family(family)
            self.log.warning("refresh 토큰 재사용 탐지 — family 폐기")
            raise InvalidTokenException()

        user = await self.users.get_by_id(claims["sub"])
        if user is None or not user.is_active:
            await self.refresh_store.revoke_family(family)
            raise InvalidTokenException()
        return await self._issue_pair(user, family=family)

    async def logout(self, refresh_token: str) -> None:
        """refresh 토큰의 family 를 폐기한다. 이미 폐기된 family 여도 성공한다(멱등)."""
        claims = self.tokens.decode(refresh_token, TokenType.REFRESH)
        family = claims.get("fam")
        if not isinstance(family, str):
            raise InvalidTokenException()
        await self.refresh_store.revoke_family(family)

    async def _issue_pair(self, user: User, family: str) -> TokenPair:
        access = self.tokens.issue_access(user.id, user.username)
        refresh = self.tokens.issue_refresh(user.id, family)
        await self.refresh_store.register(refresh.jti, user.id, family)
        return TokenPair(access.token, refresh.token, access.ttl_seconds)
