"""CI 의 의존성 설치는 락이 어긋나면 실패해야 한다 (service-hardening ADR-003).

`uv sync --frozen` 은 `uv.lock` 을 **검사하지 않고** 그대로 쓴다. `pyproject.toml` 을 고치고
락 갱신을 잊은 커밋도 CI 가 초록으로 통과시켰고, `ci.yml` 주석은 반대로 "어긋나면 실패한다" 고
적고 있었다. `--locked` 는 락이 pyproject 와 어긋나면 설치 전에 실패한다.

주석 줄은 보지 않는다 — 왜 `--frozen` 을 쓰지 않는지 설명하는 주석은 남아도 된다.
"""

from __future__ import annotations

import re
from pathlib import Path

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

_SYNC = re.compile(r"\buv sync\b")


def _sync_commands(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if _SYNC.search(line) and not line.lstrip().startswith("#")
    ]


def test_every_uv_sync_is_locked() -> None:
    commands = _sync_commands(CI.read_text(encoding="utf-8"))

    # gate·mysql 두 job 이 각자 설치한다. 0건이면 검사가 헛돈다.
    assert len(commands) >= 2, commands
    assert all("--locked" in c and "--frozen" not in c for c in commands), commands


def test_rule_catches_frozen() -> None:
    """규칙 자체가 헛돌지 않는지 — `--frozen` 실행 줄은 잡고 주석은 넘긴다."""
    text = "      # --frozen 은 쓰지 않는다\n        run: uv sync --frozen\n"

    assert _sync_commands(text) == ["run: uv sync --frozen"]
