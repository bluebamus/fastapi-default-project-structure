"""User Repository — 사용자 데이터 접근.

BaseRepository 의 CRUD 를 그대로 사용하고, username 조회만 특화로 추가한다.
"""

from sqlalchemy import select

from app.core.repositories.repository_base import BaseRepository
from app.features.user.models.models import User


class UserRepository(BaseRepository[User]):
    """사용자 Repository."""

    model = User

    async def get_by_username(self, username: str) -> User | None:
        """사용자명으로 단건 조회한다.

        문자열 컬럼명을 받는 범용 필터가 아니라 SQLAlchemy 속성으로 쓴다 —
        컬럼 이름이 바뀌면 실행 전에 드러난다(ORM-REP-005).
        """
        statement = select(User).where(User.username == username)
        result = await self.db_session.execute(statement)
        return result.scalars().first()
