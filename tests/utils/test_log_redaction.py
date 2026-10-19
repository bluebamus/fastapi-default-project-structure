"""로그·오류 응답의 비밀값 마스킹 — log-redaction ADR-001.

``logger.exception(...)`` 은 예외 메시지와 체인(``raise ... from``)·``stack_info`` 를 traceback
본문으로 출력한다. 그 안의 DSN 비밀번호·``password=``·``Authorization`` 값이 그대로 나가던 것을
막는다. 출력 경로마다 본다:

- 앱 기본 경로: root 의 queue 핸들러 → listener 의 stdout(전 환경)·stderr(staging/production).
  **실제 dictConfig** 를 자식 프로세스에 적용해 본다(이 프로세스의 로깅을 바꾸지 않는다).
- queue 포화 시 ERROR 의 stderr fallback.
- ``uvicorn main:app`` CLI — uvicorn 로거가 자기 핸들러로 내보내는 경로.
- Celery worker — root 핸들러를 갈아끼우는 경로(``after_setup_logger``).
- DEBUG 에서 500 응답의 ``detail``(클라이언트로 나간다).
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import queue
import subprocess  # noqa: S404 - 실제 로깅 구성을 자식 프로세스에 적용해 본다
import sys

import pytest
from starlette.requests import Request

from app.utils.logs.filters import REDACTED, RedactingFilter, redact
from app.utils.logs.queue_handler import BoundedQueueHandler

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SECRETS = ("secret42", "tok-9f3e7a")
DSN = "mysql+asyncmy://u:secret42@h/db"


def _raise_chained() -> None:
    """DSN·password= 를 담은 원인 예외를 Authorization 을 담은 예외로 감싼다."""
    try:
        raise ValueError(f"connect failed {DSN} password=secret42")
    except ValueError as exc:
        raise RuntimeError("upstream said Authorization: Bearer tok-9f3e7a") from exc


def _assert_redacted_traceback(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text, f"비밀값 {secret!r} 이 출력에 남았다:\n{text}"
    assert REDACTED in text, f"마스킹 표식이 없다:\n{text}"
    # 진단 정보는 남는다: 예외 타입·체인·파일·줄·stack.
    assert "ValueError: connect failed mysql+asyncmy://***:***@h/db password=***" in text
    assert "RuntimeError: upstream said Authorization: Bearer ***" in text
    assert "The above exception was the direct cause of the following exception" in text
    assert "test_log_redaction.py" in text
    assert ", line " in text


# =============================================================================
# 마스킹 규칙(정본) 단위
# =============================================================================
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # DSN 은 사용자명도 가린다(logging-overhaul L7) — 계정명도 공격 표면이다.
        (DSN, "mysql+asyncmy://***:***@h/db"),
        ("mysql://admin@h/db", "mysql://***@h/db"),
        ("redis://:p%40ss@cache:6379/0", "redis://:***@cache:6379/0"),
        ("password=secret42 next", "password=*** next"),
        ("MYSQL_PASSWORD: 'secret42'", "MYSQL_PASSWORD: '***'"),
        ('{"refresh_token": "abc.def"}', '{"refresh_token": "***"}'),
        ("Authorization: Bearer abc.def-ghi", "Authorization: Bearer ***"),
        ("authorization=Basic dXNlcjpwdw==", "authorization=Basic ***"),
        ("sent bearer abc.def", "sent bearer ***"),
    ],
)
def test_redact_masks_known_secret_shapes(raw, expected):
    assert redact(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "http://127.0.0.1:8000/health",
        'File "C:\\repo\\app\\main.py", line 12, in handler',
        "error_code=AUTH_INVALID_TOKEN status=401",
        "GET /api/v1/blog/posts?page=2 200",
    ],
)
def test_redact_leaves_ordinary_text_alone(text):
    assert redact(text) == text


# =============================================================================
# 필터 — record 단위
# =============================================================================
def _record(msg: str, args: tuple | None = None, *, exc: bool = False) -> logging.LogRecord:
    exc_info = None
    if exc:
        try:
            _raise_chained()
        except RuntimeError:
            exc_info = sys.exc_info()
    return logging.LogRecord("t", logging.ERROR, __file__, 1, msg, args, exc_info)


def test_filter_masks_traceback_and_keeps_exc_info():
    record = _record("boom", exc=True)
    RedactingFilter().filter(record)

    assert record.exc_info is not None, "exc_info 를 지우면 포매터·외부 수집기가 진단 정보를 잃는다"
    text = logging.Formatter().format(record)
    _assert_redacted_traceback(text)


def test_filter_masks_stack_info():
    record = _record("boom")
    record.stack_info = (
        f'Stack (most recent call last):\n  File "x.py", line 3\n    connect("{DSN}")'
    )
    RedactingFilter().filter(record)

    assert "secret42" not in record.stack_info
    assert "line 3" in record.stack_info


def test_filter_masks_message_arguments():
    record = _record("db url %s", (DSN,))
    RedactingFilter().filter(record)

    assert record.getMessage() == "db url mysql+asyncmy://***:***@h/db"


def test_filter_keeps_args_when_nothing_to_mask():
    """가릴 것이 없으면 ``msg``/``args`` 를 그대로 둔다 — uvicorn access 포매터가 ``args`` 를 읽는다."""
    args = ("127.0.0.1:5000", "GET", "/health", "1.1", 200)
    record = _record('%s - "%s %s HTTP/%s" %d', args)
    RedactingFilter().filter(record)

    assert record.args == args


ACCESS_FMT = '%s - "%s %s HTTP/%s" %d'
ACCESS_SECRET_ARGS = ("127.0.0.1:5000", "GET", "/x?token=tok-9f3e7a&password=secret42", "1.1", 200)


def test_filter_masks_inside_one_argument_and_keeps_args_shape():
    """비밀값이 인자 하나 안에 있으면 그 인자만 가리고 ``args`` 모양을 지킨다(config-cleanup F-008).

    uvicorn ``AccessFormatter`` 는 ``args`` 5개를 직접 푼다 — 비우면 접속 줄이 logging 오류와 함께 사라진다.
    """
    record = _record(ACCESS_FMT, ACCESS_SECRET_ARGS)
    RedactingFilter().filter(record)

    assert record.msg == ACCESS_FMT
    assert record.args == ("127.0.0.1:5000", "GET", "/x?token=***&password=***", "1.1", 200)


def test_filter_falls_back_when_secret_spans_template_and_argument():
    """키는 틀에, 값은 인자에 있으면 인자만 봐서는 못 가린다 — 합친 메시지로 가리는 기존 방식."""
    record = _record("password=%s", ("secret42",))
    RedactingFilter().filter(record)

    assert record.getMessage() == "password=***"


# =============================================================================
# 설정 비밀값 원문 (logging-overhaul L7)
# =============================================================================
def test_configured_secret_values_are_masked_anywhere(monkeypatch):
    """설정된 비밀번호·사용자명·키의 **원문**은 형태와 무관하게 가린다."""
    from app.utils.logs import filters

    monkeypatch.setattr(filters, "SECRET_VALUES", ("Sup3r-pass", "dbadmin"))
    assert redact("login dbadmin with Sup3r-pass failed") == "login *** with *** failed"


def test_short_account_name_is_masked_only_in_account_shapes(monkeypatch):
    """4글자 미만 값(주로 계정명)은 원문 일치로 가리지 않는다 — 일반 단어 오탐 방지.

    ``user=``·``username=`` 와 DSN 에서만 가린다.
    """
    from app.utils.logs import filters

    monkeypatch.setattr(filters, "SECRET_VALUES", ("app",))
    assert redact("application app started") == "application app started"
    assert redact("user=app username: 'app'") == "user=*** username: '***'"
    assert redact("mysql://app@h/db") == "mysql://***@h/db"


def test_secret_value_inside_exception_chain_is_masked(monkeypatch):
    from app.utils.logs import filters

    monkeypatch.setattr(filters, "SECRET_VALUES", ("Sup3r-pass",))
    try:
        try:
            raise OSError("auth failed: Sup3r-pass")
        except OSError as exc:
            raise RuntimeError("wrapped") from exc
    except RuntimeError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "x", None, sys.exc_info())
    RedactingFilter().filter(record)

    text = logging.Formatter().format(record)
    assert "Sup3r-pass" not in text
    assert "OSError: auth failed: ***" in text


def test_secret_values_come_from_settings(monkeypatch):
    """대상 값은 config 의 목록(``LOG_SECRET_SETTINGS``)이 정한다. 빈 값은 뺀다."""
    import config

    monkeypatch.setattr(config.db_settings, "MYSQL_PASSWORD", "db-pass-1")
    monkeypatch.setattr(config.db_settings, "MYSQL_REPLICA_PASSWORD", None)
    monkeypatch.setattr(config.redis_settings, "REDIS_PASSWORD", "")
    values = config.log_secret_values()
    assert "db-pass-1" in values
    assert "" not in values and None not in values
    assert config.jwt_settings.ACCESS_TOKEN_SECRET_KEY in values


def test_every_secret_like_setting_is_in_the_log_secret_list():
    """새 비밀 설정이 생기면 ``LOG_SECRET_SETTINGS`` 에 넣어야 한다 — 이름 규칙으로 감시한다."""
    import re

    import config
    from pydantic_settings import BaseSettings

    rule = re.compile(r"(_USER|_PASSWORD|SECRET|_KEY)$|SECRET")
    secret_like = {
        name
        for cls in vars(config).values()
        if isinstance(cls, type) and issubclass(cls, BaseSettings) and cls is not BaseSettings
        for name in cls.model_fields
        if rule.search(name)
    }
    assert secret_like, "규칙이 아무것도 못 찾으면 계약이 무의미하다"
    assert secret_like <= set(config.LOG_SECRET_SETTINGS), secret_like - set(
        config.LOG_SECRET_SETTINGS
    )


# =============================================================================
# 출력 경로별
# =============================================================================
PIPELINE_PROBE = """
import logging
from config import app_settings
app_settings.ENV = "production"   # stdout + ERROR 전용 stderr 를 둘 다 만든다
from app.utils.logs import setup
setup.configure_logging(force=True)
from tests.utils.test_log_redaction import DSN as _DSN, _raise_chained
try:
    _raise_chained()
