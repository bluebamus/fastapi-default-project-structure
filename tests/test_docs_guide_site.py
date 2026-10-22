"""HTML 가이드 사이트(docs/guides/**/*.html)의 내용 계약 — 표가 코드와 같은 사실을 말하는가.

링크·경로 존재는 ``tests/test_docs_guides.py`` 가 본다. 여기서는 생성 문서가 코드와 어긋났던
지점(docs-guide-site 그룹)만 고정한다:

1. API 레퍼런스 표의 (메서드, 경로, 접근 수준) = ``app.openapi()`` operation × ``AccessPolicyGuard`` 판정
2. 설정 레퍼런스에 Settings 필드가 전부 있다
3. Mermaid 는 고정 버전 하나만 쓴다
4. 허브가 모든 HTML 가이드를 링크하고, 스타일시트 경로가 실재한다
"""

from __future__ import annotations

import inspect
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

import config
from app.core.security.access import AccessPolicyGuard
from main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDES = REPO_ROOT / "docs" / "guides"
HTML_GUIDES = sorted(GUIDES.rglob("*.html"))
MERMAID_VERSION = "11.12.0"


class _Page(HTMLParser):
    """표(헤더 행 + 본문 행의 셀 텍스트)와 ``<a href>``·``<link href>`` 를 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.anchors: list[str] = []
        self.stylesheets: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.tables[-1].append([])
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "a" and values.get("href"):
            self.anchors.append(values["href"] or "")
        elif tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(values.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self.tables:
            self.tables[-1][-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _page(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def test_api_reference_matches_openapi_and_access_policy():
    """표의 행 집합이 실제 operation × 접근 수준과 같다 — 빠진 행·없는 행·틀린 수준 모두 실패."""
    documented_ops = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    guard = AccessPolicyGuard()
    expected = set()
    for label, context in guard.routes(app):
        methods, path = label.split(" ", 1)
        for method in methods.split(","):
            if (method, path) in documented_ops:
                (level,) = guard.levels(context.dependant)
                expected.add((method, path, str(level)))
    assert {(m, p) for m, p, _ in expected} == documented_ops

    tables = [
        t for t in _page(GUIDES / "reference" / "api.html").tables if t and "접근 수준" in t[0]
    ]
    assert len(tables) == 1, "api.html 에 '접근 수준' 열이 있는 표가 정확히 하나 있어야 한다"
    header, *rows = tables[0]
    columns = [header.index(name) for name in ("메서드", "경로", "접근 수준")]
    actual = {tuple(row[i] for i in columns) for row in rows}

    assert actual == expected


def test_configuration_reference_lists_every_settings_field():
    settings_classes = [
        cls
        for _, cls in inspect.getmembers(config, inspect.isclass)
        if issubclass(cls, BaseSettings) and cls is not BaseSettings
    ]
    fields = {name for cls in settings_classes for name in cls.model_fields}
    assert len(fields) > 60, "Settings 수집이 헛돈다"
    text = (GUIDES / "reference" / "configuration.html").read_text(encoding="utf-8")

    missing = sorted(name for name in fields if f"<code>{name}</code>" not in text)

    assert not missing, f"configuration.html 에 없는 설정: {missing}"


def test_mermaid_is_pinned_to_one_version():
    versions = {
        path.relative_to(REPO_ROOT).as_posix(): set(
            re.findall(r"mermaid@([^/\"']+)", path.read_text(encoding="utf-8"))
        )
        for path in HTML_GUIDES
    }
    wrong = {name: found for name, found in versions.items() if found - {MERMAID_VERSION}}

    assert not wrong, f"mermaid@{MERMAID_VERSION} 이 아닌 스크립트: {wrong}"


def test_hub_links_every_html_guide():
    hub = GUIDES / "index.html"
    linked = {(hub.parent / href.split("#", 1)[0]).resolve() for href in _page(hub).anchors}
    unlinked = [
        path.relative_to(GUIDES).as_posix()
        for path in HTML_GUIDES
        if path != hub and path.resolve() not in linked
    ]

    assert not unlinked, f"허브가 링크하지 않는 가이드: {unlinked}"


@pytest.mark.parametrize("guide", HTML_GUIDES, ids=lambda p: p.relative_to(GUIDES).as_posix())
def test_stylesheet_links_exist(guide: Path):
    broken = [href for href in _page(guide).stylesheets if not (guide.parent / href).is_file()]

    assert not broken, f"없는 스타일시트: {broken}"
