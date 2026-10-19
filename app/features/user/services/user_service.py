"""
User Service

사용자 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_db_session)이 책임진다.

인가(service-hardening ADR-018): 목록·생성·삭제는 라우트가 슈퍼유저로 막고, 단건 조회·수정은
여기서 주입된 ``OwnershipPolicy`` 로 **본인 또는 슈퍼유저**만 허용한다. ``is_active``·``is_superuser``
변경은 슈퍼유저만 할 수 있다. 비활성화·삭제는 그 사용자의 refresh 토큰 family 를 모두 폐기한다
(``RefreshTokenStore.revoke_user``) — Redis 폐기는 커밋 전에 일어나므로, 커밋이 실패해도 토큰이
살아남는 쪽이 아니라 폐기된 쪽(안전한 쪽)으로 어긋난다.

관리 세션(admin-session-hardening ADR-002): 비활성화·슈퍼유저 강등·삭제는 그 사용자의 ``/admin`` 서버
세션도 모두 지운다(``AdminSessionStore.revoke_user``, 다른 브라우저 포함). 관리 화면을 끈 앱이면 저장소가
``None`` 이다. 비밀번호 변경 경로는 아직 없다 — 생기면 같은 자리에서 두 저장소를 함께 폐기한다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import ForbiddenException
from app.core.security.admin_session import AdminSessionStore
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.password_hasher import PasswordHasher
from app.core.security.refresh_store import RefreshTokenStore
from app.core.services.services_base import BaseService
from app.features.user.exceptions import (
    UsernameDuplicateException,
    UserNotFoundException,
)
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.schemas.user_schema import UserCreate, UserUpdate


class UserService(BaseService):
    """사용자 비즈니스 로직 (세션 기반)."""

    def __init__(
        self,
        db_session: AsyncSession,
        ownership: OwnershipPolicy,
        password_hasher: PasswordHasher,
        refresh_store: RefreshTokenStore,
        admin_sessions: AdminSessionStore | None,
    ) -> None:
        super().__init__(db_session)
        self.repository = UserRepository(db_session)
        self.ownership = ownership
        self.password_hasher = password_hasher
        self.refresh_store = refresh_store
        self.admin_sessions = admin_sessions

    async def create_user(self, data: UserCreate) -> User:
        """사용자를 생성한다(비밀번호는 Argon2 해시로 저장). 사용자명 중복 시 UsernameDuplicateException."""
        self.log.debug("사용자 생성: username=%s", data.username)
        if await self.repository.get_by_username(data.username) is not None:
            raise UsernameDuplicateException(detail={"username": data.username})
        hashed = await self.password_hasher.hash(data.password)
        return await self.repository.create(
            {**data.model_dump(exclude={"password"}), "hashed_password": hashed}
        )

    async def get_user(self, user_id: str, principal: Principal) -> User:
        """사용자를 조회한다 — 본인 또는 슈퍼유저만. 없으면 UserNotFoundException.

        권한을 존재 확인보다 먼저 본다 — 남의 ID 로 404/403 을 갈라 계정 존재를 캐지 못하게.
        """
        self.ownership.ensure_can_modify(user_id, principal)
        return await self._get(user_id)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """사용자 목록과 전체 개수를 조회한다."""
        self.log.debug("사용자 목록 조회: skip=%s limit=%s", skip, limit)
        users = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return users, total

    async def update_user(self, user_id: str, data: UserUpdate, principal: Principal) -> User:
        """사용자를 부분 수정한다 — 본인 또는 슈퍼유저만. 없으면 UserNotFoundException.

        ``is_active``·``is_superuser`` 를 보낸 요청은 슈퍼유저만 할 수 있다(본인이라도 403).
        비활성화하면 그 사용자의 refresh 토큰을 모두 폐기한다. 비활성화·강등은 관리 세션도 모두 폐기한다.
        """
        self.log.debug("사용자 수정: id=%s", user_id)
        self.ownership.ensure_can_modify(user_id, principal)
        if data.model_fields_set & UserUpdate.superuser_only_fields and not principal.is_superuser:
            raise ForbiddenException()
        existing = await self._get(user_id)  # 존재 보장(없으면 404)
        updated = await self.repository.update_by_id(user_id, data.model_dump(exclude_unset=True))
        if data.is_active is False:
            await self.refresh_store.revoke_user(user_id)
        if data.is_active is False or data.is_superuser is False:
            await self._revoke_admin_sessions(user_id)
        # updated 가 None 이면 변경행 0(동일 값 no-op, MySQL changed-rows 의미). 존재는 이미
        # 보장됐으므로 404 가 아니라 현재 엔티티를 반환한다.
        return updated if updated is not None else existing

    async def delete_user(self, user_id: str) -> None:
        """사용자를 삭제하고 refresh 토큰·관리 세션을 모두 폐기한다. 없으면 UserNotFoundException."""
        self.log.debug("사용자 삭제: id=%s", user_id)
        deleted = await self.repository.delete_by_id(user_id)
        if not deleted:
            raise UserNotFoundException(detail={"id": user_id})
        await self.refresh_store.revoke_user(user_id)
        await self._revoke_admin_sessions(user_id)

    async def _revoke_admin_sessions(self, user_id: str) -> None:
        if self.admin_sessions is not None:
            await self.admin_sessions.revoke_user(user_id)

    async def _get(self, user_id: str) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException(detail={"id": user_id})
        return user
