"""
User Service

사용자 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_session)이 책임진다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.domains.user.exceptions import (
    UsernameDuplicateException,
    UserNotFoundException,
)
from app.domains.user.models.models import User
from app.domains.user.repositories.user_repository import UserRepository
from app.domains.user.schemas.user_schema import UserCreate, UserUpdate


class UserService(BaseService):
    """사용자 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = UserRepository(session)

    async def create_user(self, data: UserCreate) -> User:
        """사용자를 생성한다. 사용자명 중복 시 UsernameDuplicateException."""
        self.log.debug("사용자 생성: username=%s", data.username)
        if await self.repository.get_by_username(data.username) is not None:
            raise UsernameDuplicateException(detail={"username": data.username})
        return await self.repository.create(data.model_dump())

    async def get_user(self, user_id: str) -> User:
        """사용자를 조회한다. 없으면 UserNotFoundException."""
        self.log.debug("사용자 조회: id=%s", user_id)
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException(detail={"id": user_id})
        return user

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """사용자 목록과 전체 개수를 조회한다."""
        self.log.debug("사용자 목록 조회: skip=%s limit=%s", skip, limit)
        users = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return users, total

    async def update_user(self, user_id: str, data: UserUpdate) -> User:
        """사용자를 부분 수정한다. 없으면 UserNotFoundException."""
        self.log.debug("사용자 수정: id=%s", user_id)
        await self.get_user(user_id)  # 존재 보장
        updated = await self.repository.update(user_id, data.model_dump(exclude_unset=True))
        if updated is None:
            raise UserNotFoundException(detail={"id": user_id})
        return updated

    async def delete_user(self, user_id: str) -> None:
        """사용자를 삭제한다. 없으면 UserNotFoundException."""
        self.log.debug("사용자 삭제: id=%s", user_id)
        deleted = await self.repository.delete(user_id)
        if not deleted:
            raise UserNotFoundException(detail={"id": user_id})
