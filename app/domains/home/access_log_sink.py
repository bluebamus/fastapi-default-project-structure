"""
Home-domain implementation of the AccessLogSink Protocol.

Persists access-log entries using HomeBackgroundUnitOfWork so that the
operation runs in the background connection pool and does not interfere
with the main API connection pool.
"""

from app.domains.home.unit_of_work import HomeBackgroundUnitOfWork
from app.domains.home.services.user_access_log_service import UserAccessLogService


class HomeAccessLogSink:
    """Saves access-log entries via the Home domain's background unit-of-work."""

    async def save(self, data: dict) -> None:
        async with HomeBackgroundUnitOfWork() as uow:
            service = UserAccessLogService(uow)
            await service.create_access_log(data)
