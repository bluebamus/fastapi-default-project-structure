"""ORM 영속성 primitive (ORM-REP-001).

이 클래스가 갖는 책임은 **네 가지뿐**이다: 세션 보관, PK 조회, 인스턴스
추가/삭제, flush/refresh. 공개 CRUD 계약은 ``BaseRepository`` 가 담당한다.

여기에 두지 않는 것:
    · ``commit`` / ``rollback`` — 트랜잭션 경계는 쓰기 View 본문의 몫이다(TX-004).
      Base 가 커밋하면 한 요청에 커밋 주체가 둘이 되어 부분 저장이 생긴다.
    · HTTP 예외 생성 — Repository 는 HTTP 를 알지 않는다.
    · eager loading·도메인 전용 쿼리 — 기능 Repository 가 소유한다.
"""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.models_base import Base

ModelType = TypeVar("ModelType", bound=Base)


class CRUDBase(Generic[ModelType]):
    """ORM 인스턴스의 최소 영속성 primitive.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        db_session: 비동기 데이터베이스 세션
    """

    model: type[ModelType]

    def __init__(self, db_session: AsyncSession) -> None:
        """
        Args:
            db_session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        self.db_session = db_session

    @property
    def session(self) -> AsyncSession:
        """Deprecated — ``db_session`` 을 쓸 것 (TX-005 전환 기간용 별칭)."""
        return self.db_session

    async def _get(self, pk: str | UUID) -> ModelType | None:
        """PK 로 엔티티를 조회한다(식별자 맵 우선)."""
        return await self.db_session.get(self.model, str(pk))

    async def _add(self, entity: ModelType) -> ModelType:
        """엔티티를 추가하고 DB 가 채운 값까지 반영해 돌려준다."""
        self.db_session.add(entity)
        await self._flush()
        await self._refresh(entity)
        return entity

    async def _delete(self, entity: ModelType) -> None:
        """엔티티를 삭제한다."""
        await self.db_session.delete(entity)
        await self._flush()

    async def _flush(self) -> None:
        """보류 중인 변경을 DB 로 내보낸다(커밋하지 않는다).

        flush 는 트랜잭션 안에서 SQL 을 발행할 뿐이라, 롤백하면 그대로 사라진다.
        commit 과 혼동하지 말 것 — 이 계층은 커밋하지 않는다.
        """
        await self.db_session.flush()

    async def _refresh(self, entity: ModelType) -> None:
        """DB 가 채운 기본값·트리거 결과를 인스턴스에 다시 읽어온다."""
        await self.db_session.refresh(entity)
