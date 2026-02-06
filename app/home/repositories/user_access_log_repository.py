"""
UserAccessLog Repository

접속 로그 데이터 접근 로직을 캡슐화합니다.
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories.repository_base import BaseRepository
from app.home.models.models import UserAccessLog
from app.utils.logger import get_logger

logger = get_logger("user_access_log_repository")


class UserAccessLogRepository(BaseRepository[UserAccessLog]):
    """
    UserAccessLog Repository

    접속 로그에 대한 CRUD 및 특화된 쿼리를 제공합니다.
    """

    model = UserAccessLog

    def __init__(self, session: AsyncSession) -> None:
        """
        UserAccessLogRepository 초기화

        Args:
            session: 비동기 데이터베이스 세션
        """
        super().__init__(session)

    async def get_by_ip(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """
        IP 주소로 접속 로그를 조회합니다.

        Args:
            ip_address: 조회할 IP 주소
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[get_by_ip] 조회 시작: ip={ip_address}")

        stmt = (
            select(self.model)
            .where(self.model.ip_address == ip_address)
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        logger.debug(f"[get_by_ip] 조회 완료: count={len(logs)}")
        return logs

    async def get_by_user_id(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """
        사용자 ID로 접속 로그를 조회합니다.

        Args:
            user_id: 조회할 사용자 ID
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[get_by_user_id] 조회 시작: user_id={user_id}")

        stmt = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        logger.debug(f"[get_by_user_id] 조회 완료: count={len(logs)}")
        return logs

    async def get_by_date_range(
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
        """
        logger.debug(f"[get_by_date_range] 조회 시작: {start_date} ~ {end_date}")

        stmt = (
            select(self.model)
            .where(
                and_(
                    self.model.created_at >= start_date,
                    self.model.created_at <= end_date,
                )
            )
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        logger.debug(f"[get_by_date_range] 조회 완료: count={len(logs)}")
        return logs

    async def count_by_device_type(self) -> dict[str, int]:
        """
        장치 유형별 접속 수를 집계합니다.

        Returns:
            장치 유형별 접속 수 딕셔너리
        """
        logger.debug("[count_by_device_type] 집계 시작")

        stmt = (
            select(self.model.device_type, func.count(self.model.id))
            .group_by(self.model.device_type)
        )
        result = await self.session.execute(stmt)
        counts = {row[0] or "unknown": row[1] for row in result.all()}

        logger.debug(f"[count_by_device_type] 집계 완료: {counts}")
        return counts

    async def count_by_os(self) -> dict[str, int]:
        """
        OS별 접속 수를 집계합니다.

        Returns:
            OS별 접속 수 딕셔너리
        """
        logger.debug("[count_by_os] 집계 시작")

        stmt = (
            select(self.model.os_name, func.count(self.model.id))
            .group_by(self.model.os_name)
        )
        result = await self.session.execute(stmt)
        counts = {row[0] or "unknown": row[1] for row in result.all()}

        logger.debug(f"[count_by_os] 집계 완료: {counts}")
        return counts

    async def count_by_browser(self) -> dict[str, int]:
        """
        브라우저별 접속 수를 집계합니다.

        Returns:
            브라우저별 접속 수 딕셔너리
        """
        logger.debug("[count_by_browser] 집계 시작")

        stmt = (
            select(self.model.browser_name, func.count(self.model.id))
            .group_by(self.model.browser_name)
        )
        result = await self.session.execute(stmt)
        counts = {row[0] or "unknown": row[1] for row in result.all()}

        logger.debug(f"[count_by_browser] 집계 완료: {counts}")
        return counts

    async def get_recent_logs(self, limit: int = 50) -> Sequence[UserAccessLog]:
        """
        최근 접속 로그를 조회합니다.

        Args:
            limit: 최대 조회 수

        Returns:
            UserAccessLog 리스트
        """
        logger.debug(f"[get_recent_logs] 조회 시작: limit={limit}")

        stmt = (
            select(self.model)
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        logs = result.scalars().all()

        logger.debug(f"[get_recent_logs] 조회 완료: count={len(logs)}")
        return logs
