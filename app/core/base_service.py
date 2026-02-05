"""
기본 서비스 클래스

Repository 패턴을 사용하는 서비스의 기본 클래스입니다.

이 모듈은 모든 도메인의 Service가 상속받는 범용 기반 클래스를 제공한다.
도메인별 폴더가 아닌 core 모듈에 위치하여 도메인 간 의존성 없이 공유할 수 있다.

설계 원칙:
    - BaseService는 도메인에 속하지 않는 공통 인프라 클래스이다
    - 모든 도메인의 Service가 이 클래스를 상속받아 Repository 주입 패턴을 사용한다
    - 의존성 방향: 도메인 Service -> core BaseService -> database BaseRepository

사용 패턴:
    class UserAccessLogService(BaseService[UserAccessLogRepository]):
        def __init__(self, repository: UserAccessLogRepository) -> None:
            super().__init__(repository)

        async def get_stats(self) -> AccessLogStats:
            total = await self.repository.count()
            ...
"""

from typing import Generic, TypeVar

from app.database.repositories.base import BaseRepository

R = TypeVar("R", bound=BaseRepository)


class BaseService(Generic[R]):
    """
    기본 서비스 클래스

    Repository를 주입받아 비즈니스 로직을 처리합니다.
    데이터 접근은 Repository에 위임합니다.

    Type Parameters:
        R: BaseRepository를 상속한 Repository 타입

    Attributes:
        repository: 데이터 접근을 위한 Repository
    """

    def __init__(self, repository: R) -> None:
        """
        BaseService 초기화

        Args:
            repository: 데이터 접근을 위한 Repository
        """
        self.repository = repository
