"""타임존 인식 Formatter.

asctime 을 설정된 타임존(또는 UTC)으로 렌더하고, 약어(KST/UTC)를 record.tzname 에 주입한다.
style 은 '{' 고정. appname/classname 이 비어 있으면 안전 기본값으로 채운다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.utils.logs.filters import _app_from_path
from config import timezone_settings

_UTC = ZoneInfo("UTC")


class TzFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        use_utc: bool = False,
        with_ms: bool = False,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style="{")
        self.use_utc = use_utc
        self.with_ms = with_ms

    def _tz(self) -> ZoneInfo:
        return _UTC if self.use_utc else timezone_settings.tz

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=self._tz())
        rendered = dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S")
        # 밀리초는 날짜 형식과 무관하게 붙인다 — LOG_DATE_FORMAT 을 줘도 development 의 표기가 유지된다.
        if self.with_ms:
            rendered = f"{rendered}.{int(record.msecs):03d}"
        return rendered

    def format(self, record: logging.LogRecord) -> str:
        record.tzname = (
            "UTC" if self.use_utc else (datetime.now(self._tz()).strftime("%Z") or "KST")
        )
        if not getattr(record, "appname", None):
            # ContextFilter 를 거치지 않은 줄(남이 만든 핸들러)도 같은 판별 함수로 헤더를 붙인다.
            record.appname = _app_from_path(record.pathname, record.name)
        if not getattr(record, "classname", None):
            record.classname = "-"
        return super().format(record)
