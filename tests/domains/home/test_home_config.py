"""Home 도메인 등록은 AppRegistry 컨벤션 자동발견으로 이뤄진다(gen-2).

home 패키지 __init__.py 가 import 시점에 access-log sink 를 등록하고(register_sink),
라우터는 컨벤션(home_router)으로 발견된다(별도 config.py 없음).
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


def test_registry_discovers_home_router_by_convention():
    from app.core.registry import AppRegistry
    from app.domains.home.api.routers.router import home_router

    apps = AppRegistry().discover()
    home = next((m for m in apps if m.name == "home"), None)
    assert home is not None
    assert home.package == "app.domains.home"
    assert home.load_router() is home_router
