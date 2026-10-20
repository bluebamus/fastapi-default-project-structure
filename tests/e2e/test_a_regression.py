"""L1 — 회귀: 기존 스위트 전부를 **이 스택 위에서** 다시 돈다(``not mysql`` + ``mysql``).

- ``not mysql``: Redis 가 필요한 실제 uvicorn 수명 테스트가 이 스택의 Redis(16391)에 붙는다(W0 — 대상 명시).
- ``mysql``: 이 스택의 primary(13321)에 기존 하네스가 쓰는 전용 DB·계정(``fastapi_test``)을 만들어 붙는다.
  그 DB 만 지우고 만든다 — E2E 스키마(``fastapi_e2e``)와 섞이지 않는다.

둘 다 실패·skip·xfail 0 이어야 한다. 결과 수치는 인벤토리 표의 기록(NOTES)에 남는다.
"""

from __future__ import annotations

import os
import re
import subprocess  # noqa: S404 - 기존 스위트를 별도 pytest 프로세스로 돈다
import sys

import pytest

from tests.e2e.stack import INHERITED_ENV, PORTS, ROOT
from tests.e2e.support import NOTES

pytestmark = pytest.mark.e2e

ANSI = re.compile(r"\x1b\[[0-9;]*m")
SUMMARY = re.compile(r"^=+ .+ in [0-9.]+s")


def _pytest(stack, marker: str, *extra: str, **env: str) -> str:
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            marker,
            "-q",
            "-rsxX",
            "-p",
            "no:cacheprovider",
            *extra,
        ],
        cwd=ROOT,
        # 앱 설정 변수는 물려주지 않는다 — CI gate·mysql job 과 같은 조건(pytest-env 가 ENV=test 를 준다).
        env={k: v for k, v in os.environ.items() if k.upper() in INHERITED_ENV} | env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    out = ANSI.sub("", done.stdout + done.stderr)
    (stack.run_dir / f"regression-{marker.replace(' ', '_')}.txt").write_text(out, encoding="utf-8")
    # 요약 줄을 찾는다 — 마지막 줄이 아닐 수 있다(로그 listener 의 종료 줄이 뒤에 붙는다, Linux 실측).
    summaries = [line for line in out.splitlines() if SUMMARY.match(line)]
    summary = summaries[-1] if summaries else ""
    assert done.returncode == 0, out[-4000:]
    assert not re.search(r"\d+ (failed|error|errors|skipped|xfailed|xpassed)\b", summary), summary
    NOTES[f"L1 회귀 · -m {marker!r}"] = summary
    return summary


def test_unit_suite_passes_against_this_stacks_redis(stack):
    summary = _pytest(stack, "not mysql", REDIS_HOST="127.0.0.1", REDIS_PORT=str(PORTS["redis"]))
    assert "passed" in summary


def test_mysql_suite_passes_against_this_stacks_primary(stack):
    stack.sql(
        "mysql-primary",
        "CREATE DATABASE IF NOT EXISTS fastapi_test;"
        "CREATE USER IF NOT EXISTS 'fastapi_test'@'%' IDENTIFIED BY 'fastapi_test_password';"
        "GRANT ALL ON fastapi_test.* TO 'fastapi_test'@'%';",
    )
    summary = _pytest(
        stack, "mysql", "--mysql-required", MYSQL_TEST_PORT=str(PORTS["mysql-primary"])
    )
    assert "passed" in summary
