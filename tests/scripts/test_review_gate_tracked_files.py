"""게이트의 파일 목록은 git 이 추적하는 파일만 담는다 — `repo_files()` (service-hardening ADR-003).

게이트가 작업 트리를 rglob 으로 훑으면 추적되지 않는 로컬 파일(다른 도구가 떨군 보고서,
임시 스크립트)이 계층·인용 검사에 섞인다. 그러면 같은 커밋이 로컬에서는 빨갛고 CI 에서는
초록이거나 그 반대가 된다. git 을 쓸 수 없는 곳(압축본으로 받은 소스)에서만 rglob 으로 대신한다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from review_gate import repo_files  # noqa: E402


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
