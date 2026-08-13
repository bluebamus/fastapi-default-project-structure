"""app/utils/logs 로깅 서브시스템 테스트.

검증: appname 산출, 클래스명 자동추출(A), 믹스인 주입(C), 포맷 필드, end-to-end.
"""

import io
import logging
import pathlib

from app.utils.logs import (
    LOG_FORMAT,
    ContextFilter,
    LoggerMixin,
    TzFormatter,
    get_logger,
    setup_uvicorn_logging,
)
from app.utils.logs import config as logs_config
from app.utils.logs import setup as logs_setup
from app.utils.logs.filters import _app_from_path


def _rec(pathname="/x/app/features/blog/services/item_service.py", func="create"):
    return logging.LogRecord("blog", logging.INFO, pathname, 10, "hello", (), None, func)


def test_appname_from_path():
    assert _app_from_path("/x/app/features/blog/services/item_service.py") == "blog"
    assert _app_from_path("C:\\x\\app\\core\\bootstrap.py") == "core"
    assert _app_from_path("/x/app/celery/tasks.py") == "celery"
    assert _app_from_path("/x/app/utils/pagination/paginator.py") == "utils"
    assert _app_from_path("/x/migrations/env.py") == "migrations"


def test_repo_root_modules_are_not_labeled_external():
    """저장소 루트의 모듈이 'ext'(서드파티)로 분류되면 안 된다 (LOG-2).

    ``main.py``·``config.py`` 는 경로에 ``/app/`` 조각이 없어서, 예전 판별식에서
    서드파티로 빠졌다. 그러면 appname 으로 '우리 코드'를 거를 수 없다.
    이 테스트는 ``filters.py`` 가 다른 깊이로 옮겨져 ``_REPO_ROOT`` 계산이
    어긋나는 경우도 함께 잡는다.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    for name in ("main.py", "config.py"):
        assert (repo_root / name).is_file(), f"{name} 이 저장소 루트에 없다 — 테스트 전제 붕괴"
        assert _app_from_path(str(repo_root / name)) == "app"


def test_installed_packages_are_external():
    """저장소 루트 **안**의 .venv 도 서드파티로 분류된다."""
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    vendored = repo_root / ".venv" / "Lib" / "site-packages" / "sqlalchemy" / "engine.py"
    assert _app_from_path(str(vendored)) == "ext"
    assert _app_from_path("/opt/py/lib/python3.14/site-packages/httpx/_client.py") == "ext"


class _Caller:
    def run(self) -> str:
        rec = _rec()
        ContextFilter().filter(rec)
        return rec.classname


def test_classname_extracted_from_calling_class():
    """방식 A — 호출 클래스의 메서드에서 자동으로 클래스명을 채운다."""
    assert _Caller().run() == "_Caller"


def test_classname_dash_for_free_function():
    rec = _rec()
    ContextFilter().filter(rec)  # 모듈 레벨 호출(self 없음)
    assert rec.classname == "-"


def test_mixin_injects_classname():
    """방식 C — LoggerMixin 이 classname 을 extra 로 주입."""

    class _Svc(LoggerMixin):
        pass

    assert _Svc().log.extra["classname"] == "_Svc"


def test_format_contains_all_fields():
    rec = _rec()
    rec.appname = "blog"
    rec.classname = "ItemService"
    out = TzFormatter(LOG_FORMAT).format(rec)
    assert "app=blog" in out
    assert "item_service:ItemService:create:10" in out
    assert ("KST" in out) or ("UTC" in out)


def test_get_logger_end_to_end():
    logger = get_logger("test.e2e")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(ContextFilter())
    handler.setFormatter(TzFormatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("hello world")
    finally:
        logger.removeHandler(handler)
    text = buf.getvalue()
    assert "hello world" in text
    assert "app=" in text


# =============================================================================
# 환경별 dictConfig 구성
#
# staging/production 가지는 로컬·CI 에서 실행되지 않는다 — 즉 운영에서 처음 도는
# 코드다. dictConfig 를 실제로 **적용하지 않고** 빌더가 만든 dict 만 검사하므로
# 핸들러도 listener 스레드도 만들어지지 않는다(부작용 없음).
# =============================================================================
def _build_with(monkeypatch, tmp_path, **overrides):
    """ENV·로그 설정을 바꿔 build_dictconfig() 결과를 얻는다.

    빌더가 모듈 전역 settings 를 읽으므로 그 속성을 monkeypatch 로 갈아끼운다
    (monkeypatch 가 테스트 종료 시 되돌린다 — 싱글턴 오염 없음).
    """
    env = overrides.pop("env", "development")
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    for key, value in overrides.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


def test_root_uses_queue_handler_only(monkeypatch, tmp_path):
    """root 에는 queue 핸들러 하나만 붙는다 (NFR-009).

    요청 event loop 에서 동기 write/flush 가 일어나지 않으려면 root 에 출력
    핸들러가 직접 붙어서는 안 된다. stdout/stderr 쓰기는 listener 스레드의 몫이다.
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        assert cfg["root"]["handlers"] == [
            "queue"
        ], f"ENV={env} 의 root 에 queue 외 핸들러가 붙었다 — event loop 를 막는다"
        queue_handler = cfg["handlers"]["queue"]
        assert queue_handler["()"] == "app.utils.logs.queue_handler.build_queue_handler"
        # 컨텍스트는 **적재 전** 요청 스레드에서 채워야 classname 이 살아 있다.
        # sql_noise 는 SQL 본문·바인딩 파라미터 유출을 막는다(NFR-001).
        assert queue_handler["filters"] == ["sql_noise", "context"]


