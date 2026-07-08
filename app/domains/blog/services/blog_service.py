"""
Blog Service

게시글 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_session)이 책임진다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.domains.blog.exceptions import PostNotFoundException
from app.domains.blog.models.models import Post
from app.domains.blog.repositories.post_repository import PostRepository
from app.domains.blog.schemas.blog_schema import PostCreate, PostUpdate


class BlogService(BaseService):
    """게시글 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = PostRepository(session)

    async def create_post(self, data: PostCreate) -> Post:
        """게시글을 생성한다(커밋은 호출자가 수행)."""
        self.log.debug("게시글 생성: title=%s", data.title)
        return await self.repository.create(data.model_dump())

    async def get_post(self, post_id: str) -> Post:
        """게시글을 조회한다. 없으면 PostNotFoundException."""
        self.log.debug("게시글 조회: id=%s", post_id)
        post = await self.repository.get_by_id(post_id)
        if post is None:
            raise PostNotFoundException(detail={"id": post_id})
        return post

    async def list_posts(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Post], int]:
        """게시글 목록과 전체 개수를 조회한다."""
        self.log.debug("게시글 목록 조회: skip=%s limit=%s", skip, limit)
        posts = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return posts, total

    async def update_post(self, post_id: str, data: PostUpdate) -> Post:
        """게시글을 부분 수정한다. 없으면 PostNotFoundException."""
        self.log.debug("게시글 수정: id=%s", post_id)
        await self.get_post(post_id)  # 존재 보장
        updated = await self.repository.update(post_id, data.model_dump(exclude_unset=True))
        if updated is None:
            raise PostNotFoundException(detail={"id": post_id})
        return updated

    async def delete_post(self, post_id: str) -> None:
        """게시글을 삭제한다. 없으면 PostNotFoundException."""
        self.log.debug("게시글 삭제: id=%s", post_id)
        deleted = await self.repository.delete(post_id)
        if not deleted:
            raise PostNotFoundException(detail={"id": post_id})
