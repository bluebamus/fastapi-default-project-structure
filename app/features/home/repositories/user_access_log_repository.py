"""
UserAccessLog Repository

접속 로그 데이터 접근 로직을 캡슐화합니다.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import TypedReturnsRows

from app.core.repositories.repository_base import BaseRepository
from app.features.home.models.models import UserAccessLog
from app.utils.logs import get_logger

logger = get_logger("user_access_log_repository")


class UserAccessLogRepository(BaseRepository[UserAccessLog]):
    """
    UserAccessLog Repository

    접속 로그에 대한 CRUD 및 특화된 쿼리를 제공합니다.
    """

    model = UserAccessLog

    def __init__(self, db_session: AsyncSession) -> None:
        """
        UserAccessLogRepository 초기화

        Args:
            session: 비동기 데이터베이스 세션
        """
        super().__init__(db_session)

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
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._execute(stmt, "get_by_ip")
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
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._execute(stmt, "get_by_user_id")
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
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._execute(stmt, "get_by_date_range")
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

        stmt = select(self.model.device_type, func.count(self.model.id)).group_by(
            self.model.device_type
        )
        result = await self._execute(stmt, "count_by_device_type")
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

        stmt = select(self.model.os_name, func.count(self.model.id)).group_by(self.model.os_name)
        result = await self._execute(stmt, "count_by_os")
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

        stmt = select(self.model.browser_name, func.count(self.model.id)).group_by(
            self.model.browser_name
        )
        result = await self._execute(stmt, "count_by_browser")
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
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
        )
        result = await self._execute(stmt, "get_recent_logs")
        logs = result.scalars().all()

        logger.debug(f"[get_recent_logs] 조회 완료: count={len(logs)}")
        return logs

    async def delete_created_before(self, cutoff: datetime, limit: int) -> int:
        """``created_at < cutoff`` 인 행을 **최대 ``limit`` 건** 지우고 지운 수를 돌려준다(커밋은 호출자).

        id 를 먼저 고르고 그 id 로 지운다 — MySQL 의 ``DELETE ... LIMIT`` 는 SQLite 에 없고, MySQL 은
        ``IN (SELECT ... LIMIT)`` 를 받지 않는다. 두 방언에서 같은 쿼리로 동작하고, 고르는 쪽은
        ``ix_user_access_logs_created_at`` 을 탄다(security-ops-hardening ADR-002).
        """
        ids_stmt = (
            select(self.model.id)
            .where(self.model.created_at < cutoff)
            .order_by(self.model.created_at)
            .limit(limit)
        )
        ids = (await self._execute(ids_stmt, "delete_created_before.select")).scalars().all()
        if not ids:
            return 0
        stmt = (
            delete(self.model)
            .where(self.model.id.in_(ids))
            .execution_options(synchronize_session=False)
        )
        result = await self._execute(cast("TypedReturnsRows[Any]", stmt), "delete_created_before")
        return cast("CursorResult[Any]", result).rowcount
