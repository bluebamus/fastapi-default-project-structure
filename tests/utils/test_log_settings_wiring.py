"""로그 설정 연결 — config-cleanup-2 (LOG_CONSOLE_FORMAT·LOG_DATE_FORMAT·LOG_CONSOLE_ENABLED).

출력 줄은 **실제 로깅 구성을 자식 프로세스에 적용해** 본다(이 프로세스의 로깅을 바꾸지 않는다).
자식은 빈 임시 폴더에서 돌린다 — 로컬 `.env` 의 LOG_* 값이 결과를 가리지 않게.
경로별로 본다: 앱 로거(queue → listener), ``uvicorn main:app`` CLI 의 uvicorn 핸들러,
Celery worker 가 단 핸들러(``after_setup_logger``).
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess  # noqa: S404 - 실제 로깅 구성을 자식 프로세스에 적용해 본다
import sys

import pytest
from pydantic import ValidationError

from config import LogSettings
from tests.utils.test_log_redaction import PIPELINE_PROBE, _assert_redacted_traceback

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 변경 전 코드에 하드코딩돼 있던 포맷 — 기본값은 이것과 같아야 한다(기본 출력 불변).
OLD_HARDCODED_FORMAT = (
    "[{asctime} {tzname}] {levelname:5} [app={appname}] "
    "[{module}:{classname}:{funcName}:{lineno}] {message}"
)
CUSTOM = {
    "LOG_CONSOLE_FORMAT": "CUSTOM|{levelname}|{asctime}|{message}",
    "LOG_DATE_FORMAT": "%Y/%m/%d",
}
CUSTOM_LINE = r"CUSTOM\|{level}\|\d{{4}}/\d{{2}}/\d{{2}}\|{msg}"
DISABLED_WARNING = "LOG_CONSOLE_ENABLED=false"

APP_PROBE = """
import logging
from config import app_settings
app_settings.ENV = {env!r}
from app.utils.logs import setup
setup.configure_logging(force=True)
logging.getLogger("probe").warning("hello-app")
setup.stop_log_listener()
"""

UVICORN_CLI_PROBE = """
import logging, logging.config
from uvicorn.config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)   # uvicorn CLI 는 앱 import 전에 이것을 적용한다
from app.utils.logs import setup
setup.configure_logging(force=True)
logging.getLogger("uvicorn.error").info("hello-uvicorn")
print("UVICORN_STREAM_HANDLERS", len(logging.getLogger("uvicorn.error").handlers))
setup.stop_log_listener()
"""

CELERY_PROBE = """
import logging, sys
from celery.app.log import ColorFormatter
from celery.signals import after_setup_logger
import app.celery.lifecycle  # 시그널 수신자 등록
from app.utils.logs import setup
logger = logging.getLogger("probe.celery")
logger.propagate = False
console = logging.StreamHandler(sys.stderr)   # celery 가 다는 콘솔 핸들러와 같은 종류
console.setFormatter(ColorFormatter("CELERYFMT %(levelname)s %(message)s", use_color=False))
logfile = logging.FileHandler({logfile!r}, encoding="utf-8")   # celery --logfile
logfile.setFormatter(logging.Formatter("FILE %(message)s"))
logger.addHandler(console)
logger.addHandler(logfile)
after_setup_logger.send(sender=None, logger=logger, loglevel=logging.INFO, logfile=None, format="", colorize=False)
logger.warning("hello-celery")
logfile.close()
print("CELERY_HANDLERS", sorted(type(h).__name__ for h in logger.handlers))
setup.stop_log_listener()
"""


def _run(
    code: str, tmp_path: pathlib.Path, **env_overrides: str
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("LOG_")}
    env.update(PYTHONPATH=str(PROJECT_ROOT), PYTHONIOENCODING="utf-8", ENV="test", **env_overrides)
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc


def _line(pattern: str, text: str) -> None:
    assert re.search(rf"^{pattern}$", text, re.MULTILINE), f"{pattern!r} 형식의 줄이 없다:\n{text}"


# =============================================================================
# 기본값 = 변경 전 출력
# =============================================================================
def test_default_format_is_the_old_hardcoded_one():
    from app.utils.logs import LOG_FORMAT

    assert LogSettings.model_fields["LOG_CONSOLE_FORMAT"].default == OLD_HARDCODED_FORMAT
    assert LOG_FORMAT == OLD_HARDCODED_FORMAT
    assert LogSettings.model_fields["LOG_DATE_FORMAT"].default == "%Y-%m-%d %H:%M:%S"


@pytest.mark.parametrize(
    ("env", "ms"), [("test", ""), ("development", r"\.\d{3}"), ("production", "")]
)
def test_default_app_output_is_unchanged(tmp_path, env, ms):
    proc = _run(APP_PROBE.format(env=env), tmp_path)
    _line(
        rf"\[\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}}{ms} \w+\] WARNING \[app=\w+\] "
        r"\[<string>:-:<module>:\d+\] hello-app",
        proc.stdout,
    )
    assert DISABLED_WARNING not in proc.stderr


def test_default_uvicorn_cli_and_celery_output_is_unchanged(tmp_path):
    proc = _run(UVICORN_CLI_PROBE, tmp_path)
    _line(r"INFO:     hello-uvicorn", proc.stderr)
    proc = _run(CELERY_PROBE.format(logfile=str(tmp_path / "c.log")), tmp_path)
    _line(r"CELERYFMT WARNING hello-celery", proc.stderr)


# =============================================================================
# 사용자 포맷·날짜 형식이 실제 출력 줄이 된다
# =============================================================================
@pytest.mark.parametrize("env", ["test", "development"])
def test_custom_format_and_datefmt_apply_to_app_logger(tmp_path, env):
    proc = _run(APP_PROBE.format(env=env), tmp_path, **CUSTOM)
    # development 의 밀리초는 날짜 형식 뒤에 붙는다(기존 동작 유지).
    suffix = r"\.\d{3}" if env == "development" else ""
    _line(
        r"CUSTOM\|WARNING\|\d{4}/\d{2}/\d{2}" + suffix + r"\|hello-app",
        proc.stdout,
    )


def test_custom_format_applies_to_uvicorn_cli_handlers(tmp_path):
    proc = _run(UVICORN_CLI_PROBE, tmp_path, **CUSTOM)
    _line(CUSTOM_LINE.format(level="INFO", msg="hello-uvicorn"), proc.stderr)


def test_custom_format_applies_to_celery_console_handler_not_file(tmp_path):
    logfile = tmp_path / "c.log"
    proc = _run(CELERY_PROBE.format(logfile=str(logfile)), tmp_path, **CUSTOM)
    _line(CUSTOM_LINE.format(level="WARNING", msg="hello-celery"), proc.stderr)
    assert logfile.read_text(encoding="utf-8").strip() == "FILE hello-celery"


def test_redaction_holds_with_custom_format(tmp_path):
    """사용자 포맷에서도 메시지·traceback·stack_info 의 비밀값이 가려진다(log-redaction ADR-001)."""
    proc = _run(PIPELINE_PROBE, tmp_path, LOG_CONSOLE_FORMAT="USERFMT {levelname} {message}")
    for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        assert (
            "USERFMT ERROR probe failed for" in stream
        ), f"{name} 에 사용자 포맷 줄이 없다:\n{stream}"
        _assert_redacted_traceback(stream)
        assert "Stack (most recent call last)" in stream
        assert "u:secret42@h" not in stream


# =============================================================================
# LOG_CONSOLE_ENABLED=false
# =============================================================================
@pytest.mark.parametrize("env", ["test", "production"])
def test_console_disabled_app_logger_writes_nothing_and_warns_once(tmp_path, env):
    proc = _run(APP_PROBE.format(env=env), tmp_path, LOG_CONSOLE_ENABLED="false")
    assert "hello-app" not in proc.stdout + proc.stderr
    assert proc.stderr.count(DISABLED_WARNING) == 1, proc.stderr
    assert len([ln for ln in proc.stderr.splitlines() if DISABLED_WARNING in ln]) == 1


def test_console_disabled_builds_no_console_handlers(monkeypatch):
    from app.utils.logs import config as logs_config

    monkeypatch.setattr(logs_config.log_settings, "LOG_CONSOLE_ENABLED", False)
    for env in ("development", "test", "staging", "production"):
        monkeypatch.setattr(logs_config.app_settings, "ENV", env)
        cfg = logs_config.build_dictconfig()
        assert set(cfg["handlers"]) == {"queue"}, env
        assert cfg["handlers"]["queue"]["handlers"] == [], env


def test_console_disabled_removes_uvicorn_cli_console_handlers(tmp_path):
    proc = _run(UVICORN_CLI_PROBE, tmp_path, LOG_CONSOLE_ENABLED="false")
    assert "hello-uvicorn" not in proc.stdout + proc.stderr
    assert "UVICORN_STREAM_HANDLERS 0" in proc.stdout


def test_console_disabled_keeps_celery_file_handler(tmp_path):
    logfile = tmp_path / "c.log"
    proc = _run(CELERY_PROBE.format(logfile=str(logfile)), tmp_path, LOG_CONSOLE_ENABLED="false")
    assert "hello-celery" not in proc.stderr
    assert "CELERY_HANDLERS ['FileHandler']" in proc.stdout
    assert logfile.read_text(encoding="utf-8").strip() == "FILE hello-celery"


# =============================================================================
# 설정 검증
# =============================================================================
@pytest.mark.parametrize(
    "fmt",
    ["{foo} {message}", "{message", "{asctime} {levelname:Q} {message}"],
    ids=["unknown-field", "unbalanced-brace", "bad-spec"],
)
def test_invalid_console_format_is_a_settings_error(fmt):
    with pytest.raises(ValidationError, match="LOG_CONSOLE_FORMAT"):
        LogSettings(_env_file=None, LOG_CONSOLE_FORMAT=fmt)


@pytest.mark.parametrize("datefmt", ["", "   "])
def test_empty_date_format_is_a_settings_error(datefmt):
    with pytest.raises(ValidationError, match="LOG_DATE_FORMAT"):
        LogSettings(_env_file=None, LOG_DATE_FORMAT=datefmt)


def test_valid_custom_format_is_accepted():
    s = LogSettings(_env_file=None, **CUSTOM)
    assert s.LOG_CONSOLE_FORMAT == CUSTOM["LOG_CONSOLE_FORMAT"]


# =============================================================================
# python main.py 경로의 uvicorn 접속 로그 — 회귀
#
# 접속 로그 레코드는 msg 와 args 만 갖는다. {client_addr}·{request_line}·{status_code} 는 uvicorn 의
# AccessFormatter 만 만드는 필드라, 공유 queue 의 TzFormatter 가 그런 필드를 쓰면 줄마다 logging 오류가 난다.
# 이 저장소는 {message} 로 렌더하고(필드를 쓰는 포맷은 설정 검증이 거부한다) 이 테스트가 그것을 고정한다.
# =============================================================================
ACCESS_PROBE = """
import logging, logging.config
from app.utils.logs import setup
setup.configure_logging(force=True)
logging.config.dictConfig(setup.setup_uvicorn_logging())   # run_server(): uvicorn.run(log_config=...)
logging.getLogger("uvicorn.access").info(
    '%s - "%s %s HTTP/%s" %d', "127.0.0.1:5000", "GET", "/x?password=secret42", "1.1", 200
)
setup.stop_log_listener()
"""
ACCESS_LINE = r'127\.0\.0\.1:5000 - "GET /x\?password=\*\*\* HTTP/1\.1" 200'


@pytest.mark.parametrize("custom", [False, True], ids=["default", "custom"])
def test_main_py_access_log_renders_without_logging_error(tmp_path, custom):
    overrides = {"LOG_CONSOLE_FORMAT": "U|{asctime}|{tzname}|{message}", "LOG_DATE_FORMAT": "%H:%M"}
    proc = _run(ACCESS_PROBE, tmp_path, **(overrides if custom else {}))
    assert "Logging error" not in proc.stderr, proc.stderr
    assert "secret42" not in proc.stdout + proc.stderr
    if custom:
        _line(rf"U\|\d{{2}}:\d{{2}}\|\w+\|{ACCESS_LINE}", proc.stdout)
    else:
        _line(
            rf"\[\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}} \w+\] INFO  \[app=uvicorn\] \[\S+\] {ACCESS_LINE}",
            proc.stdout,
        )


def test_access_only_fields_are_rejected_at_settings_load():
    with pytest.raises(ValidationError, match="client_addr"):
        LogSettings(_env_file=None, LOG_CONSOLE_FORMAT="{client_addr} {request_line} {message}")
