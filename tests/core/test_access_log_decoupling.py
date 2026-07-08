"""
Tests for Task 3.4: access-log middleware decoupling from home domain.

These tests verify that:
1. The middleware source contains no direct home-domain imports.
2. The sink registration roundtrip works correctly.
"""

import importlib
import importlib.util


def test_middleware_does_not_import_home():
    """Middleware source must not reference app.home or app.domains.home."""
    src = importlib.util.find_spec("app.core.middlewares.user_info_middleware").origin
    text = open(src, encoding="utf-8").read()
    assert "app.home" not in text and "app.domains.home" not in text


async def test_sink_registration_roundtrip():
    """set_access_log_sink / get_access_log_sink roundtrip works and delegates calls."""
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )

    original = get_access_log_sink()

    calls = []

    class StubSink:
        async def save(self, data: dict) -> None:
            calls.append(data)

    stub = StubSink()
    try:
        set_access_log_sink(stub)
        assert get_access_log_sink() is stub
        await get_access_log_sink().save({"x": 1})
        assert calls == [{"x": 1}]
    finally:
        set_access_log_sink(original)
