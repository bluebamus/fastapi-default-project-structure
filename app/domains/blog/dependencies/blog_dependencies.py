"""Blog 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합하여 view 에 제공한다.
yield 후 성공 시 커밋 — 제거된 UnitOfWork 의 트랜잭션 경계를 대체한다.
예외 시에는 get_session 의 teardown 이 롤백을 수행한다.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_session, get_session
from app.domains.blog.services.blog_service import BlogService


async def get_blog_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[BlogService, None]:
    """BlogService 를 구성해 view 에 제공하고, 요청 성공 시 커밋한다(쓰기 전용)."""
    service = BlogService(session)
    yield service
    await session.commit()


async def get_blog_service_readonly(
    session: AsyncSession = Depends(get_read_session),
) -> BlogService:
    """조회 엔드포인트용 — 커밋하지 않는다.

    쓰기용 의존성을 읽기에 재사용하면 조회마다 불필요한 COMMIT 왕복이 생기고,
    인증 등 다른 의존성과 함께 쓸 때 한 세션에 커밋 주체가 둘이 되는 위험이 있다
    (auth 의 get_current_user 가 같은 이유로 분리되어 있다).
    """
    return BlogService(session)
