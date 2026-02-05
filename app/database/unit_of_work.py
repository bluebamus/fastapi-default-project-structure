"""
UnitOfWork 패턴의 기반 클래스

이 모듈은 모든 도메인별 UnitOfWork가 상속받는 추상 기반 클래스를 제공한다.
BaseUnitOfWork는 세션 관리와 트랜잭션 제어만을 담당하며,
구체적인 Repository 정의는 각 도메인의 하위 클래스에 위임한다.

설계 원칙:
    - 인프라 계층(database)은 도메인 계층을 알지 못한다
    - 도메인별 UnitOfWork가 이 기반 클래스를 상속받아 Repository를 정의한다
    - 의존성 방향: 도메인 -> 인프라 (올바른 방향)

사용 패턴:
    이 클래스는 직접 사용하지 않고, 도메인별 UnitOfWork를 통해 사용한다.

    # app/home/unit_of_work.py
    class HomeUnitOfWork(BaseUnitOfWork):
        user_access_logs: UserAccessLogRepository

        async def __aenter__(self) -> Self:
            await super().__aenter__()
            self.user_access_logs = UserAccessLogRepository(self._session)
            return self

    # 라우터에서 사용
    async with HomeUnitOfWork(session) as uow:
        logs = await uow.user_access_logs.get_recent_logs()
"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal, BackgroundSessionLocal
from app.utils.logger import get_logger

logger = get_logger("unit_of_work")


class BaseUnitOfWork:
    """
    UnitOfWork 패턴의 기반 클래스.

    이 클래스는 데이터베이스 세션의 생명주기와 트랜잭션 경계를 관리한다.
    Repository는 포함하지 않으며, 각 도메인별 하위 클래스에서 정의한다.

    이 클래스는 Python의 비동기 컨텍스트 매니저 프로토콜을 구현하여
    async with 구문과 함께 사용할 수 있다.

    Attributes:
        _session: 데이터베이스 세션 인스턴스
        _owns_session: 세션 소유권 여부 (True면 이 인스턴스가 세션을 생성함)

    Example:
        이 클래스는 직접 사용하지 않고, 하위 클래스를 통해 사용한다.

        class HomeUnitOfWork(BaseUnitOfWork):
            user_access_logs: UserAccessLogRepository

            async def __aenter__(self) -> Self:
                await super().__aenter__()
                self.user_access_logs = UserAccessLogRepository(self._session)
                return self
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        BaseUnitOfWork를 초기화한다.

        외부에서 세션을 주입받을 수 있으며, 주입받지 않은 경우
        컨텍스트 진입 시 자동으로 새 세션을 생성한다.

        Args:
            session: 외부에서 주입할 세션. None인 경우 자동 생성한다.
        """
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        """
        비동기 컨텍스트 매니저 진입점.

        세션이 주입되지 않은 경우 새 세션을 생성한다.
        하위 클래스에서는 이 메서드를 오버라이드하여 Repository를 초기화한다.

        Returns:
            Self: UnitOfWork 인스턴스 자신
        """
        if self._owns_session:
            self._session = AsyncSessionLocal()

        logger.debug("[BaseUnitOfWork] 컨텍스트 진입")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """
        비동기 컨텍스트 매니저 종료점.

        예외가 발생한 경우 자동으로 롤백을 수행한다.
        세션을 직접 생성한 경우(소유권이 있는 경우) 세션을 닫는다.

        Args:
            exc_type: 발생한 예외의 타입 (없으면 None)
            exc_val: 발생한 예외 인스턴스 (없으면 None)
            exc_tb: 예외의 트레이스백 (없으면 None)
        """
        if exc_type is not None:
            logger.error(
                f"[BaseUnitOfWork] 예외 발생으로 롤백: "
                f"{exc_type.__name__}: {exc_val}"
            )
            await self.rollback()

        if self._owns_session and self._session:
            await self._session.close()
            logger.debug("[BaseUnitOfWork] 세션 종료")

    @property
    def session(self) -> AsyncSession:
        """
        현재 세션을 반환한다.

        Returns:
            AsyncSession: 현재 활성화된 데이터베이스 세션

        Raises:
            RuntimeError: UnitOfWork가 컨텍스트에 진입하지 않은 경우
        """
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork가 시작되지 않았습니다. "
                "async with 구문 내에서 사용하세요."
            )
        return self._session

    async def commit(self) -> None:
        """
        현재 트랜잭션을 커밋한다.

        모든 변경 사항을 데이터베이스에 영구적으로 반영한다.
        """
        logger.debug("[BaseUnitOfWork] 커밋 수행")
        await self.session.commit()

    async def rollback(self) -> None:
        """
        현재 트랜잭션을 롤백한다.

        현재 트랜잭션에서 수행된 모든 변경 사항을 취소한다.
        """
        logger.debug("[BaseUnitOfWork] 롤백 수행")
        await self.session.rollback()

    async def flush(self) -> None:
        """
        세션의 변경 사항을 데이터베이스에 전송한다.

        flush는 변경 사항을 데이터베이스에 전송하지만 커밋하지는 않는다.
        이를 통해 데이터베이스에서 생성된 값(예: auto increment ID)을
        트랜잭션 커밋 전에 조회할 수 있다.
        """
        await self.session.flush()


class BaseBackgroundUnitOfWork(BaseUnitOfWork):
    """
    백그라운드 태스크용 UnitOfWork 기반 클래스.

    메인 API 요청과 분리된 커넥션 풀을 사용하여
    백그라운드 작업이 API 응답 성능에 영향을 주지 않도록 한다.

    주요 사용 사례:
        - 접속 로그 비동기 저장
        - 이메일 발송 기록
        - 통계 데이터 집계
        - 배치 작업
    """

    async def __aenter__(self) -> Self:
        """
        백그라운드 세션을 사용하여 컨텍스트에 진입한다.

        Returns:
            Self: UnitOfWork 인스턴스 자신
        """
        if self._owns_session:
            self._session = BackgroundSessionLocal()

        logger.debug("[BaseBackgroundUnitOfWork] 컨텍스트 진입")
        return self
