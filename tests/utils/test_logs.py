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
# 코드다. dictConfig 를 실제로 적용하지 않고 **빌더가 만든 dict 만** 검사하므로
# 파일 핸들러가 열리지 않는다(파일 I/O 없음).
# =============================================================================
def _build_with(monkeypatch, tmp_path, **overrides):
    """ENV·로그 설정을 바꿔 build_dictconfig() 결과를 얻는다.

    빌더가 모듈 전역 settings 를 읽으므로 그 속성을 monkeypatch 로 갈아끼운다
    (monkeypatch 가 테스트 종료 시 되돌린다 — 싱글턴 오염 없음).
    """
    env = overrides.pop("env", "development")
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    # 로그 디렉터리는 tmp 로 — get_log_dir() 이 mkdir 을 하므로 저장소를 더럽히지 않게.
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in overrides.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


def test_production_adds_rotating_file_handlers(monkeypatch, tmp_path):
    """production 에서는 콘솔에 더해 회전 파일·에러 파일 핸들러가 붙고 UTC 를 쓴다."""
    cfg = _build_with(monkeypatch, tmp_path, env="production", LOG_FILE_ENABLED=True)

    assert set(cfg["handlers"]) == {"console", "file", "error_file"}
    assert cfg["root"]["handlers"] == ["console", "file", "error_file"]
    assert cfg["formatters"]["app"]["use_utc"] is True

    for name in ("file", "error_file"):
        handler = cfg["handlers"][name]
        assert handler["class"] == "logging.handlers.RotatingFileHandler"
        assert handler["backupCount"] == logs_config.log_settings.LOG_BACKUP_COUNT
        assert handler["maxBytes"] == logs_config.log_settings.LOG_MAX_SIZE_MB * 1024 * 1024
        # 핸들러마다 컨텍스트 필터가 붙어야 appname/classname 이 채워진다.
        assert handler["filters"] == ["context"]
        assert str(tmp_path) in handler["filename"]

    # 에러 전용 파일은 ERROR 만 받아야 의미가 있다.
    assert cfg["handlers"]["error_file"]["level"] == "ERROR"


def test_development_is_console_only_and_local_time(monkeypatch, tmp_path):
    """개발에서는 파일 핸들러를 붙이지 않고 로컬 TZ + 밀리초를 쓴다."""
    cfg = _build_with(monkeypatch, tmp_path, env="development")

    assert set(cfg["handlers"]) == {"console"}
    assert cfg["root"]["handlers"] == ["console"]
    assert cfg["formatters"]["app"]["use_utc"] is False
    assert cfg["formatters"]["app"]["with_ms"] is True


def test_file_logging_can_be_disabled_in_production(monkeypatch, tmp_path):
    """production 이라도 LOG_FILE_ENABLED=False 면 파일 핸들러를 만들지 않는다.

    읽기 전용 파일시스템(컨테이너)에서 기동이 깨지지 않으려면 이 스위치가 살아 있어야 한다.
    """
    cfg = _build_with(monkeypatch, tmp_path, env="production", LOG_FILE_ENABLED=False)

    assert set(cfg["handlers"]) == {"console"}
    assert cfg["root"]["handlers"] == ["console"]
    assert cfg["formatters"]["app"]["use_utc"] is True  # UTC 는 파일 여부와 무관


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


def test_uvicorn_config_isolates_three_loggers():
    """uvicorn 3종 로거가 각자 핸들러를 갖고 root 로 전파하지 않는다.

    propagate=True 면 앱 root 핸들러가 같은 줄을 한 번 더 찍어 중복 출력이 된다.
    """
    cfg = setup_uvicorn_logging()

    assert set(cfg["loggers"]) == {"uvicorn", "uvicorn.error", "uvicorn.access"}
    for name, spec in cfg["loggers"].items():
        assert spec["propagate"] is False, f"{name} 이 root 로 전파되면 로그가 중복된다"
        assert spec["handlers"], f"{name} 에 핸들러가 없다"

    # access 로그만 전용 포맷(요청 라인)을 쓴다.
    assert cfg["loggers"]["uvicorn.access"]["handlers"] == ["access"]
    assert "request_line" in cfg["formatters"]["access"]["fmt"]
    for handler in cfg["handlers"].values():
        assert handler["filters"] == ["context"]


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
