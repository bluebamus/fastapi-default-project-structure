"""파일 로그 회전 — 날짜 + 크기 + 보관 일수 (logging-overhaul L6).

모두 tmp 경로의 실제 파일로 본다. 자정 교체는 ``rolloverAt`` 을 과거로 당겨 재현한다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.utils.logs.handlers import DailySizeRotatingFileHandler

UTC = ZoneInfo("UTC")
KST = ZoneInfo("Asia/Seoul")


def _handler(path: Path, *, max_bytes: int = 1_000_000, retention_days: int = 0, tz=UTC):
    handler = DailySizeRotatingFileHandler(
        str(path), tz=tz, max_bytes=max_bytes, retention_days=retention_days
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def _emit(handler: logging.Handler, message: str) -> None:
    handler.emit(logging.LogRecord("t", logging.INFO, __file__, 1, message, None, None))


def _today(tz=UTC) -> date:
    return datetime.now(tz).date()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_midnight_rollover_names_the_closed_day(tmp_path):
    log = tmp_path / "app.log"
    handler = _handler(log)
    try:
        _emit(handler, "yesterday-line")
        closed_day = datetime.fromtimestamp(time.time() - 60, UTC).date()
        handler.rolloverAt = int(time.time()) - 60 + 1  # 자정이 1분 전에 지났다
        _emit(handler, "today-line")
    finally:
        handler.close()

    assert _read(tmp_path / f"app.log.{closed_day}") == "yesterday-line\n"
    assert _read(log) == "today-line\n"
    next_midnight = datetime.combine(_today() + timedelta(days=1), datetime.min.time(), UTC)
    assert handler.rolloverAt == int(next_midnight.timestamp())


def test_rollover_boundary_follows_the_configured_timezone(tmp_path):
    """교체 시각은 로그 시각과 같은 시간대의 자정이다(KST 면 KST 자정)."""
    handler = _handler(tmp_path / "app.log", tz=KST)
    try:
        at = datetime(2026, 10, 19, 23, 30, tzinfo=KST).timestamp()
        expected = datetime(2026, 10, 20, 0, 0, tzinfo=KST).timestamp()
        assert handler.computeRollover(at) == int(expected)
    finally:
        handler.close()


def test_size_split_within_a_day_numbers_the_parts(tmp_path):
    log = tmp_path / "app.log"
    handler = _handler(log, max_bytes=30)
    try:
        for i in range(6):
            _emit(handler, f"line-{i:02d}-xxxxxxxx")  # 줄당 20바이트 → 파일당 1줄
    finally:
        handler.close()

    today = _today()
    parts = sorted(tmp_path.glob(f"app.log.{today}.*"), key=lambda p: int(p.suffix[1:]))
    assert [p.name for p in parts] == [f"app.log.{today}.{n}" for n in range(1, 6)]
    joined = "".join(_read(p) for p in parts) + _read(log)
    assert joined == "".join(f"line-{i:02d}-xxxxxxxx\n" for i in range(6)), "분할 중 잃은 줄이 있다"


def test_rollover_never_overwrites_an_existing_file(tmp_path):
    """다른 프로세스가 먼저 만든 같은 이름이 있으면 덮지 않고 다음 번호로 넘긴다."""
    log = tmp_path / "app.log"
    handler = _handler(log)
    try:
        _emit(handler, "mine")
        closed_day = datetime.fromtimestamp(time.time() - 60, UTC).date()
        (tmp_path / f"app.log.{closed_day}").write_text("other-process\n", encoding="utf-8")
        handler.rolloverAt = int(time.time()) - 59
        _emit(handler, "next")
    finally:
        handler.close()

    assert _read(tmp_path / f"app.log.{closed_day}") == "other-process\n"
    assert _read(tmp_path / f"app.log.{closed_day}.1") == "mine\n"


def _seed(tmp_path: Path, days_ago: int, suffix: str = "") -> Path:
    path = tmp_path / f"app.log.{_today() - timedelta(days=days_ago)}{suffix}"
    path.write_text("old\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("retention_days", [3, 7])
def test_retention_keeps_exactly_n_days_and_deletes_older_including_parts(tmp_path, retention_days):
    edge = _seed(tmp_path, retention_days)
    edge_part = _seed(tmp_path, retention_days, ".2")
    older = _seed(tmp_path, retention_days + 1)
    older_part = _seed(tmp_path, retention_days + 1, ".1")
    oldest = _seed(tmp_path, retention_days + 30, ".7")
    unrelated = tmp_path / "other.log.2000-01-01"
    unrelated.write_text("keep\n", encoding="utf-8")

    handler = _handler(tmp_path / "app.log", max_bytes=10, retention_days=retention_days)
    try:
        _emit(handler, "trigger-1")
        _emit(handler, "trigger-2")  # 크기 초과 → 교체 시점에 보관 정리
    finally:
        handler.close()

    assert edge.exists() and edge_part.exists(), "정확히 N일 전 파일은 남아야 한다"
    assert not older.exists() and not older_part.exists() and not oldest.exists()
    assert unrelated.exists(), "다른 파일은 건드리지 않는다"


def test_retention_zero_deletes_nothing(tmp_path):
    ancient = _seed(tmp_path, 400)
    ancient_part = _seed(tmp_path, 400, ".3")
    handler = _handler(tmp_path / "app.log", max_bytes=10, retention_days=0)
    try:
        _emit(handler, "trigger-1")
        _emit(handler, "trigger-2")
    finally:
        handler.close()

    assert ancient.exists() and ancient_part.exists()
