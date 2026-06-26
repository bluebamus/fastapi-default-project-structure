"""기본 서비스 클래스.

세션을 주입받아 비즈니스 로직을 처리하는 모든 도메인 Service의 공통 기반.

설계 원칙 (UnitOfWork 제거 후):
    - Service 는 AsyncSession 을 주입받는다(트랜잭션 경계는 의존성/컨텍스트가 관리).
    - 데이터 접근은 Service 가 session 으로 생성한 Repository 를 통해 수행한다.
    - LoggerMixin 을 상속하여 self.log 로 클래스명이 주입된 로거를 쓴다(방식 C).

사용 패턴:
    class UserAccessLogService(BaseService):
        def __init__(self, session: AsyncSession) -> None:
            super().__init__(session)
            self.repository = UserAccessLogRepository(session)

        async def list(self, skip: int, limit: int):
            self.log.debug("목록 조회 skip=%s limit=%s", skip, limit)
            return await self.repository.get_all(skip=skip, limit=limit)
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logs import LoggerMixin


class BaseService(LoggerMixin):
    """세션 주입 기반 서비스 공통 클래스.

    트랜잭션 커밋/롤백은 호출하는 의존성(요청) 또는 background_session(비요청)이
    경계를 책임진다. Service 는 필요 시 commit()/rollback() 헬퍼를 쓸 수 있다.

    Attributes:
        session: 비동기 데이터베이스 세션
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        """현재 트랜잭션을 커밋한다(보통 의존성/컨텍스트가 대신 수행)."""
        await self.session.commit()

    async def rollback(self) -> None:
        """현재 트랜잭션을 롤백한다."""
        await self.session.rollback()
