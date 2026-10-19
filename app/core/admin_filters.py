"""관리 화면 목록의 날짜 필터 — ``LocalDateFilter`` (security-ops-hardening ADR-005).

sqladmin 의 ``OperationColumnFilter`` 는 ``UTCDateTime``(TypeDecorator)을 날짜형으로 보지 못해 입력 문자열을
그대로 바인딩하고, ``UTCDateTime`` 이 그것을 거부해 목록이 500 이 됐다. 이 필터는 sqladmin 0.32 의 연산 필터
프로토콜(``has_operator``·``parameter_name``·``get_operation_options_for_model``·``get_filtered_query``)을
그대로 따르되, 입력 날짜(``YYYY-MM-DD``, 업무 시간대 ``TIME_ZONE``)의 로컬 자정을 UTC aware 시각으로 바꿔
범위 조건으로 질의한다.

- 연산: ``on``(그날 하루), ``on_or_after``(그날 0시 이후, 포함), ``before``(그날 0시 이전, 미포함).
- 형식이 틀린 입력·모르는 연산은 필터를 적용하지 않고 WARNING 로그만 남긴다(500 이 아니다).
- 빠른 선택(오늘·최근 7일·최근 30일)은 ``quick_ranges()`` 가 같은 연산·값으로 만든다.

sqladmin 을 import 하지 않는다 — 관리 화면을 끈 앱(``ADMIN_DISABLED=true``)에서도 이 모듈은 가볍다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select

from app.utils.logs import get_logger
from config import timezone_settings

logger = get_logger("admin_filters")

DATE_FORMAT = "%Y-%m-%d"
OPERATIONS: list[tuple[str, str]] = [
    ("on", "같은 날"),
    ("on_or_after", "이후(포함)"),
    ("before", "이전(미포함)"),
]


class LocalDateFilter:
    """``created_at`` 같은 UTC 저장 시각 컬럼을 로컬 날짜로 거르는 sqladmin 연산 필터."""

    has_operator = True
    template = "sqladmin/filters/local_date_filter.html"

    def __init__(
        self,
        column: Any,
        title: str | None = None,
        parameter_name: str | None = None,
        *,
        tz: ZoneInfo | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """
        Args:
            column: 모델 컬럼 속성(예: ``Post.created_at``).
            tz: 날짜를 해석할 시간대. 생략하면 ``TIME_ZONE``.
            clock: 빠른 선택의 "오늘" 기준 시각(테스트용). 생략하면 ``timezone_settings.utc_now``.
        """
        self.column = column
        self.parameter_name = parameter_name or column.key
        self.title = title or "생성 날짜"
        self._tz = tz or timezone_settings.tz
        self._clock = clock or timezone_settings.utc_now

    def get_operation_options_for_model(self, model: Any) -> list[tuple[str, str]]:
        return list(OPERATIONS)

    async def lookups(self, request: Any, model: Any, run_query: Any) -> list[tuple[str, str]]:
        return []  # 연산 필터는 쓰지 않는다(sqladmin 프로토콜 자리).

    def day_start(self, day: date) -> datetime:
        """로컬 날짜 ``day`` 의 0시를 UTC aware 시각으로."""
        return datetime.combine(day, time(), tzinfo=self._tz).astimezone(UTC)

    def quick_ranges(self) -> list[tuple[str, str, str]]:
        """(이름, 연산, 날짜) — 오늘·최근 7일·최근 30일(오늘 포함)."""
        today = self._clock().astimezone(self._tz).date()
        return [
            ("오늘", "on", today.strftime(DATE_FORMAT)),
            ("최근 7일", "on_or_after", (today - timedelta(days=6)).strftime(DATE_FORMAT)),
            ("최근 30일", "on_or_after", (today - timedelta(days=29)).strftime(DATE_FORMAT)),
        ]

    async def get_filtered_query(
        self, query: Select[Any], operation: str, value: Any, model: Any
    ) -> Select[Any]:
        try:
            day = datetime.strptime(str(value).strip(), DATE_FORMAT).date()
            start = self.day_start(day)
            end = self.day_start(day + timedelta(days=1))
        except (ValueError, OverflowError):  # 형식 오류, 0001-01-01·9999-12-31 경계 넘침
            logger.warning(
                "[admin] 날짜 필터 입력 무시: %s=%r", self.parameter_name, str(value)[:32]
            )
            return query
        if operation == "on":
            return query.filter(self.column >= start, self.column < end)
        if operation == "on_or_after":
            return query.filter(self.column >= start)
        if operation == "before":
            return query.filter(self.column < start)
        logger.warning("[admin] 날짜 필터 연산 무시: %s_op=%r", self.parameter_name, operation[:32])
        return query
