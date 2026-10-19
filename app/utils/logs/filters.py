"""로그 컨텍스트 필터.

record 에 두 필드를 주입한다.
- appname: 소스 파일 **경로**에서 앱 식별. 로거 이름이 아니라 경로를 쓰는 이유는
  ``app/utils/logs/config.py`` 상단 참고. 산출값은 아래 ``_app_from_path`` 참조.
- classname:
    · 방식 C — LoggerAdapter/extra 로 이미 주입돼 있으면 그대로 존중(오버헤드 0).
    · 방식 A — 없으면 호출 프레임에서 self/cls 를 찾아 클래스명을 자동 추출.
  자유 함수(클래스 없음)는 '-'.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from types import FrameType

from config import log_secret_values

# 이 파일은 <저장소루트>/app/utils/logs/filters.py 다. parents[3] 이 저장소 루트.
# 파일을 옮기면 이 계산이 조용히 어긋나므로, tests/utils/test_logs.py 가
# main.py -> "app" 을 단언해 이동을 즉시 잡는다.
_REPO_ROOT = str(Path(__file__).resolve().parents[3]).replace("\\", "/").rstrip("/").lower() + "/"


def _app_from_path(pathname: str) -> str:
    """소스 경로에서 앱 라벨을 만든다.

    반환값:
        ``<기능명>``  — ``app/features/<name>/**``
        ``core`` · ``celery`` · ``utils`` · ``migrations`` — 해당 하위 시스템
        ``app``  — 그 밖의 **이 저장소 안** 코드(``main.py`` · ``config.py`` · ``tests/**`` 등)
        ``ext``  — **저장소 밖** 코드(설치된 서드파티 패키지)

    ``ext`` 는 "우리 코드가 아님"을 뜻한다. 예전에는 경로에 ``/app/`` 조각이 있는지로만
    판별해서 저장소 루트의 ``main.py``·``config.py``·``migrations/`` 가 ``ext`` 로 빠졌다.
    진입점이 서드파티로 분류되면 이 필드로 우리 코드를 거를 수 없다(LOG-2).
    """
    p = pathname.replace("\\", "/")
    if "/features/" in p:
        return p.split("/features/", 1)[1].split("/", 1)[0]
    for seg in ("/app/core/", "/app/celery/", "/app/utils/", "/migrations/"):
        if seg in p:
            return seg.strip("/").rsplit("/", 1)[-1]
    # .venv 는 저장소 루트 **안**에 있으므로 루트 판정보다 먼저 걸러야 한다.
    if "/site-packages/" in p or "/dist-packages/" in p:
        return "ext"
    if "/app/" in p:
        return "app"
    return "app" if p.lower().startswith(_REPO_ROOT) else "ext"


def _class_from_stack() -> str:
    """호출 스택에서 logging/이 패키지 프레임을 건너뛰고 첫 사용자 프레임의 클래스명을 찾는다."""
    frame: FrameType | None = sys._getframe(0)
    while frame is not None:
        filename = frame.f_code.co_filename.replace("\\", "/")
        if "/logging/" not in filename and "/utils/logs/" not in filename:
            local_self = frame.f_locals.get("self")
            if local_self is not None:
                return type(local_self).__name__
            local_cls = frame.f_locals.get("cls")
            if isinstance(local_cls, type):
                return local_cls.__name__
            return "-"
        frame = frame.f_back
    return "-"


class ContextFilter(logging.Filter):
    """record 에 appname/classname 을 채운다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "appname", None):
            record.appname = _app_from_path(record.pathname)
        if not getattr(record, "classname", None):
            record.classname = _class_from_stack()
        return True


# SQL 본문과 바인딩 파라미터를 저레벨 로그로 내보내는 로거들.
# 이름 그대로가 아니라 **접두사**로 본다 — sqlalchemy.engine.Engine 처럼
# 하위 로거가 실제 발행자인 경우가 많다.
SQL_NOISE_LOGGER_PREFIXES = (
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "aiosqlite",
    "aiomysql",
    "asyncmy",
    "pymysql",
)

# 이 레벨 미만은 버린다. 연결 실패 같은 경고·오류는 통과시켜야 장애를 볼 수 있다.
_SQL_NOISE_MIN_LEVEL = logging.WARNING


class SqlNoiseFilter(logging.Filter):
    """SQL 본문·파라미터가 로그로 새는 것을 막는다 (NFR-001).

    이 프로젝트의 기본값은 ``DEBUG=true`` 이고 그러면 유효 로그 레벨이 DEBUG 다.
    그 상태에서 SQLAlchemy 와 드라이버는 실행한 SQL 과 **바인딩된 값**을 그대로
    찍는다. 값에는 비밀번호 해시·토큰·검색어가 들어 있고 로그는 보통 외부
    collector 로 흘러간다.

    ``loggers`` 키를 추가해 레벨을 조정하는 대신 필터를 쓰는 이유는 ADR-019
    (앱별 로거를 등록하지 않고 경로로 appname 을 판별한다)를 깨지 않기 위해서다.
    핸들러는 여전히 root 에만 붙는다.

    SQL 을 봐야 하는 개발자는 ``LOG_SQL_ECHO_ENABLED=true`` 로 명시적으로 연다.
    """

    def __init__(self, allow_sql_echo: bool = False) -> None:
        super().__init__()
        self.allow_sql_echo = allow_sql_echo

    def filter(self, record: logging.LogRecord) -> bool:
        if self.allow_sql_echo:
            return True
        if record.levelno >= _SQL_NOISE_MIN_LEVEL:
            return True
        return not record.name.startswith(SQL_NOISE_LOGGER_PREFIXES)


# =============================================================================
# 비밀값 마스킹 — 규칙의 정본 (log-redaction ADR-001)
# =============================================================================
REDACTED = "***"

# 각 패턴은 남길 앞부분을 ``keep`` 그룹으로 잡고, 그 뒤의 값만 ``REDACTED`` 로 바꾼다.
# 로그 메시지·traceback·stack·DEBUG 500 응답 detail 이 모두 ``redact()`` 하나를 쓴다 —
# 패턴을 다른 곳에 복제하지 않는다.
_SECRET_PATTERNS = (
    # DSN 의 비밀번호: scheme://user:<password>@host
    re.compile(r"(?P<keep>\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]*:)[^\s@/]+(?=@)"),
    # DSN 의 사용자명: scheme://<user>[:password]@host (logging-overhaul L7)
    re.compile(r"(?P<keep>\b[a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s:/@]+(?=(?::[^\s@/]*)?@)"),
    # Authorization 헤더 값: "Authorization: Bearer <token>" · "authorization=<token>"
    re.compile(
        r"(?i)(?P<keep>\b(?:proxy-)?authorization\b[\"']?\s*[:=]\s*[\"']?"
        r"(?:(?:bearer|basic|token)\s+)?)[^\s\"',;]+"
    ),
    # 헤더 이름 없이 남은 Bearer 토큰
    re.compile(r"(?i)(?P<keep>\bbearer\s+)[a-z0-9\-._~+/]+=*"),
    # key=value · key: value · "key": "value" — 키 이름에 비밀 단어가 들어 있으면
    re.compile(
        r"(?i)(?P<keep>\b[\w\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key)[\w\-]*"
        r"[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&)}\]]+"
    ),
)


# 설정된 비밀값 원문(``config.LOG_SECRET_SETTINGS``). 이보다 짧은 값(주로 계정명)은 일반 단어를
# 가리는 오탐을 막으려고 원문 일치로 가리지 않고 ``user=``·``username=`` 형태에서만 가린다 —
# DSN 의 사용자명은 위 패턴이 따로 가린다.
SECRET_VALUES: tuple[str, ...] = log_secret_values()
_LITERAL_MIN_LENGTH = 4


def redact(text: str) -> str:
    """문자열 안의 비밀값(DSN 계정·Authorization·password= 류·설정 비밀값 원문)을 ``***`` 로 가린다."""
    for value in SECRET_VALUES:
        if len(value) >= _LITERAL_MIN_LENGTH:
            text = text.replace(value, REDACTED)
        else:
            text = re.sub(
                rf"(?i)(\buser(?:name)?[\"']?\s*[:=]\s*[\"']?){re.escape(value)}(?![\w])",
                lambda m: m.group(1) + REDACTED,
                text,
            )
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group("keep") + REDACTED, text)
    return text


_TRACEBACK_FORMATTER = logging.Formatter()


class RedactingFilter(logging.Filter):
    """record 의 메시지·traceback·stack_info 에서 비밀값을 가린다 (log-redaction ADR-001).

    traceback 은 보통 **포매터**가 나중에 ``exc_info`` 에서 만든다. 그때는 필터가 이미 지나간
    뒤라 가릴 기회가 없다. 그래서 여기서 ``exc_info`` 를 미리 ``exc_text`` 로 포맷해 가려
    둔다 — ``logging.Formatter.format`` 은 ``exc_text`` 가 있으면 다시 만들지 않는다.
    ``exc_info`` 는 남겨 두므로 예외 타입·파일·줄 같은 진단 정보는 그대로 나간다.

    메시지는 **가릴 것이 있을 때만** 바꾼다. 평소에는 ``msg``/``args`` 를 건드리지 않는다 —
    uvicorn 의 access 포매터처럼 ``args`` 를 직접 읽는 포매터가 있다. 가릴 것이 있어도 비밀값이
    **인자 안에만** 있으면 그 인자만 가리고 ``args`` 모양을 지킨다(그 포매터가 ``args`` 를 풀다
    실패해 줄이 사라지지 않게 — config-cleanup F-008). 틀·인자에 걸치면 합친 문자열로 바꾸고
    ``args`` 를 비운다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # 포맷 오류는 기존대로 핸들러의 handleError 가 보고하게 둔다.
            message = None
        if message is not None:
            masked = redact(message)
            if masked != message and not self._mask_args_only(record, masked):
                record.msg = masked
                record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = _TRACEBACK_FORMATTER.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True

    @staticmethod
    def _mask_args_only(record: logging.LogRecord, masked: str) -> bool:
        """인자만 가려서 합친 결과가 ``masked`` 와 같으면 그 인자로 바꾸고 True."""
        if not isinstance(record.args, tuple):
            return False
        args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        try:
            if str(record.msg) % args != masked:
                return False
        except Exception:
            return False
        record.args = args
        return True


def add_redacting_filter(target: logging.Logger | logging.Handler) -> None:
    """``RedactingFilter`` 를 한 번만 붙인다(여러 번 불러도 중복되지 않는다)."""
    if not any(isinstance(existing, RedactingFilter) for existing in target.filters):
        target.addFilter(RedactingFilter())


class StaticAppFilter(logging.Filter):
    """appname 을 고정값으로 미리 찍는다 — 서드파티 로거용.

    uvicorn 처럼 소스가 site-packages 에 있는 로거는 경로 판별이 ``ext`` 로 떨어져
    "어느 앱의 로그인지"를 잃는다. 해당 로거에 이 필터를 붙이면 ``ContextFilter``
    가 이미 채워진 값을 존중하므로(``if not getattr(...)``) 라벨이 유지된다.
    """

    def __init__(self, appname: str) -> None:
        super().__init__()
        self.appname = appname

    def filter(self, record: logging.LogRecord) -> bool:
        record.appname = self.appname
        return True
