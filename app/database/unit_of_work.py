"""
Unit of Work 패턴 구현

트랜잭션 경계를 관리하고 Repository를 통합합니다.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.utils.logger import get_logger

logger = get_logger("uow")


class UnitOfWork:
    """
    Unit of Work 패턴 구현

    트랜잭션 경계를 관리하고 여러 Repository를 통합하여
    일관된 데이터 접근을 제공합니다.

    사용 예시:
        async with UnitOfWork() as uow:
            log = await uow.user_access_logs.create(data)
            await uow.commit()

    Attributes:
        session: 비동기 데이터베이스 세션
        user_access_logs: UserAccessLogRepository 인스턴스
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        UnitOfWork 초기화

        Args:
            session: 외부에서 주입할 세션 (선택적)
        """
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        """
        컨텍스트 매니저 진입

        Returns:
            UnitOfWork 인스턴스
        """
        if self._owns_session:
            self._session = AsyncSessionLocal()

        logger.debug("[1/3] UnitOfWork 시작")
        self._init_repositories()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        컨텍스트 매니저 종료

        예외 발생 시 롤백, 정상 종료 시 세션 닫기
        """
        if exc_type is not None:
            logger.error(f"[UnitOfWork] 예외 발생으로 롤백: {exc_type.__name__}: {exc_val}")
            await self.rollback()

        if self._owns_session and self._session:
            await self._session.close()
            logger.debug("[3/3] UnitOfWork 종료")

    def _init_repositories(self) -> None:
        """Repository 인스턴스 초기화"""
        # 순환 참조 방지를 위해 지연 import
        from app.home.repositories.user_access_log_repository import (
            UserAccessLogRepository,
        )

        self.user_access_logs = UserAccessLogRepository(self._session)

    @property
    def session(self) -> AsyncSession:
        """현재 세션 반환"""
        if self._session is None:
            raise RuntimeError("UnitOfWork가 시작되지 않았습니다.")
        return self._session

    async def commit(self) -> None:
        """
        트랜잭션 커밋

        모든 변경사항을 데이터베이스에 반영합니다.
        """
        logger.debug("[2/3] UnitOfWork 커밋")
        await self.session.commit()

    async def rollback(self) -> None:
        """
        트랜잭션 롤백

        모든 변경사항을 취소합니다.
        """
        logger.debug("[UnitOfWork] 롤백 수행")
        await self.session.rollback()

    async def flush(self) -> None:
        """
        세션 플러시

        변경사항을 데이터베이스에 전송하지만 커밋하지 않습니다.
        """
        await self.session.flush()


class BackgroundUnitOfWork(UnitOfWork):
    """
    백그라운드 태스크용 Unit of Work

    메인 커넥션 풀과 분리된 백그라운드 풀을 사용합니다.
    """

    async def __aenter__(self) -> Self:
        """컨텍스트 매니저 진입 (백그라운드 세션 사용)"""
        if self._owns_session:
            self._session = BackgroundSessionLocal()

        logger.debug("[1/3] BackgroundUnitOfWork 시작")
        self._init_repositories()
        return self
