"""환경별 로깅 dictConfig 빌더 — 설정 단일 지점.

ENV(development/test/staging/production)에 따라 레벨·출력·타임존을 다르게 구성한다.
- development (uv run fastapi dev): stdout, DEBUG, 밀리초, 로컬 TZ(KST)
- test: stdout, 간결, 로컬 TZ
- staging/production: stdout + stderr(ERROR 전용), INFO, UTC

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

from config import app_settings, log_settings

# 확정 포맷 (#3): [시간 TZ] LEVEL [app=..] [module:class:func:line] message
LOG_FORMAT = (
    "[{asctime} {tzname}] {levelname:5} [app={appname}] "
    "[{module}:{classname}:{funcName}:{lineno}] {message}"
)

# listener 가 소유하는 실제 출력 핸들러 이름. queue 핸들러가 아니라 이 handler 들이
# stdout/stderr 에 쓴다.
CONSOLE_HANDLER = "console"
ERROR_CONSOLE_HANDLER = "error_console"
QUEUE_HANDLER = "queue"


def _env() -> str:
    return getattr(app_settings, "ENV", "development")


def _level() -> str:
    return log_settings.get_effective_log_level(app_settings.DEBUG)


def listener_handler_names(env: str | None = None) -> list[str]:
    """QueueListener 가 위임할 출력 핸들러 이름 목록."""
    env = env if env is not None else _env()
    names = [CONSOLE_HANDLER]
    if env in ("production", "staging"):
        names.append(ERROR_CONSOLE_HANDLER)
    return names


def build_dictconfig() -> dict:
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    with_ms = env == "development"

    # listener 스레드가 소유하는 출력 핸들러. root 에는 붙이지 않는다.
    handlers: dict = {
        CONSOLE_HANDLER: {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "level": log_settings.get_effective_console_level(app_settings.DEBUG),
        },
        QUEUE_HANDLER: {
            "()": "app.utils.logs.queue_handler.build_queue_handler",
            # 적재 전에 요청 스레드에서 컨텍스트를 채운다(listener 스레드에서는 늦다).
            # sql_noise 는 SQL 본문·바인딩 파라미터가 로그로 새는 것을 막는다.
            "filters": ["sql_noise", "context"],
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

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
            "sql_noise": {
                "()": "app.utils.logs.filters.SqlNoiseFilter",
                "allow_sql_echo": log_settings.LOG_SQL_ECHO_ENABLED,
            },
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
        "root": {"handlers": [QUEUE_HANDLER], "level": level},
    }
