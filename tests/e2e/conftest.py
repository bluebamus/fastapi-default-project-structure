"""E2E 스위트 하네스 (integration-e2e W2) — ``-m e2e`` 로만 돈다.

    uv run python -m pytest -m e2e

마커식에 ``e2e`` 가 없으면 이 디렉터리의 테스트는 **deselect** 된다(skip 이 아니다). 기본 실행·
CI gate job(``-m "not mysql"``)·review_gate 는 Docker 없이 돌아야 하고, 이 스위트는 Docker 스택을
띄운다. CI 는 별도 job ``e2e`` 가 ``-m e2e`` 로 돌린다.

스택은 세션에 하나다(``stack``). 테스트는 파일 이름 순서로 돈다 — 장애 주입(L5)·재기동(L4·L6)은
끝나면 스택을 원래 상태로 되돌리고, 인벤토리 대조와 비밀값 grep 은 마지막 파일(test_zz_*)이다.
"""

from __future__ import annotations

import datetime as dt
import functools

import pytest

from tests.e2e.stack import ROOT, Stack, StackError
from tests.e2e.support import record


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if "e2e" in (config.option.markexpr or ""):
        return
    e2e = [item for item in items if item.get_closest_marker("e2e")]
    if e2e:
        config.hook.pytest_deselected(items=e2e)
        items[:] = [item for item in items if not item.get_closest_marker("e2e")]


@pytest.fixture(scope="session")
def stack():
    run_dir = ROOT / ".pytest_tmp" / "e2e" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        stack = Stack(run_dir)
        stack.preflight()
    except StackError as exc:
        pytest.exit(f"E2E 스택을 세울 수 없다: {exc}", returncode=3)
    try:
        stack.up()
        stack.start_app()
        stack.start_worker()
    except StackError as exc:
        stack.down()
        pytest.exit(f"E2E 스택 기동 실패: {exc}", returncode=3)
    yield stack
    stack.down()


@pytest.fixture
def cover(request):
    """``cover(kind, item, cell, na=None)`` — 이 테스트가 인벤토리의 한 칸을 실행했다고 적는다."""
    return functools.partial(record, request.node.nodeid)
