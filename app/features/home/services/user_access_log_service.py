"""
UserAccessLog Service

접속 로그 관련 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
Service 메서드는 스스로 커밋하지 않는다. HTTP 라우트는 조회만 하고, 접속 로그 적재는 ``HomeAccessLogSink`` 가
``background_db_session`` 안에서 직접 커밋한다.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.home.exceptions import InvalidDateRangeException
from app.features.home.models.models import UserAccessLog
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.features.home.schemas.user_access_log_schema import (
    AccessLogStats,
    BrowserStats,
    DeviceTypeStats,
    OSStats,
    UserAccessLogCreate,
)


def fit_to_columns(data: dict[str, Any]) -> dict[str, Any]:
    """문자열 값을 ``UserAccessLog`` 컬럼 길이로 자른 사본을 돌려준다.

    헤더·경로·쿼리는 클라이언트가 길이를 정한다. MySQL strict 모드에서 길이 초과
    INSERT 는 실패하고, 접속 로그는 백그라운드라 그 실패가 조용히 버려진다 — 긴 헤더
    하나로 감사 기록을 피할 수 있었다(service-hardening ADR-007). 길이는 모델 컬럼에서
    읽는다(숫자를 두 번 적지 않는다). ``Text`` 처럼 길이가 없는 컬럼은 그대로 둔다.
    """
    columns = UserAccessLog.__table__.c
    fitted = dict(data)
    for name, value in data.items():
        if not isinstance(value, str) or name not in columns:
            continue
        length = getattr(columns[name].type, "length", None)
        if length is not None and len(value) > length:
            fitted[name] = value[:length]
    return fitted


class UserAccessLogService(BaseService):
    """접속 로그 비즈니스 로직 (세션 기반)."""

    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = UserAccessLogRepository(db_session)

    async def create_access_log(
        self,
        data: UserAccessLogCreate | dict[str, Any],
    ) -> UserAccessLog:
        """접속 로그를 생성한다(커밋은 호출자가 수행)."""
        data_dict = data.model_dump() if isinstance(data, UserAccessLogCreate) else data
        self.log.debug("접속 로그 생성: path=%s", data_dict.get("request_path"))
        return await self.repository.create(fit_to_columns(data_dict))

    async def get_access_logs(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[UserAccessLog], int]:
        """접속 로그 목록과 전체 개수를 조회한다."""
        self.log.debug("접속 로그 목록 조회: skip=%s, limit=%s", skip, limit)
        logs = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total

    async def get_recent_logs(self, limit: int = 50) -> Sequence[UserAccessLog]:
        """최근 접속 로그를 조회한다."""
        self.log.debug("최근 접속 로그 조회: limit=%s", limit)
        return await self.repository.get_recent_logs(limit=limit)

    async def get_logs_by_ip(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """IP 주소로 접속 로그를 조회한다."""
        self.log.debug("IP별 접속 로그 조회: ip=%s", ip_address)
        return await self.repository.get_by_ip(ip_address=ip_address, skip=skip, limit=limit)

    async def get_logs_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """사용자 ID로 접속 로그를 조회한다."""
        self.log.debug("사용자별 접속 로그 조회: user_id=%s", user_id)
        return await self.repository.get_by_user_id(user_id=user_id, skip=skip, limit=limit)

    async def get_logs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """날짜 범위로 접속 로그를 조회한다."""
        if start_date > end_date:
            self.log.warning("잘못된 날짜 범위: start=%s end=%s", start_date, end_date)
            raise InvalidDateRangeException(
                detail={"start_date": str(start_date), "end_date": str(end_date)},
            )
        self.log.debug("날짜 범위 접속 로그 조회: %s ~ %s", start_date, end_date)
        return await self.repository.get_by_date_range(
            start_date=start_date, end_date=end_date, skip=skip, limit=limit
        )

    async def get_stats(self) -> AccessLogStats:
        """접속 로그 통계를 조회한다."""
        self.log.debug("접속 로그 통계 조회 시작")
        total_count = await self.repository.count()
        device_counts = await self.repository.count_by_device_type()
        os_counts = await self.repository.count_by_os()
        browser_counts = await self.repository.count_by_browser()
        return AccessLogStats(
            total_count=total_count,
            device_types=[
                DeviceTypeStats(device_type=k, count=v) for k, v in device_counts.items()
            ],
            os_list=[OSStats(os_name=k, count=v) for k, v in os_counts.items()],
            browsers=[BrowserStats(browser_name=k, count=v) for k, v in browser_counts.items()],
        )
