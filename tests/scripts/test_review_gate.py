"""``scripts/review_gate.py`` 의 판정 로직.

- 조용한 skip 거부: pytest 요약에 ``skipped``·``xfailed``·``xpassed``·``deselected`` 가 0 이 아닌 개수로 있으면
  통과가 아니다. pytest 는 파이프로 캡처해도 요약에 ANSI 색상 코드를 섞어 ``[1m3 skipped`` 가 되므로
  ```` 정규식이 깨지기 쉽다 — 그래서 **진짜 출력 모양**(색상 포함)으로 시험한다.
- 파일 목록: git 이 추적하는 파일만 본다. 작업 트리를 훑으면 추적되지 않는 로컬 파일이 판정에 섞여
  로컬과 CI 결과가 달라진다. git 을 쓸 수 없을 때만 rglob 으로 대신한다.
- 빈 ``.py``: 추적되는 내용 없는 모듈을 잡되 ``__init__.py`` 와 추적되지 않는 파일은 뺀다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.review_gate import _forbidden_outcomes, empty_python_files, repo_files

# 실제 pytest 출력 모양(색상 포함).
COLORED_SKIP = (
    "\x1b[33m===== \x1b[32m609 passed\x1b[0m, \x1b[33m\x1b[1m3 skipped\x1b[0m\x1b[33m in 36s\x1b[0m"
)
COLORED_CLEAN = (
    "\x1b[33m===== \x1b[32m612 passed\x1b[0m, \x1b[33m1 warning\x1b[0m\x1b[33m in 32s\x1b[0m"
)


@pytest.mark.parametrize(
    "summary",
    [
        COLORED_SKIP,
        "609 passed, 3 skipped, 1 warning in 28s",
        "5 passed, 2 xfailed",
        "5 passed, 1 xpassed",
        "788 passed, 32 deselected",
    ],
    ids=["colored-skip", "plain-skip", "xfailed", "xpassed", "deselected"],
)
def test_not_run_is_not_a_pass(summary: str) -> None:
    """안 돈 것은 통과가 아니다 — 색상이 섞여도 잡아야 한다."""
    assert _forbidden_outcomes(summary), f"잡히지 않았다: {summary!r}"


@pytest.mark.parametrize(
    "summary",
    [
        COLORED_CLEAN,
        "612 passed, 1 warning in 32s",
        # `0 skipped` 는 정상 출력이다. 이걸 실패로 보면 게이트가 영원히 빨간불이 된다.
        "100 passed, 0 skipped",
        "\x1b[1m0 skipped\x1b[0m",
        "no tests ran",
    ],
    ids=["colored-clean", "plain-clean", "zero-skipped", "colored-zero", "no-tests"],
)
def test_clean_summary_is_not_a_false_positive(summary: str) -> None:
    """반대 방향도 지킨다 — 멀쩡한 요약을 실패로 만들면 게이트를 아무도 안 믿는다."""
    assert _forbidden_outcomes(summary) == [], f"오탐: {summary!r}"


# --- 파일 목록 ---------------------------------------------------------------
def _write(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")
    return path


def test_untracked_files_are_not_listed(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S607
    tracked = _write(tmp_path / "app" / "tracked.py")
    _write(tmp_path / "app" / "untracked.py")
    _write(tmp_path / "app" / "__pycache__" / "cached.py")
    subprocess.run(["git", "add", "app/tracked.py"], cwd=tmp_path, check=True)  # noqa: S607

    assert repo_files("app", ".py", root=tmp_path) == [tracked]


def test_falls_back_to_rglob_without_git(tmp_path: Path, monkeypatch) -> None:
    """git 저장소가 아니면 작업 트리를 본다 — 캐시 디렉터리는 여전히 뺀다."""
    # 임시 디렉터리의 상위가 우연히 git 저장소여도 그것을 찾아 올라가지 않게 막는다.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    first = _write(tmp_path / "app" / "a.py")
    second = _write(tmp_path / "app" / "sub" / "b.py")
    _write(tmp_path / "app" / "__pycache__" / "c.py")
    _write(tmp_path / "app" / "notes.md")

    assert repo_files("app", ".py", root=tmp_path) == [first, second]


def test_root_under_a_skipped_directory_is_still_listed(tmp_path: Path) -> None:
    """게이트는 --basetemp .pytest_tmp 로 돈다 — 루트의 **상위** 경로는 걸러내기 대상이 아니다."""
    root = tmp_path / ".pytest_tmp" / "repo"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)  # noqa: S607
    tracked = _write(root / "app" / "tracked.py")
    _write(root / "app" / "__pycache__" / "cached.py")
    subprocess.run(["git", "add", "-f", "app"], cwd=root, check=True)  # noqa: S607

    assert repo_files("app", ".py", root=root) == [tracked]


# --- 빈 .py -------------------------------------------------------------------
def test_only_tracked_empty_modules_are_reported(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S607
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "empty.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "full.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "app" / "untracked.py").write_text("", encoding="utf-8")
    subprocess.run(  # noqa: S607
        ["git", "add", "app/__init__.py", "app/empty.py", "app/full.py"], cwd=tmp_path, check=True
    )

    assert empty_python_files(tmp_path) == [tmp_path / "app" / "empty.py"]
