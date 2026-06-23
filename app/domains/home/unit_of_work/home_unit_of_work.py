"""
Home 도메인 전용 UnitOfWork 구현.

이 모듈은 Home 도메인에서 사용하는 UnitOfWork 클래스를 정의한다.
Home 도메인은 사용자 접속 로그와 관련된 기능을 담당한다.

설계 원칙:
    - 각 도메인은 자신만의 UnitOfWork를 가진다
    - 도메인 UnitOfWork는 해당 도메인의 Repository만 포함한다
    - repositories 맵을 선언하면 BaseUnitOfWork.__aenter__가 자동으로 초기화한다

사용 예시:
    # API 엔드포인트에서 (UoW를 Service에 주입)
    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow)
        logs = await service.get_recent_logs(limit=50)

    # 백그라운드 태스크에서
    async with HomeUnitOfWork(background=True) as uow:
        service = UserAccessLogService(uow)
        await service.create_access_log(data)
"""

from app.core.db.unit_of_work import BaseUnitOfWork
from app.domains.home.repositories.user_access_log_repository import UserAccessLogRepository


class HomeUnitOfWork(BaseUnitOfWork):
    """Home 도메인 전용 UnitOfWork (선언형 repositories 맵).

    Attributes:
        user_access_logs: 사용자 접속 로그 Repository

    Example:
        # 세션을 주입받아 사용 (FastAPI Depends)
        async with HomeUnitOfWork(session) as uow:
            logs = await uow.user_access_logs.get_recent_logs(limit=50)

        # 백그라운드 풀 사용
        async with HomeUnitOfWork(background=True) as uow:
            log = await uow.user_access_logs.create({...})
            await uow.commit()
    """

    user_access_logs: UserAccessLogRepository
    repositories = {"user_access_logs": UserAccessLogRepository}


class HomeBackgroundUnitOfWork(HomeUnitOfWork):
    """DEPRECATED: HomeUnitOfWork(background=True)를 사용하라. 호환을 위해 유지."""

    def __init__(self, session=None):
        super().__init__(session, background=True)
