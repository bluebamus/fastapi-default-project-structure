"""환경별 로깅 dictConfig 빌더 — 설정 단일 지점.

ENV(development/test/staging/production)에 따라 레벨·출력·타임존을 다르게 구성한다.
- development (uv run fastapi dev): stdout, DEBUG, 밀리초, 로컬 TZ(KST)
- test: stdout, 간결, 로컬 TZ
- staging/production: stdout + stderr(ERROR 전용), INFO, UTC

포맷·시각 형식·콘솔 출력 여부는 ``LogSettings`` 의 ``LOG_CONSOLE_FORMAT``·``LOG_DATE_FORMAT``·
``LOG_CONSOLE_ENABLED`` 가 정한다. 콘솔 출력 여부는 ``console_enabled()`` **한 곳**에서 판단하고,
앱 dictConfig·uvicorn CLI 핸들러·Celery 핸들러(``setup.apply_console_settings``)가 모두 그것을 본다.

**출력 경로는 항상 queue 를 거친다** (NFR-009). root 로거에는
``BoundedQueueHandler`` 하나만 붙고, 실제 stdout/stderr 쓰기는 ``QueueListener``
스레드가 수행한다. 요청 event loop 에서 동기 write/flush 가 일어나지 않게 하려는
것이고, 그래서 애플리케이션 파일 handler 와 rotation 설정은 제거했다 — 저장과
rotation 은 Docker/Kubernetes/운영 agent 가 담당한다.

``context`` 필터는 **queue 핸들러에** 붙는다. ``ContextFilter`` 가 호출 스택에서
classname 을 뽑기 때문에, listener 스레드에서 돌리면 스택이 이미 사라져 값이 항상
'-' 가 된다. 필터는 record 를 적재하기 전 요청 스레드에서 실행돼야 한다.

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
      ``LogSettings`` 에도 전역 레벨(``LOG_LEVEL``·``LOG_CONSOLE_LEVEL``)만 있다.
    · **서드파티 로거(sqlalchemy·aiomysql 등)를 개별 제어할 수 없다.** 아래 dict 에
      해당 항목이 없어 전부 root 레벨을 따른다.
    둘 중 하나가 실제로 필요해지면 그때 ``loggers`` 키를 추가한다 —
    그 시점에 charter 비목표를 먼저 개정한다.
"""

from __future__ import annotations

import logging

from config import LogSettings, app_settings, log_settings

# 확정 포맷 (#3): [시간 TZ] LEVEL [app=..] [module:class:func:line] message
# 정본은 LOG_CONSOLE_FORMAT 의 기본값이다 — 실제 출력은 설정값을 쓴다(console_formatter_kwargs).
LOG_FORMAT: str = LogSettings.model_fields["LOG_CONSOLE_FORMAT"].default

# listener 가 소유하는 실제 출력 핸들러 이름. queue 핸들러가 아니라 이 handler 들이
# stdout/stderr 에 쓴다.
CONSOLE_HANDLER = "console"
ERROR_CONSOLE_HANDLER = "error_console"
QUEUE_HANDLER = "queue"


def _env() -> str:
    return getattr(app_settings, "ENV", "development")


def _level() -> str:
    return log_settings.get_effective_log_level(app_settings.DEBUG)


def lowest_level() -> str:
    """``LOG_LEVEL`` 과 ``LOG_APP_LEVELS`` 중 가장 낮은 레벨 — 로거·queue 레벨.

    로거 레벨이 높으면 ``AppLevelFilter`` 가 보기 전에 레코드가 버려진다. 로거는 최솟값까지 열고
    헤더별 판단은 필터가 한다(logging-overhaul L4).
    """
    names = [_level(), *(logging.getLevelName(n) for n in log_settings.app_levels().values())]
    return min(names, key=lambda name: logging.getLevelNamesMapping()[name.upper()])


def console_enabled() -> bool:
    """콘솔(stdout/stderr) 핸들러를 붙일지 — 콘솔 핸들러를 만드는 모든 경로가 이것만 본다."""
    return log_settings.LOG_CONSOLE_ENABLED


