"""User Repository — 사용자 데이터 접근.

BaseRepository 의 CRUD 를 그대로 사용하고, username 조회만 특화로 추가한다.
"""

from app.core.repositories.repository_base import BaseRepository
from app.domains.user.models.models import User


class UserRepository(BaseRepository[User]):
    """사용자 Repository."""

    model = User

    async def get_by_username(self, username: str) -> User | None:
        """사용자명으로 단건 조회한다."""
        return await self.get_one(username=username)
