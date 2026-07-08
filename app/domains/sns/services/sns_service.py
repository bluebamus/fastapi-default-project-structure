"""
SNS Service

피드 게시물 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_session)이 책임진다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.domains.sns.exceptions import SnsPostNotFoundException
from app.domains.sns.models.models import SnsPost
from app.domains.sns.repositories.sns_post_repository import SnsPostRepository
from app.domains.sns.schemas.sns_schema import SnsPostCreate, SnsPostUpdate


class SnsService(BaseService):
    """피드 게시물 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = SnsPostRepository(session)

    async def create_post(self, data: SnsPostCreate) -> SnsPost:
        """피드 게시물을 생성한다(커밋은 호출자가 수행)."""
        self.log.debug("피드 게시물 생성: author=%s", data.author)
        return await self.repository.create(data.model_dump())

    async def get_post(self, post_id: str) -> SnsPost:
        """피드 게시물을 조회한다. 없으면 SnsPostNotFoundException."""
        self.log.debug("피드 게시물 조회: id=%s", post_id)
        post = await self.repository.get_by_id(post_id)
        if post is None:
            raise SnsPostNotFoundException(detail={"id": post_id})
        return post

    async def list_posts(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[SnsPost], int]:
        """피드 게시물 목록과 전체 개수를 조회한다."""
        self.log.debug("피드 게시물 목록 조회: skip=%s limit=%s", skip, limit)
        posts = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return posts, total

    async def update_post(self, post_id: str, data: SnsPostUpdate) -> SnsPost:
        """피드 게시물을 부분 수정한다. 없으면 SnsPostNotFoundException."""
        self.log.debug("피드 게시물 수정: id=%s", post_id)
        await self.get_post(post_id)  # 존재 보장
        updated = await self.repository.update(post_id, data.model_dump(exclude_unset=True))
        if updated is None:
            raise SnsPostNotFoundException(detail={"id": post_id})
        return updated

    async def delete_post(self, post_id: str) -> None:
        """피드 게시물을 삭제한다. 없으면 SnsPostNotFoundException."""
        self.log.debug("피드 게시물 삭제: id=%s", post_id)
        deleted = await self.repository.delete(post_id)
        if not deleted:
            raise SnsPostNotFoundException(detail={"id": post_id})
