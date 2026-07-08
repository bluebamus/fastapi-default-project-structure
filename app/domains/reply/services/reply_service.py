"""
Reply Service

댓글 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_session)이 책임진다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.domains.reply.exceptions import ReplyNotFoundException
from app.domains.reply.models.models import Reply
from app.domains.reply.repositories.reply_repository import ReplyRepository
from app.domains.reply.schemas.reply_schema import ReplyCreate, ReplyUpdate


class ReplyService(BaseService):
    """댓글 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = ReplyRepository(session)

    async def create_reply(self, data: ReplyCreate) -> Reply:
        """댓글을 생성한다(커밋은 호출자가 수행)."""
        self.log.debug("댓글 생성: post_id=%s", data.post_id)
        return await self.repository.create(data.model_dump())

    async def get_reply(self, reply_id: str) -> Reply:
        """댓글을 조회한다. 없으면 ReplyNotFoundException."""
        self.log.debug("댓글 조회: id=%s", reply_id)
        reply = await self.repository.get_by_id(reply_id)
        if reply is None:
            raise ReplyNotFoundException(detail={"id": reply_id})
        return reply

    async def list_replies(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Reply], int]:
        """댓글 목록과 전체 개수를 조회한다."""
        self.log.debug("댓글 목록 조회: skip=%s limit=%s", skip, limit)
        replies = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return replies, total

    async def update_reply(self, reply_id: str, data: ReplyUpdate) -> Reply:
        """댓글을 부분 수정한다. 없으면 ReplyNotFoundException."""
        self.log.debug("댓글 수정: id=%s", reply_id)
        await self.get_reply(reply_id)  # 존재 보장
        updated = await self.repository.update(reply_id, data.model_dump(exclude_unset=True))
        if updated is None:
            raise ReplyNotFoundException(detail={"id": reply_id})
        return updated

    async def delete_reply(self, reply_id: str) -> None:
        """댓글을 삭제한다. 없으면 ReplyNotFoundException."""
        self.log.debug("댓글 삭제: id=%s", reply_id)
        deleted = await self.repository.delete(reply_id)
        if not deleted:
            raise ReplyNotFoundException(detail={"id": reply_id})
