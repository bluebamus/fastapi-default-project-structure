"""현행 가이드(docs/guides)와 README 가 가리키는 파일이 실제로 존재하는지 본다.

README 는 설치·실행 절차(옛 QUICKSTART)를 담으므로 가이드와 같은 규칙으로 검사한다.

가이드는 사람이 **따라 하는** 문서라 틀리면 가장 비싸다. 코드 테스트는 문서를
import 하지 않으므로, 파일을 옮기거나 지워도 가이드만 조용히 썩는다 — 2026-09-17
가이드 대조에서 실제로 여러 건이 나왔다.

규칙은 백틱(HTML 은 ``<code>``)으로 감싼, 슬래시가 있는 경로만 본다. 문서는
``db/session.py`` 처럼 앞을 생략해 쓰므로 **접미사 일치**로 판정한다.
``## N. 변경 이력`` 절은 당시의 사실이라 지운 파일이 나오는 것이 정상이므로 뺀다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDES = sorted((REPO_ROOT / "docs" / "guides").glob("*.md")) + sorted(
    (REPO_ROOT / "docs" / "guides").glob("*.html")
)
#: 경로 검사 대상 — 가이드 전부 + 루트 README.
CHECKED_DOCS = [REPO_ROOT / "README.md", *GUIDES]

_PATH = re.compile(
    r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.(?:py|ya?ml|toml|json|ini|cfg|txt|md|html))`"
)
_HTML_CODE = re.compile(r"<code>([^<]+)</code>")
_HISTORY = re.compile(r"^(#{1,6}) [^\n]*변경 이력[^\n]*\n.*?(?=^#{1,6} |\Z)", re.M | re.S)
_RELATIVE_PREFIX = re.compile(r"^(?:\.\.?/)+")
_IGNORED_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}

#: 의도적으로 실재하지 않는 경로 — 이유를 함께 적는다.
ALLOWED_MISSING = {
    "app/apps.py",  # 제거된 중앙 등록 파일 — 과거 배선을 설명하는 부정 서술
    "inventory/__init__.py",  # DEVELOPMENT: 새 기능을 만드는 가상 예시
}


def missing_paths(text: str, known: list[str], *, html: bool) -> list[str]:
    if html:
        text = _HTML_CODE.sub(r"`\1`", text)
    text = _HISTORY.sub("", text)
    missing = []
    for reference in sorted(set(_PATH.findall(text))):
        needle = _RELATIVE_PREFIX.sub("", reference)
        if reference not in ALLOWED_MISSING and not any(p.endswith(needle) for p in known):
            missing.append(reference)
    return missing


def _repo_files() -> list[str]:
    return [
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in REPO_ROOT.rglob("*")
        if path.is_file() and not _IGNORED_DIRS & set(path.parts)
    ]


def test_rule_catches_missing_and_skips_history():
    """규칙 자체가 헛돌지 않는지 — 본문의 옛 경로는 잡고, 이력·상대 표기는 통과시킨다."""
    known = ["docs/crp/groups/a/charter.md"]
    doc = "`app/gone.py` `../crp/groups/a/charter.md`\n## 8. 변경 이력\n`app/old.py`\n"

    assert missing_paths(doc, known, html=False) == ["app/gone.py"]
    assert missing_paths("<code>app/gone.py</code>", known, html=True) == ["app/gone.py"]


def test_guides_exist():
    assert GUIDES, "docs/guides 가 비어 있다 — 검사가 아무것도 보지 않는다"


@pytest.mark.parametrize("guide", CHECKED_DOCS, ids=lambda p: p.name)
def test_guide_paths_exist(guide: Path):
    known = _repo_files()
    text = guide.read_text(encoding="utf-8")

    assert missing_paths(text, known, html=guide.suffix == ".html") == []
