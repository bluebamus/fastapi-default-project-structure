"""
Access-log sink Protocol and registry.

Decouples the core middleware from any domain that implements log persistence.
The domain registers its sink via set_access_log_sink(); the middleware calls
get_access_log_sink() and delegates to it (no-op if nothing is registered).
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class AccessLogSink(Protocol):
    """Protocol that any access-log storage backend must satisfy."""

    async def save(self, data: dict) -> None:
        """Persist one access-log entry."""
        ...


_sink: AccessLogSink | None = None


def set_access_log_sink(sink: AccessLogSink) -> None:
    """Register the active access-log sink (called by the home domain config)."""
    global _sink
    _sink = sink


def get_access_log_sink() -> AccessLogSink | None:
    """Return the registered sink, or None if none has been registered yet."""
    return _sink