def test_no_file_handlers_in_any_environment(monkeypatch, tmp_path):
    """어느 환경에도 애플리케이션 파일 핸들러를 만들지 않는다 (NFR-009).

    저장·rotation 은 Docker/Kubernetes/운영 agent 가 담당한다. 파일 핸들러가
    다시 생기면 요청 스레드가 동기 rotation 을 수행하게 되므로 이 테스트가 관문이다.
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        for name, handler in cfg["handlers"].items():
            assert "File" not in handler.get(
                "class", ""
            ), f"ENV={env} 에 파일 핸들러 {name} 이 생겼다"


def test_production_separates_errors_to_stderr(monkeypatch, tmp_path):
    """production/staging 은 stdout 에 더해 ERROR 전용 stderr 출력을 갖고 UTC 를 쓴다."""
    for env in ("production", "staging"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)

        assert set(cfg["handlers"]) == {"queue", "console", "error_console"}
        assert cfg["formatters"]["app"]["use_utc"] is True

        assert cfg["handlers"]["console"]["stream"] == "ext://sys.stdout"
        assert cfg["handlers"]["error_console"]["stream"] == "ext://sys.stderr"
        assert cfg["handlers"]["error_console"]["level"] == "ERROR"

        # listener 가 두 출력 모두를 위임받아야 한다.
        assert logs_config.listener_handler_names(env) == ["console", "error_console"]


def test_development_is_stdout_only_and_local_time(monkeypatch, tmp_path):
    """개발에서는 stdout 하나만 쓰고 로컬 TZ + 밀리초를 쓴다."""
    cfg = _build_with(monkeypatch, tmp_path, env="development")

    assert set(cfg["handlers"]) == {"queue", "console"}
    assert cfg["formatters"]["app"]["use_utc"] is False
    assert cfg["formatters"]["app"]["with_ms"] is True
    assert logs_config.listener_handler_names("development") == ["console"]


def test_dictconfig_has_no_per_app_loggers(monkeypatch, tmp_path):
    """ADR-019 — 앱별 로거를 **등록하지 않는다**(핸들러는 root 에만).

    이 프로젝트는 Django 의 ``settings.LOGGING["loggers"]`` 식 등록을 쓰지 않고
    소스 경로에서 앱을 판별한다. ``loggers`` 키가 생기면 그 설계가 바뀐 것이므로,
    코드보다 charter §2-4 비목표를 먼저 고쳐야 한다. 이 테스트가 그 관문이다.
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        assert "loggers" not in cfg, (
            f"ENV={env} 의 dictConfig 에 loggers 키가 생겼습니다. "
            "앱별 로거 등록은 ADR-019 의 비목표입니다 — charter §2-4 를 먼저 개정하세요."
        )
        assert cfg["root"]["handlers"], "root 에 핸들러가 없으면 아무 로그도 나가지 않는다"


def test_uvicorn_shares_the_app_queue(monkeypatch):
    """uvicorn 3종 로거가 앱과 **같은** queue 로 나가고 root 로 전파하지 않는다.

    propagate=True 면 앱 root 핸들러가 같은 줄을 한 번 더 찍어 중복 출력이 된다.
    핸들러는 앱과 공유하므로 ``app=uvicorn`` 라벨은 **로거** 필터로 찍어야 한다 —
    공유 핸들러에 붙이면 앱 로그까지 uvicorn 으로 라벨링된다.
    """
    cfg = setup_uvicorn_logging()

    assert set(cfg["loggers"]) == {"uvicorn", "uvicorn.error", "uvicorn.access"}
    for name, spec in cfg["loggers"].items():
        assert spec["propagate"] is False, f"{name} 이 root 로 전파되면 로그가 중복된다"
        assert spec["handlers"] == ["queue"], f"{name} 이 공유 queue 를 쓰지 않는다"
        assert spec["filters"] == ["uvicorn_app"], f"{name} 의 app 라벨 필터가 없다"

    assert cfg["handlers"]["queue"]["()"] == "app.utils.logs.setup.get_shared_queue_handler"
    assert cfg["filters"]["uvicorn_app"]["appname"] == "uvicorn"
    # 공유 핸들러를 오염시키면 안 되므로 핸들러에는 필터를 두지 않는다.
    assert "filters" not in cfg["handlers"]["queue"]


def test_shared_queue_handler_is_the_app_queue_handler():
    """uvicorn 이 받는 핸들러가 앱이 쓰는 바로 그 인스턴스여야 한다.

    두 개가 되면 queue 도 listener 도 둘이 되어 출력 순서와 종료 시점이 갈린다.
    (root 로거 자체는 pytest 의 로그 캡처가 가로채므로 여기서 단언하지 않는다 —
    root 배선은 ``test_root_uses_queue_handler_only`` 가 dictConfig 로 검증한다.)
    """
    from app.utils.logs.queue_handler import BoundedQueueHandler
    from app.utils.logs.setup import get_queue_handler, get_shared_queue_handler

    handler = get_queue_handler()
    assert isinstance(handler, BoundedQueueHandler)
    assert get_shared_queue_handler() is handler


def test_configure_logging_applies_once(monkeypatch):
    """configure_logging() 은 여러 번 불러도 dictConfig 를 1회만 적용한다.

    get_logger() 가 매번 호출하므로, 여기서 idempotent 가 깨지면 로거를 만들 때마다
    전체 로깅이 재구성되어 런타임에 붙인 핸들러가 사라진다.
    """
    calls = []
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: calls.append(cfg))
    monkeypatch.setattr(logs_setup, "_configured", False, raising=False)

    logs_setup.configure_logging()
    logs_setup.configure_logging()
    get_logger("test.idempotent")
    assert len(calls) == 1

    # force=True 는 의도적 재적용이므로 통과해야 한다.
    logs_setup.configure_logging(force=True)
    assert len(calls) == 2
