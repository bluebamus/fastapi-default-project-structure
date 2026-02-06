"""
Home 도메인 전용 UnitOfWork 구현.

이 모듈은 Home 도메인에서 사용하는 UnitOfWork 클래스를 정의한다.
Home 도메인은 사용자 접속 로그와 관련된 기능을 담당한다.

설계 원칙:
    - 각 도메인은 자신만의 UnitOfWork를 가진다
    - 도메인 UnitOfWork는 해당 도메인의 Repository만 포함한다
    - 다른 도메인의 Repository는 알지 못한다

사용 예시:
    # API 엔드포인트에서 (UoW를 Service에 주입)
    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow)
        logs = await service.get_recent_logs(limit=50)

    # 백그라운드 태스크에서
    async with HomeBackgroundUnitOfWork() as uow:
        service = UserAccessLogService(uow)
        await service.create_access_log(data)  # auto_commit=True (기본값)
"""

from typing import Self

from app.database.unit_of_work import BaseUnitOfWork, BaseBackgroundUnitOfWork
from app.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.utils.logger import get_logger

logger = get_logger("home_uow")


class HomeUnitOfWork(BaseUnitOfWork):
    """
    Home 도메인 전용 UnitOfWork.

    접속 로그 관련 Repository를 포함하며, Home 도메인의 모든 API 엔드포인트에서
    이 UnitOfWork를 사용하여 데이터에 접근한다.

    이 클래스는 BaseUnitOfWork를 상속받아 세션 관리 기능을 재사용하고,
    Home 도메인에 필요한 Repository만 초기화한다.

    Attributes:
        user_access_logs: 사용자 접속 로그 Repository
            - 접속 로그 CRUD 작업
            - IP별, 사용자별 조회
            - 통계 집계

    Example:
        # 세션을 주입받아 사용 (FastAPI Depends)
        async with HomeUnitOfWork(session) as uow:
            logs = await uow.user_access_logs.get_recent_logs(limit=50)

        # 세션 자동 생성
        async with HomeUnitOfWork() as uow:
            log = await uow.user_access_logs.create({...})
            await uow.commit()
    """

    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        """
        컨텍스트 진입 시 Home 도메인의 Repository를 초기화한다.

        부모 클래스의 __aenter__를 호출하여 세션을 생성/설정한 후,
        Home 도메인에 필요한 Repository 인스턴스를 생성한다.

        Returns:
            Self: HomeUnitOfWork 인스턴스
        """
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        logger.debug("[HomeUnitOfWork] Repository 초기화 완료: user_access_logs")
        return self


class HomeBackgroundUnitOfWork(BaseBackgroundUnitOfWork):
    """
    Home 도메인의 백그라운드 작업용 UnitOfWork.

    미들웨어에서 접속 로그를 비동기적으로 저장할 때 사용한다.
    메인 API 커넥션 풀과 분리되어 있어 API 응답 지연을 방지한다.

    주요 사용 사례:
        - UserInfoMiddleware에서 접속 로그 저장
        - 비동기 로그 집계 작업
        - 백그라운드 통계 처리

    Attributes:
        user_access_logs: 사용자 접속 로그 Repository

    Example:
        # 미들웨어에서 백그라운드로 로그 저장
        async def _save_access_log(data: dict) -> None:
            async with HomeBackgroundUnitOfWork() as uow:
                service = UserAccessLogService(uow)
                await service.create_access_log(data)  # auto_commit=True (기본값)
    """

    user_access_logs: UserAccessLogRepository

    async def __aenter__(self) -> Self:
        """
        백그라운드 세션으로 컨텍스트에 진입하고 Repository를 초기화한다.

        Returns:
            Self: HomeBackgroundUnitOfWork 인스턴스
        """
        await super().__aenter__()
        self.user_access_logs = UserAccessLogRepository(self._session)
        logger.debug("[HomeBackgroundUnitOfWork] Repository 초기화 완료: user_access_logs")
        return self
