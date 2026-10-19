"""접속 로그 보존 정책 — 보존 기간이 지난 행을 배치로 지운다 (security-ops-hardening ADR-002).

보존 일수와 기준 시각(시계)은 주입받는다. 조립은 ``build_access_log_retention_service``
(``ACCESS_LOG_RETENTION_DAYS``·``timezone_settings.utc_now``)가 하고, 실행은 Celery beat 의
``home.purge_expired_access_logs`` 가 하루 한 번 한다.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository

# 한 트랜잭션에서 지우는 최대 행 수 — 긴 잠금·거대한 undo 로그를 피한다.
DEFAULT_BATCH_SIZE = 5_000


class AccessLogRetentionService(BaseService):
    """``created_at < now - retention_days`` 인 접속 로그를 배치마다 커밋하며 지운다."""

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        retention_days: int,
        clock: Callable[[], datetime],
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """
        Args:
            retention_days: 보존 일수. 0 이면 지우지 않는다.
            clock: 현재 UTC aware 시각을 돌려준다(테스트는 고정 시계를 넣는다).
            batch_size: 한 번에 지울 최대 행 수.
        """
        if retention_days < 0:
            raise ValueError("retention_days 는 0 이상이어야 합니다.")
        if batch_size < 1:
            raise ValueError("batch_size 는 1 이상이어야 합니다.")
        super().__init__(db_session)
        self.repository = UserAccessLogRepository(db_session)
        self.retention_days = retention_days
        self.batch_size = batch_size
        self._clock = clock

    async def purge(self) -> int:
        """보존 기간이 지난 행을 모두 지우고 지운 총 행 수를 돌려준다(배치마다 커밋)."""
        if self.retention_days == 0:
            self.log.info("접속 로그 보존: 보존 일수 0 — 삭제하지 않음")
            return 0
        cutoff = self._clock() - timedelta(days=self.retention_days)
        total = 0
        while True:
            deleted = await self.repository.delete_created_before(cutoff, self.batch_size)
            await self.commit()
            total += deleted
            if deleted < self.batch_size:
                break
        self.log.info("접속 로그 보존: cutoff=%s 삭제=%d", cutoff.isoformat(), total)
        return total
