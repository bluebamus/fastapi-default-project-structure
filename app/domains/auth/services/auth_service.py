"""Auth 서비스 — 회원가입/인증/토큰 발급.

user 도메인의 `User` 모델·`UserRepository` 에 대해 인증한다(자격증명은 users.hashed_password).
auth 는 횡단 관심사라 user 식별 모델에 의존하는 것을 허용한다.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.domains.auth.exceptions import (
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from app.domains.auth.schemas.auth_schema import RegisterRequest
from app.domains.user.models.models import User
from app.domains.user.repositories.user_repository import UserRepository
from app.utils.authenticator.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


class AuthService(BaseService):
    """인증 비즈니스 로직(세션 기반). 커밋은 의존성이 담당."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.users = UserRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        """사용자를 생성한다(사용자명 중복 시 409)."""
        if await self.users.get_by_username(data.username) is not None:
            raise UsernameAlreadyExistsException()
        # bcrypt 해시는 CPU 집약적(수백 ms)이라 이벤트 루프를 막지 않도록 스레드로 격리한다.
        hashed = await asyncio.to_thread(hash_password, data.password)
        return await self.users.create(
            {
                "username": data.username,
                "email": data.email,
                "hashed_password": hashed,
            }
        )

    async def authenticate(self, username: str, password: str) -> User:
        """사용자명/비밀번호를 검증하고 사용자를 반환한다(실패 시 401)."""
        user = await self.users.get_by_username(username)
        if user is None or not user.hashed_password or not user.is_active:
            raise InvalidCredentialsException()
        # bcrypt 검증도 CPU 집약적이라 스레드로 격리(이벤트 루프 블로킹 방지).
        if not await asyncio.to_thread(verify_password, password, user.hashed_password):
            raise InvalidCredentialsException()
        return user

    def issue_tokens(self, user: User) -> tuple[str, str]:
        """access/refresh 토큰을 발급한다."""
        access = create_access_token(user.id, extra={"username": user.username})
        refresh = create_refresh_token(user.id)
        return access, refresh

    async def get_user_by_id(self, user_id: str) -> User | None:
        """ID 로 사용자를 조회한다."""
        return await self.users.get_one(id=user_id)