def console_formatter_kwargs(env: str | None = None) -> dict:
    """콘솔 포매터(``TzFormatter``) 인자 — 앱 dictConfig 와 uvicorn CLI·Celery 핸들러가 함께 쓴다."""
    env = env if env is not None else _env()
    return {
        "fmt": log_settings.LOG_CONSOLE_FORMAT,
        "datefmt": log_settings.LOG_DATE_FORMAT,
        "use_utc": env in ("production", "staging"),
        "with_ms": env == "development",
    }


def listener_handler_names(env: str | None = None) -> list[str]:
    """QueueListener 가 위임할 출력 핸들러 이름 목록(콘솔이 꺼졌으면 빈 목록)."""
    env = env if env is not None else _env()
    if not console_enabled():
        return []
    names = [CONSOLE_HANDLER]
    if env in ("production", "staging"):
        names.append(ERROR_CONSOLE_HANDLER)
    return names


def build_dictconfig() -> dict:
    env = _env()
    level = lowest_level()

    # listener 스레드가 소유하는 출력 핸들러. root 에는 붙이지 않는다.
    handlers: dict = {
        CONSOLE_HANDLER: {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "level": log_settings.get_effective_console_level(app_settings.DEBUG),
        },
        QUEUE_HANDLER: {
            # ``class`` 로 선언해야 dictConfig 의 QueueHandler 특수 처리 경로를 탄다.
            # ``()`` 팩토리를 쓰면 그 경로를 통째로 우회하게 되어 queue·listener·대상
            # 핸들러 연결을 전부 손으로 해야 한다 (ADR-021).
            "class": "app.utils.logs.queue_handler.BoundedQueueHandler",
            "queue": {"()": "app.utils.logs.queue_handler.build_log_queue"},
            "listener": "app.utils.logs.queue_handler.TimeoutSentinelListener",
            # listener 가 위임받아 실제로 stdout/stderr 에 쓰는 핸들러들.
            "handlers": listener_handler_names(env),
            "respect_handler_level": True,
            # 적재 전에 요청 스레드에서 컨텍스트를 채운다(listener 스레드에서는 늦다).
            # sql_noise 는 SQL 본문·바인딩 파라미터가 로그로 새는 것을 막는다.
            # redact 는 메시지·traceback·stack 의 비밀값을 적재 **전에** 가린다 — queue 가 가득 찬
            # ERROR 의 stderr fallback 도 이 뒤라 가려진 값을 쓴다(log-redaction ADR-001).
            # app_levels 는 헤더가 채워진 뒤 LOG_APP_LEVELS 로 거른다(logging-overhaul L4).
            "filters": ["sql_noise", "redact", "context", "app_levels"],
            "level": level,
        },
    }

    if env in ("production", "staging"):
        # 예전의 error_file 자리 — 운영에서 오류만 따로 뽑을 수 있어야 한다.
        handlers[ERROR_CONSOLE_HANDLER] = {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "app",
            "level": "ERROR",
        }

    # 콘솔이 꺼졌으면 listener 가 쓰지 않는 출력 핸들러는 만들지도 않는다.
    handlers = {
        name: spec
        for name, spec in handlers.items()
        if name == QUEUE_HANDLER or name in handlers[QUEUE_HANDLER]["handlers"]
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
            "app_levels": {
                "()": "app.utils.logs.filters.AppLevelFilter",
                "levels": log_settings.app_levels(),
                "default": _level(),
            },
            "redact": {"()": "app.utils.logs.filters.RedactingFilter"},
            "sql_noise": {
                "()": "app.utils.logs.filters.SqlNoiseFilter",
                "allow_sql_echo": log_settings.LOG_SQL_ECHO_ENABLED,
            },
        },
        "formatters": {
            "app": {
                "()": "app.utils.logs.formatters.TzFormatter",
                **console_formatter_kwargs(env),
            },
        },
        "handlers": handlers,
        "root": {"handlers": [QUEUE_HANDLER], "level": level},
    }
