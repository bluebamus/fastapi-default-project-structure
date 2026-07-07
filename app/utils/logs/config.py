"""환경별 로깅 dictConfig 빌더 (Django 스타일).

ENV(development/test/staging/production)에 따라 레벨·핸들러·타임존을 다르게 구성한다.
- development (uv run fastapi dev): 콘솔, DEBUG, 밀리초, 로컬 TZ(KST)
- test: 콘솔, 간결, 파일 off, 로컬 TZ
- staging/production: 콘솔 + 회전 파일 + 에러 파일, INFO, UTC
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