except RuntimeError:
    logging.getLogger("probe").exception("probe failed for %s", _DSN, stack_info=True)
setup.stop_log_listener()
"""


def test_project_logging_pipeline_masks_stdout_and_stderr():
    """실제 dictConfig(queue → listener → console/error_console)의 두 출력 모두 가려진다."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", PIPELINE_PROBE],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        assert "probe failed for" in stream, f"{name} 에 로그가 없다:\n{stream}"
        _assert_redacted_traceback(stream)
        assert "Stack (most recent call last)" in stream, f"{name} 에 stack_info 가 없다"
        assert "u:secret42@h" not in stream


def test_queue_overflow_fallback_is_masked():
    """queue 가 가득 차 ERROR 가 stderr 로 우회해도 가려진 메시지를 쓴다(필터가 적재 전에 돈다)."""
    full = queue.Queue(maxsize=1)
    full.put_nowait(object())
    sink = io.StringIO()
    handler = BoundedQueueHandler(full, stderr=sink)
    handler.addFilter(RedactingFilter())
    logger = logging.getLogger("test.redaction.fallback")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.error("cannot reach %s", DSN)
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    assert handler.fallbacks == 1
    assert "secret42" not in sink.getvalue()
    assert "://***:***@h" in sink.getvalue()


def test_uvicorn_cli_loggers_are_masked():
    """``uvicorn main:app`` 로 띄우면 uvicorn 로거는 자기 핸들러로 쓴다 — 로거 필터가 덮는다."""
    from uvicorn.logging import DefaultFormatter

    from app.utils.logs import get_logger
    from app.utils.logs.setup import UVICORN_TRACEBACK_LOGGERS

    get_logger("test.redaction")  # 로깅 구성(필터 부착)을 보장한다
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)  # uvicorn 기본 핸들러와 같은 종류
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s", use_colors=False))
    for name in UVICORN_TRACEBACK_LOGGERS:
        logger = logging.getLogger(name)
        assert any(isinstance(f, RedactingFilter) for f in logger.filters), name

    logger = logging.getLogger("uvicorn.error")
    logger.addHandler(handler)
    try:
        try:
            _raise_chained()
        except RuntimeError as exc:
            logger.error("Exception in ASGI application\n", exc_info=exc)
    finally:
        logger.removeHandler(handler)

    _assert_redacted_traceback(buf.getvalue())


