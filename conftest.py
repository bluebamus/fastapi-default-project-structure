"""pytest 전역 옵션.

여기 있어야 하는 이유: ``pytest_addoption`` 은 **루트 conftest** 에서만 인식된다.
초기 인자 파싱 단계에 로드되기 때문이며, ``tests/`` 안으로 옮기면 옵션 자체가
없는 것으로 취급된다.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

# Python 3.12 부터 sqlite3 의 **기본** date/datetime 어댑터가 폐기됐다. aiosqlite 를
# 쓰는 테스트가 `datetime` 을 그대로 바인딩하면 `DeprecationWarning` 이 쏟아진다.
# 서드파티 버그가 아니라 "어댑터를 직접 등록하라" 는 요구라서, 여기서 등록한다.
# 형식은 폐기된 기본 어댑터와 **같게** 맞춘다(datetime 은 공백 구분자) — 기존 데이터·
# 문자열 비교의 의미가 바뀌지 않도록. 복원(converter)은 등록하지 않는다: 이 저장소는
# `detect_types` 를 쓰지 않아 호출될 일이 없고, 타입 복원은 SQLAlchemy 가 맡는다.
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
sqlite3.register_adapter(date, lambda value: value.isoformat())


def pytest_addoption(parser: pytest.Parser) -> None:
    """``--mysql-required`` — MySQL 통합 테스트를 skip 으로 넘기지 않는다.

    기본 동작은 skip 이다. MySQL 없이도 단위 테스트를 돌릴 수 있어야 하기 때문이다.
    문제는 **skip 이 초록으로 보인다**는 것이다. CI 에서 컨테이너가 안 떴는데 결과만
    보면 통과처럼 읽히고, "돌았는데 통과" 와 "안 돌았다" 가 구분되지 않는다
    (residual-risk **R-003**).

    이 옵션을 주면 DB 에 닿지 못할 때 skip 대신 **실패**한다. 통합 검증을 근거로
    쓰는 자리(릴리스 게이트·수렴 판정)에서는 항상 이걸 붙인다::

        pytest -m mysql --mysql-required
    """
    parser.addoption(
        "--mysql-required",
        action="store_true",
        default=False,
        help="MySQL 통합 테스트를 skip 하지 않는다. DB 에 닿지 못하면 실패시킨다.",
    )
