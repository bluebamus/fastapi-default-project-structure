"""루트 conftest — 모든 테스트에 앞서 sqlite3 어댑터를 등록한다."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

# Python 3.12 부터 sqlite3 의 **기본** date/datetime 어댑터가 폐기됐다. aiosqlite 를
# 쓰는 테스트가 `datetime` 을 그대로 바인딩하면 `DeprecationWarning` 이 쏟아진다.
# 서드파티 버그가 아니라 "어댑터를 직접 등록하라" 는 요구라서, 여기서 등록한다.
# 형식은 폐기된 기본 어댑터와 **같게** 맞춘다(datetime 은 공백 구분자) — 기존 데이터·
# 문자열 비교의 의미가 바뀌지 않도록. 복원(converter)은 등록하지 않는다: 이 저장소는
# `detect_types` 를 쓰지 않아 호출될 일이 없고, 타입 복원은 SQLAlchemy 가 맡는다.
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
sqlite3.register_adapter(date, lambda value: value.isoformat())
