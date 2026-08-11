"""
UserProfile 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합해 view 에 제공한다.
yield 후 성공 시 커밋 — 트랜잭션 경계를 담당한다(UnitOfWork 대체).

예시:
    from collections.abc import AsyncGenerator
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.db.session import get_session
    from app.features.user_profile.services.user_profile_service import UserProfileService

    async def get_user_profile_service(
        session: AsyncSession = Depends(get_session),
    ) -> AsyncGenerator[UserProfileService, None]:
        service = UserProfileService(session)
        yield service
        await session.commit()
"""
