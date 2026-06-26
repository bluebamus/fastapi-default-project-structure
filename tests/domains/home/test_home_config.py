"""Home 도메인 등록은 AppRegistry 자동발견(home/config.py)으로 이뤄진다.

home/config.py 는 import 시점에 access-log sink 를 등록하고(register_sink),
HomeConfig(AppConfig) 를 통해 home 라우터를 노출한다.
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


def test_registry_discovers_home_router():
    from app.core.registry import AppRegistry
    from app.domains.home.api.routers.router import home_router

    apps = AppRegistry().discover()
    home = next((c for c in apps if c.name == "home"), None)
    assert home is not None
    assert home.router() is home_router
