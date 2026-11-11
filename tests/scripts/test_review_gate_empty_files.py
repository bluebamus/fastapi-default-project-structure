"""게이트는 git 이 추적하는 빈 ``.py`` 를 잡는다 — ``__init__.py`` 와 추적되지 않는 파일은 뺀다."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from review_gate import empty_python_files  # noqa: E402


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


def test_repository_has_no_empty_modules() -> None:
    assert empty_python_files() == []
