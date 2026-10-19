"""날짜 + 크기로 회전하고 보관 일수를 넘긴 파일을 지우는 파일 핸들러 (logging-overhaul L6).

- 매일 자정(로그 시각과 **같은 시간대** — ``TzFormatter`` 의 UTC/로컬 결정과 같다)에 ``app.log`` 를
  ``app.log.2026-10-19`` 로 넘긴다.
- 하루 안에서 ``max_bytes`` 를 넘으면 ``app.log.2026-10-19.1``·``.2``… 로 나눈다.
- 교체할 때마다 ``retention_days`` 보다 오래된 날짜의 파일(분할 파일 포함)을 지운다. 0 이면 지우지 않는다.

교체 대상 이름이 이미 있으면 **덮지 않고** 다음 번호로 넘긴다 — 표준 ``TimedRotatingFileHandler`` 는
지우고 덮는데, 여러 프로세스가 같은 파일을 쓰면 그것이 곧 유실이다. 그래도 다중 프로세스 회전은
안전하지 않다(README "여러 워커"). 쓰기는 queue listener 스레드에서 일어난다(NFR-009).
"""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta, tzinfo
from datetime import time as dtime
from logging import LogRecord
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class DailySizeRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, filename: str, tz: tzinfo, max_bytes: int, retention_days: int) -> None:
        self.tz = tz
        self.max_bytes = max_bytes
        self.retention_days = retention_days
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, when="midnight", encoding="utf-8", delay=True)
        # 회전 파일 이름: <base>.YYYY-MM-DD 또는 <base>.YYYY-MM-DD.N
        self._rotated = re.compile(
            re.escape(Path(self.baseFilename).name) + r"\.(\d{4}-\d{2}-\d{2})(?:\.\d+)?$"
        )

    def computeRollover(self, currentTime: float) -> int:
        """``currentTime`` 다음의 자정(설정 시간대)."""
        day = datetime.fromtimestamp(currentTime, self.tz).date() + timedelta(days=1)
        return int(datetime.combine(day, dtime(), self.tz).timestamp())

    def shouldRollover(self, record: LogRecord) -> bool:
        if time.time() >= self.rolloverAt:
            return True
        if self.stream is None:
            self.stream = self._open()
        pos = self.stream.tell()
        # 빈 파일은 나누지 않는다 — 한 줄이 max_bytes 보다 커도 무한 회전하지 않게.
        return bool(pos) and pos + len(self.format(record) + self.terminator) >= self.max_bytes

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        now = time.time()
        if now >= self.rolloverAt:
            closed = datetime.fromtimestamp(self.rolloverAt - 1, self.tz).date()
            target = self._free_name(f"{self.baseFilename}.{closed}", plain_first=True)
            self.rolloverAt = self.computeRollover(now)
        else:
            today = datetime.fromtimestamp(now, self.tz).date()
            target = self._free_name(f"{self.baseFilename}.{today}", plain_first=False)
        if os.path.exists(self.baseFilename):
            os.rename(self.baseFilename, target)
        self._delete_expired(datetime.fromtimestamp(now, self.tz).date())

    @staticmethod
    def _free_name(stem: str, plain_first: bool) -> str:
        if plain_first and not os.path.exists(stem):
            return stem
        n = 1
        while os.path.exists(f"{stem}.{n}"):
            n += 1
        return f"{stem}.{n}"

    def _delete_expired(self, today: date) -> None:
        if self.retention_days <= 0:
            return
        cutoff = today - timedelta(days=self.retention_days)
        folder = Path(self.baseFilename).parent
        for path in folder.iterdir():
            match = self._rotated.match(path.name)
            if match and date.fromisoformat(match.group(1)) < cutoff:
                path.unlink(missing_ok=True)
