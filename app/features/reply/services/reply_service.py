"""
Reply Service

댓글 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계는 쓰기 핸들러(View)가 닫는다 — 응답 DTO 검증 뒤 ``await service.commit()`` 한 번.
요청 밖에서는 ``background_db_session`` 을 연 쪽이 커밋한다. Service 메서드는 스스로 커밋하지 않는다.

작성자는 인증 주체(``Principal``)로 서버가 채우고, 수정·삭제는 주입된 ``OwnershipPolicy`` 가
소유자 또는 슈퍼유저만 허용한다(service-hardening ADR-018).
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.services.services_base import BaseService
from app.features.reply.exceptions import ReplyNotFoundException
from app.features.reply.models.models import Reply
from app.features.reply.repositories.reply_repository import ReplyRepository
from app.features.reply.schemas.reply_schema import ReplyCreate, ReplyUpdate


class ReplyService(BaseService):
    """댓글 비즈니스 로직 (세션 기반)."""

    def __init__(self, db_session: AsyncSession, ownership: OwnershipPolicy) -> None:
        super().__init__(db_session)
        self.ownership = ownership
        self.repository = ReplyRepository(db_session)

    async def create_reply(self, data: ReplyCreate, principal: Principal) -> Reply:
        """댓글을 생성한다(커밋은 호출자가 수행)."""
        self.log.debug("댓글 생성: post_id=%s", data.post_id)
        # 작성자는 요청 본문이 아니라 인증 주체에서 온다 — 남의 이름으로 쓰지 못한다.
        return await self.repository.create(
            {**data.model_dump(), "author_id": principal.id, "author": principal.username}
        )

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
        replies = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return replies, total

    async def update_reply(self, reply_id: str, data: ReplyUpdate, principal: Principal) -> Reply:
        """댓글을 부분 수정한다. 없으면 ReplyNotFoundException."""
        self.log.debug("댓글 수정: id=%s", reply_id)
        existing = await self.get_reply(reply_id)  # 존재 보장(없으면 404)
        self.ownership.ensure_can_modify(existing.author_id, principal)
        updated = await self.repository.update_by_id(reply_id, data.model_dump(exclude_unset=True))
        # updated 가 None 이면 변경행 0(동일 값 no-op, MySQL changed-rows 의미). 존재는 이미
        # 보장됐으므로 404 가 아니라 현재 엔티티를 반환한다.
        return updated if updated is not None else existing

    async def delete_reply(self, reply_id: str, principal: Principal) -> None:
        """댓글을 삭제한다. 없으면 ReplyNotFoundException."""
        self.log.debug("댓글 삭제: id=%s", reply_id)
        existing = await self.get_reply(reply_id)  # 존재 보장(없으면 404)
        self.ownership.ensure_can_modify(existing.author_id, principal)
        deleted = await self.repository.delete_by_id(reply_id)
        if not deleted:
            raise ReplyNotFoundException(detail={"id": reply_id})
