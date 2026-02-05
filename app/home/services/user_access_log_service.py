"""
UserAccessLog Service

접속 로그 관련 비즈니스 로직을 처리합니다.
"""

from datetime import datetime
from typing import Any, Sequence

from app.home.home_exception import InvalidDateRangeException
from app.home.models.models import UserAccessLog
from app.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.home.schemas.user_access_log_schema import (
    UserAccessLogCreate,
    AccessLogStats,
    DeviceTypeStats,
    OSStats,
    BrowserStats,
)
from app.core.base_service import BaseService
from app.utils.logger import get_logger

logger = get_logger("user_access_log_service")


class UserAccessLogService(BaseService[UserAccessLogRepository]):
    """
    UserAccessLog Service

    접속 로그 관련 비즈니스 로직을 처리합니다.
    BaseService를 상속받아 Repository 패턴을 사용합니다.

    Attributes:
        repository: UserAccessLogRepository 인스턴스
    """

    def __init__(self, repository: UserAccessLogRepository) -> None:
        """
        UserAccessLogService 초기화

        Args:
            repository: UserAccessLogRepository 인스턴스
        """
        super().__init__(repository)

    async def create_access_log(
        self,
        data: UserAccessLogCreate | dict[str, Any],
    ) -> UserAccessLog:
        """
        접속 로그를 생성합니다.

        Args:
            data: 생성할 접속 로그 데이터

        Returns:
            생성된 UserAccessLog
        """
        request_path = data.get("request_path") if isinstance(data, dict) else data.request_path
        logger.debug(f"[1/2] 접속 로그 생성 시작: path={request_path}")

        if isinstance(data, UserAccessLogCreate):
            data_dict = data.model_dump()
        else:
            data_dict = data

        log = await self.repository.create(data_dict)

        logger.debug(f"[2/2] 접속 로그 생성 완료: id={log.id}")
        return log

    async def get_access_logs(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[UserAccessLog], int]:
        """
        접속 로그 목록을 조회합니다.

        Args:
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            (UserAccessLog 리스트, 전체 개수) 튜플
        """
        logger.debug(f"[1/2] 접속 로그 목록 조회 시작: skip={skip}, limit={limit}")

        logs = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()

        logger.debug(f"[2/2] 접속 로그 목록 조회 완료: count={len(logs)}, total={total}")
        return logs, total

    async def get_recent_logs(
        self,
        limit: int = 50,
    ) -> Sequence[UserAccessLog]:
        """
        최근 접속 로그를 조회합니다.

        Args:
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[1/2] 최근 접속 로그 조회 시작: limit={limit}")

        logs = await self.repository.get_recent_logs(limit=limit)

        logger.debug(f"[2/2] 최근 접속 로그 조회 완료: count={len(logs)}")
        return logs

    async def get_logs_by_ip(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """
        IP 주소로 접속 로그를 조회합니다.

        Args:
            ip_address: IP 주소
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[1/2] IP별 접속 로그 조회 시작: ip={ip_address}")

        logs = await self.repository.get_by_ip(
            ip_address=ip_address,
            skip=skip,
            limit=limit,
        )

        logger.debug(f"[2/2] IP별 접속 로그 조회 완료: count={len(logs)}")
        return logs

    async def get_logs_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """
        사용자 ID로 접속 로그를 조회합니다.

        Args:
            user_id: 사용자 ID
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[1/2] 사용자별 접속 로그 조회 시작: user_id={user_id}")

        logs = await self.repository.get_by_user_id(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

        logger.debug(f"[2/2] 사용자별 접속 로그 조회 완료: count={len(logs)}")
        return logs

    async def get_logs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """
        날짜 범위로 접속 로그를 조회합니다.

        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트

        Raises:
            BadRequestException: 시작 날짜가 종료 날짜보다 늦은 경우
        """
        # 날짜 범위 유효성 검증
        if start_date > end_date:
            logger.warning(f"[VALIDATION] 잘못된 날짜 범위: start={start_date}, end={end_date}")
            raise InvalidDateRangeException(
                detail={"start_date": str(start_date), "end_date": str(end_date)},
            )

        logger.debug(f"[1/2] 날짜 범위 접속 로그 조회 시작: {start_date} ~ {end_date}")

        logs = await self.repository.get_by_date_range(
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )

        logger.debug(f"[2/2] 날짜 범위 접속 로그 조회 완료: count={len(logs)}")
        return logs

    async def get_stats(self) -> AccessLogStats:
        """
        접속 로그 통계를 조회합니다.

        Returns:
            AccessLogStats
        """
        logger.debug("[1/4] 접속 로그 통계 조회 시작")

        # 전체 개수
        total_count = await self.repository.count()
        logger.debug(f"[2/4] 전체 개수: {total_count}")

        # 장치 유형별 통계
        device_counts = await self.repository.count_by_device_type()
        device_types = [
            DeviceTypeStats(device_type=k, count=v)
            for k, v in device_counts.items()
        ]
        logger.debug("[3/4] 장치 유형별 통계 완료")

        # OS별 통계
        os_counts = await self.repository.count_by_os()
        os_list = [
            OSStats(os_name=k, count=v)
            for k, v in os_counts.items()
        ]

        # 브라우저별 통계
        browser_counts = await self.repository.count_by_browser()
        browsers = [
            BrowserStats(browser_name=k, count=v)
            for k, v in browser_counts.items()
        ]

        logger.debug("[4/4] 접속 로그 통계 조회 완료")

        return AccessLogStats(
            total_count=total_count,
            device_types=device_types,
            os_list=os_list,
            browsers=browsers,
        )


def get_user_access_log_service(repository: UserAccessLogRepository) -> UserAccessLogService:
    """
    UserAccessLogService 팩토리 함수

    Args:
        repository: UserAccessLogRepository 인스턴스

    Returns:
        UserAccessLogService 인스턴스
    """
    return UserAccessLogService(repository)
