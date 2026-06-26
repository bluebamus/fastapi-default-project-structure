"""
Home-domain implementation of the AccessLogSink Protocol.

Persists access-log entries using the background session context
(background_session) so the write runs on the background connection pool and
does not interfere with the main API pool. (UnitOfWork was removed; the
transaction boundary is the background_session context manager.)
"""

from app.core.db.session import background_session
from app.core.middlewares.access_log_sink import AccessLogSink, set_access_log_sink
from app.domains.home.services.user_access_log_service import UserAccessLogService


class HomeAccessLogSink(AccessLogSink):
    """Saves access-log entries via the background session context."""

    async def save(self, data: dict) -> None:
        async with background_session() as session:
            service = UserAccessLogService(session)
            await service.create_access_log(data)
            await session.commit()


def register_sink() -> None:
    """Register the Home access-log sink as the active middleware sink.

    Called from ``home/__init__.py`` (import-time) so that convention discovery
    of the home app also wires up access-log persistence.
    """
    set_access_log_sink(HomeAccessLogSink())