def test_celery_worker_handlers_are_masked():
    """Celery worker 가 root 에 단 핸들러에도 필터가 붙는다(``after_setup_logger``)."""
    from celery.app.log import ColorFormatter
    from celery.signals import after_setup_logger, after_setup_task_logger

    import app.celery.lifecycle  # noqa: F401 - 시그널 수신자 등록

    for signal in (after_setup_logger, after_setup_task_logger):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(ColorFormatter("%(levelname)s %(message)s", use_color=False))
        logger = logging.getLogger(f"test.redaction.celery.{signal.name}")
        logger.addHandler(handler)
        logger.propagate = False
        try:
            signal.send(
                sender=None,
                logger=logger,
                loglevel=logging.INFO,
                logfile=None,
                format="",
                colorize=False,
            )
            try:
                _raise_chained()
            except RuntimeError:
                logger.exception("Task failed")
        finally:
            logger.removeHandler(handler)
            logger.propagate = True

        _assert_redacted_traceback(buf.getvalue())


async def test_debug_500_detail_is_masked(monkeypatch):
    """DEBUG 의 500 응답 ``detail`` 은 클라이언트로 나간다 — 같은 규칙으로 가린다."""
    import main

    monkeypatch.setattr(main.app_settings, "DEBUG", True, raising=False)
    handler = main.app.exception_handlers[Exception]
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})

    response = await handler(request, RuntimeError(f"cannot connect {DSN}"))

    body = bytes(response.body).decode()
    assert response.status_code == 500
    assert "secret42" not in body
    assert "mysql+asyncmy://***:***@h/db" in body


ACCESS_CLI_PROBE = """
import logging, logging.config
from uvicorn.config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)   # uvicorn main:app CLI 는 앱 import 전에 이것을 적용한다
from app.utils.logs import setup
setup.configure_logging(force=True)
from tests.utils.test_log_redaction import ACCESS_FMT, ACCESS_SECRET_ARGS
logging.getLogger("uvicorn.access").info(ACCESS_FMT, *ACCESS_SECRET_ARGS)
setup.stop_log_listener()
"""


def test_uvicorn_cli_access_line_is_masked_and_not_lost(tmp_path):
    """``uvicorn main:app`` 의 접속 줄: 비밀값은 가려지고 줄은 uvicorn 형식 그대로 남는다(config-cleanup F-008)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("LOG_")}
    env.update(PYTHONPATH=str(PROJECT_ROOT), PYTHONIOENCODING="utf-8")
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", ACCESS_CLI_PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Logging error" not in proc.stderr, proc.stderr
    assert (
        'INFO:     127.0.0.1:5000 - "GET /x?token=***&password=*** HTTP/1.1" 200 OK' in proc.stdout
    ), proc.stdout + proc.stderr
    for secret in ("tok-9f3e7a", "secret42"):
        assert secret not in proc.stdout + proc.stderr
