"""Home 도메인 등록은 표준 FastAPI 배선으로 이뤄진다.

home 패키지 __init__.py 가 import 시점에 access-log sink 를 등록하고(register_sink),
하위 뷰 라우터를 취합한 ``router`` (= home_router) 를 공개하며, main.py 가 이를
``include_router`` 로 /api 에 취합한다.
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


def test_home_package_exposes_router_and_main_includes_it():
    from app.domains import home
    from app.domains.home.api.routers.router import home_router

    # 패키지가 취합 라우터를 공개한다.
    assert home.router is home_router

    # main.py 가 /api 프리픽스로 취합한다.
    from main import app

    paths = {r.path for r in app.routes}
    assert any(p.startswith("/api/v1/home") for p in paths)
