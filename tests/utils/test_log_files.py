"""파일 로그 — 프로세스별 + 에러 (logging-overhaul L5) 와 비밀값 원문 차단 (L7) 의 실제 출력.

실제 로깅 구성을 저장소 밖 tmp 작업 디렉터리의 자식 프로세스에 적용해 본다(이 프로세스의 로깅은
바꾸지 않는다). 파일은 그 tmp 아래 ``LOG_DIR`` 에 생긴다.
"""

from __future__ import annotations

import re

from tests.utils.test_log_settings_wiring import PROJECT_LINE, _run

WEB_PROBE = """
import logging
from app.utils.logs import setup
setup.configure_logging(force=True)
setup.attach_log_files("app")
logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/p", "1.1", 200)
logging.getLogger("probe").info("web-info")
logging.getLogger("probe").error("web-error")
setup.stop_log_listener()
"""

CELERY_WORKER_PROBE = """
import logging, sys
from celery.signals import after_setup_logger
import app.celery.lifecycle  # 시그널 수신자 등록
from app.utils.logs import setup
root = logging.getLogger()
root.handlers = [logging.StreamHandler(sys.stderr)]   # worker_hijack_root_logger 가 하는 일
root.setLevel(logging.INFO)
after_setup_logger.send(sender=None, logger=root, loglevel=logging.INFO, logfile=None, format="", colorize=False)
logging.getLogger("celery.worker.strategy").info("celery-lib-info")
logging.getLogger("probe").error("task-error")
setup.stop_log_listener()
"""

FILES_ON = {"LOG_FILE_ENABLED": "true", "LOG_DIR": "logs"}


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_web_process_writes_app_log_and_error_log(tmp_path):
    proc = _run(WEB_PROBE, tmp_path, **FILES_ON)
    logs = tmp_path / "logs"
    assert sorted(p.name for p in logs.iterdir()) == ["app.log", "error.log"], proc.stderr
    app_log = "\n".join(_lines(logs / "app.log"))
    for level, app, msg in (
        ("INFO", "uvicorn", r'1\.2\.3\.4:5 - "GET /p HTTP/1\.1" 200'),
        ("INFO", "ext", "web-info"),
        ("ERROR", "ext", "web-error"),
    ):
        assert re.search(PROJECT_LINE.format(level=level, app=app, msg=msg), app_log), app_log
    assert [ln.endswith("web-error") for ln in _lines(logs / "error.log")] == [True]


def test_celery_worker_writes_its_own_files(tmp_path):
    proc = _run(CELERY_WORKER_PROBE, tmp_path, **FILES_ON)
    logs = tmp_path / "logs"
    assert sorted(p.name for p in logs.iterdir()) == ["celery-error.log", "celery.log"], proc.stderr
    text = "\n".join(_lines(logs / "celery.log"))
    assert re.search(PROJECT_LINE.format(level="INFO", app="celery", msg="celery-lib-info"), text)
    assert [ln.endswith("task-error") for ln in _lines(logs / "celery-error.log")] == [True]
    # 콘솔(stdout)도 같은 형식이다.
    assert re.search(
        PROJECT_LINE.format(level="INFO", app="celery", msg="celery-lib-info"), proc.stdout
    )


def test_web_entry_point_attaches_the_web_files(tmp_path):
    """웹 진입점(``main.py`` import)이 프로세스 종류를 정한다 — 앱 기동 줄이 app.log 에 남는다."""
    code = "import main\nfrom app.utils.logs import setup\nsetup.stop_log_listener()\n"
    proc = _run(code, tmp_path, **FILES_ON)
    text = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "[main:-:<module>:" in text, proc.stderr
    assert not (tmp_path / "logs" / "celery.log").exists()


def test_file_level_applies_to_the_process_file_only(tmp_path):
    _run(WEB_PROBE, tmp_path, LOG_FILE_LEVEL="ERROR", **FILES_ON)
    lines = _lines(tmp_path / "logs" / "app.log")
    assert len(lines) == 1 and lines[0].endswith("web-error")


def test_files_are_off_by_default(tmp_path):
    proc = _run(WEB_PROBE, tmp_path)
    assert not (tmp_path / "logs").exists()
    assert "web-info" in proc.stdout


SECRETS = {
    "MYSQL_USER": "dbowner",
    "MYSQL_PASSWORD": "Db-Pass-777",
    "MYSQL_REPLICA_PASSWORD": "Replica-Pass-888",
    "REDIS_PASSWORD": "Redis-Pass-999",
    "ACCESS_TOKEN_SECRET_KEY": "access-secret-0123456789abcdefghijklmnop",
    "REFRESH_TOKEN_SECRET_KEY": "refresh-secret-0123456789abcdefghijklmno",
    "SESSION_SECRET_KEY": "session-secret-0123456789abcdefghijklmno",
}
LEAK_PROBE = """
import logging, logging.config, os
from uvicorn.config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)   # uvicorn main:app CLI 경로
from celery.signals import after_setup_logger
import app.celery.lifecycle
from app.utils.logs import setup
setup.configure_logging(force=True)
setup.attach_log_files("app")
values = [os.environ[k] for k in {keys!r}]
logging.getLogger("probe").warning("app line %s", " ".join(values))
logging.getLogger("uvicorn.error").warning("uvicorn line " + " ".join(values))
logging.getLogger("celery.worker").warning("celery line %s", values)
try:
    raise RuntimeError("chained " + values[1])
except RuntimeError:
    logging.getLogger("probe").exception("boom user=%s", values[0])
setup.stop_log_listener()
"""


def test_configured_secret_values_never_reach_any_output(tmp_path):
    proc = _run(LEAK_PROBE.format(keys=list(SECRETS)), tmp_path, **FILES_ON, **SECRETS)
    outputs = {"stdout": proc.stdout, "stderr": proc.stderr}
    for path in (tmp_path / "logs").iterdir():
        outputs[path.name] = path.read_text(encoding="utf-8")
    assert "uvicorn line" in outputs["app.log"] and "celery line" in outputs["app.log"]
    for name, text in outputs.items():
        for key, value in SECRETS.items():
            assert value not in text, f"{key} 원문이 {name} 에 남았다:\n{text}"
