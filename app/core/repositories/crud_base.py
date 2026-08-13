"""
기본 CRUD 베이스 클래스

모든 Repository의 최하위 기반 클래스입니다.
가장 기본적인 CRUD 작업만 제공합니다.

사용법:
    class BaseRepository(CRUDBase[ModelType]):
        # CRUDBase를 상속받아 확장 기능 구현
        ...
"""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.models_base import Base

ModelType = TypeVar("ModelType", bound=Base)


class CRUDBase(Generic[ModelType]):
    """
    기본 CRUD 베이스 클래스

    가장 기본적인 데이터베이스 CRUD 작업을 제공합니다.
    BaseRepository가 이 클래스를 상속받아 확장 기능을 구현합니다.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        db_session: 비동기 데이터베이스 세션

    Type Parameters:
        ModelType: Base를 상속한 SQLAlchemy 모델 타입
    """

    model: type[ModelType]

    def __init__(self, db_session: AsyncSession) -> None:
        """
        CRUDBase 초기화

        Args:
            db_session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        self.db_session = db_session

    @property
    def session(self) -> AsyncSession:
        """Deprecated — ``db_session`` 을 쓸 것 (TX-005 전환 기간용 별칭)."""
        return self.db_session

    async def _get(self, id: str | UUID) -> ModelType | None:
        """
        ID로 엔티티를 조회합니다 (내부용).

        Args:
            id: 조회할 엔티티의 ID

        Returns:
            모델 인스턴스 또는 None
        """
        return await self.db_session.get(self.model, str(id))

    async def _add(self, entity: ModelType) -> ModelType:
        """
        엔티티를 추가합니다 (내부용).

        Args:
            entity: 추가할 모델 인스턴스

        Returns:
            추가된 모델 인스턴스
        """
        self.db_session.add(entity)
        await self.db_session.flush()
        await self.db_session.refresh(entity)
        return entity

    async def _update(self, entity: ModelType) -> ModelType:
        """
        엔티티를 업데이트합니다 (내부용).

        Args:
            entity: 업데이트할 모델 인스턴스

        Returns:
            업데이트된 모델 인스턴스
        """
        return await self._add(entity)

    async def _delete(self, entity: ModelType) -> None:
        """
        엔티티를 삭제합니다 (내부용).

        Args:
            entity: 삭제할 모델 인스턴스
        """
        await self.db_session.delete(entity)
        await self.db_session.flush()
