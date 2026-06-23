"""
Home-domain implementation of the AccessLogSink Protocol.

Persists access-log entries using HomeUnitOfWork(background=True) so that the
operation runs in the background connection pool and does not interfere
with the main API connection pool.
"""

from app.core.middlewares.access_log_sink import AccessLogSink, set_access_log_sink
from app.domains.home.services.user_access_log_service import UserAccessLogService
from app.domains.home.unit_of_work import HomeUnitOfWork


class HomeAccessLogSink(AccessLogSink):
    """Saves access-log entries via the Home domain's background unit-of-work."""

    async def save(self, data: dict) -> None:
        async with HomeUnitOfWork(background=True) as uow:
            service = UserAccessLogService(uow)
            await service.create_access_log(data)


def register_sink() -> None:
    """Register the Home access-log sink as the active middleware sink.

    Explicitly called from ``app/apps.py:routers()`` so that mounting the
    home router also wires up access-log persistence (replaces the former
    import-time side effect in ``home/config.py``).
    """
    set_access_log_sink(HomeAccessLogSink())
