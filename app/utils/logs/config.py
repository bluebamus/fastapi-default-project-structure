"""환경별 로깅 dictConfig 빌더 — 설정 단일 지점.

ENV(development/test/staging/production)에 따라 레벨·핸들러·타임존을 다르게 구성한다.
- development (uv run fastapi dev): 콘솔, DEBUG, 밀리초, 로컬 TZ(KST)
- test: 콘솔, 간결, 파일 off, 로컬 TZ
- staging/production: 콘솔 + 회전 파일 + 에러 파일, INFO, UTC

Django 와 같은 점 / 다른 점 (ADR-019 — 이 설계를 유지하기로 확정했다):
    같다   — 설정이 한 곳에 모인다. Django 의 ``settings.LOGGING`` 자리를
             ``build_dictconfig()`` 가 맡고, ``configure_logging()`` 이 1회 적용한다.
    다르다 — **앱별 로거를 등록하지 않는다.** 아래 dict 에 ``loggers`` 키가 없고
             핸들러는 **root 에만** 붙는다. ``get_logger(name)`` 이 돌려주는 것은
             NOTSET·핸들러 0·propagate=True 인 자식 로거이며, 로그 헤더의 ``app=`` 은
             로거 이름이 아니라 **소스 파일 경로**에서 산출된다
             (``filters.ContextFilter`` → ``_app_from_path``).

왜 이렇게 하나:
    새 기능을 추가할 때 로깅 설정에 **손댈 곳이 0** 이다. Django 라면 ``LOGGING["loggers"]``
    에 한 줄을 더해야 하고, 그 한 줄을 빠뜨리면 조용히 기본값으로 흘러간다. 경로 기반
    판별은 등록 누락이라는 실패 모드 자체를 없앤다. 로거 이름을 잘못 줘도(복사·붙여넣기)
    ``app=`` 라벨은 항상 맞다.

이 선택이 포기한 것 (수용된 잔여 위험 — 결함으로 재보고하지 말 것):
    · **앱별 로그 레벨을 따로 줄 수 없다.** 레벨은 root 하나뿐이고
      ``LogSettings`` 에도 전역 레벨(``LOG_LEVEL``·``LOG_CONSOLE_LEVEL``·``LOG_FILE_LEVEL``)만 있다.
    · **서드파티 로거(sqlalchemy·aiomysql 등)를 개별 제어할 수 없다.** 아래 dict 에
      해당 항목이 없어 전부 root 레벨을 따른다.
    둘 중 하나가 실제로 필요해지면 그때 ``loggers`` 키를 추가한다 —
    그 시점에 charter 비목표를 먼저 개정한다.
"""

from __future__ import annotations

from config import app_settings, log_settings, timezone_settings

# 확정 포맷 (#3): [시간 TZ] LEVEL [app=..] [module:class:func:line] message
LOG_FORMAT = (
    "[{asctime} {tzname}] {levelname:5} [app={appname}] "
    "[{module}:{classname}:{funcName}:{lineno}] {message}"
)


def _env() -> str:
    return getattr(app_settings, "ENV", "development")


def _level() -> str:
    return log_settings.get_effective_log_level(app_settings.DEBUG)


def build_dictconfig() -> dict:
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    with_ms = env == "development"

    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "filters": ["context"],
            "level": log_settings.get_effective_console_level(app_settings.DEBUG),
        },
    }
    root_handlers = ["console"]

    if env in ("production", "staging") and log_settings.LOG_FILE_ENABLED:
        log_dir = log_settings.get_log_dir()
        today = timezone_settings.now().strftime("%Y-%m-%d")
        max_bytes = log_settings.LOG_MAX_SIZE_MB * 1024 * 1024
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / log_settings.LOG_APP_FILENAME.format(date=today)),
            "maxBytes": max_bytes,
            "backupCount": log_settings.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
            "formatter": "app",
            "filters": ["context"],
            "level": log_settings.LOG_FILE_LEVEL,
        }
        handlers["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / log_settings.LOG_ERROR_FILENAME.format(date=today)),
            "maxBytes": max_bytes,
            "backupCount": log_settings.LOG_BACKUP_COUNT,
            "encoding": "utf-8",
            "formatter": "app",
            "filters": ["context"],
            "level": "ERROR",
        }
        root_handlers += ["file", "error_file"]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
        },
        "formatters": {
            "app": {
                "()": "app.utils.logs.formatters.TzFormatter",
                "fmt": LOG_FORMAT,
                "use_utc": use_utc,
                "with_ms": with_ms,
            },
        },
        "handlers": handlers,
        "root": {"handlers": root_handlers, "level": level},
    }
