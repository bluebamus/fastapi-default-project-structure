"""Home domain registration is now done explicitly in app/apps.py.

The former home/config.py AppConfig was removed; the home-domain side effect
(access-log sink registration) lives in access_log_sink.register_sink().
"""


def test_register_sink_installs_home_sink():
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.domains.home.access_log_sink import HomeAccessLogSink, register_sink

    original = get_access_log_sink()
    try:
        set_access_log_sink(None)
        register_sink()
        assert isinstance(get_access_log_sink(), HomeAccessLogSink)
    finally:
        set_access_log_sink(original)


def test_apps_routers_includes_home():
    from app.apps import routers
    from app.domains.home.api.routers.router import home_router

    assert any(spec.router is home_router for spec in routers())
