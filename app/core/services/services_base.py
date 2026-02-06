"""
기본 서비스 클래스

UnitOfWork 패턴을 사용하는 서비스의 기본 클래스입니다.

이 모듈은 모든 도메인의 Service가 상속받는 범용 기반 클래스를 제공한다.
도메인별 폴더가 아닌 core 모듈에 위치하여 도메인 간 의존성 없이 공유할 수 있다.

설계 원칙:
    - BaseService는 도메인에 속하지 않는 공통 인프라 클래스이다
    - 모든 도메인의 Service가 이 클래스를 상속받아 UoW 주입 패턴을 사용한다
    - Service는 UoW를 통해 트랜잭션을 제어할 수 있다
    - 의존성 방향: 도메인 Service -> core BaseService -> database BaseUnitOfWork

사용 패턴:
    class UserAccessLogService(BaseService[HomeUnitOfWork]):
        def __init__(self, uow: HomeUnitOfWork) -> None:
            super().__init__(uow)

        async def create_with_audit(self, data: dict) -> UserAccessLog:
            log = await self.uow.user_access_logs.create(data)
            await self.uow.commit()  # Service에서 트랜잭션 제어
            return log
"""

from typing import Generic, TypeVar

from app.database.unit_of_work import BaseUnitOfWork

UoW = TypeVar("UoW", bound=BaseUnitOfWork)


class BaseService(Generic[UoW]):
    """
    기본 서비스 클래스

    UnitOfWork를 주입받아 비즈니스 로직을 처리합니다.
    데이터 접근은 UoW의 Repository를 통해 수행합니다.
    트랜잭션 제어(commit/rollback)는 Service에서 담당합니다.

    Type Parameters:
        UoW: BaseUnitOfWork를 상속한 UnitOfWork 타입

    Attributes:
        uow: 트랜잭션 및 Repository 접근을 위한 UnitOfWork
    """

    def __init__(self, uow: UoW) -> None:
        """
        BaseService 초기화

        Args:
            uow: 트랜잭션 및 Repository 접근을 위한 UnitOfWork
        """
        self.uow = uow

    async def commit(self) -> None:
        """
        현재 트랜잭션을 커밋합니다.

        Service 메서드 내에서 데이터 변경 후 호출합니다.
        """
        await self.uow.commit()

    async def rollback(self) -> None:
        """
        현재 트랜잭션을 롤백합니다.

        예외 발생 시 또는 명시적 롤백이 필요할 때 호출합니다.
        """
        await self.uow.rollback()
