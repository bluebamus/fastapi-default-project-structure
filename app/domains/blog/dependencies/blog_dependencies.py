"""Blog 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합하여 view 에 제공한다.
yield 후 성공 시 커밋 — 제거된 UnitOfWork 의 트랜잭션 경계를 대체한다.
예외 시에는 get_session 의 teardown 이 롤백을 수행한다.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.domains.blog.services.blog_service import BlogService


async def get_blog_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[BlogService, None]:
    """BlogService 를 구성해 view 에 제공하고, 요청 성공 시 커밋한다."""
    service = BlogService(session)
    yield service
    await session.commit()
