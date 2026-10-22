"""HTML 가이드 사이트(docs/guides/**/*.html)의 내용 계약 — 표가 코드와 같은 사실을 말하는가.

링크·경로 존재는 ``tests/test_docs_guides.py`` 가 본다. 여기서는 생성 문서가 코드와 어긋났던
지점(docs-guide-site 그룹)만 고정한다:

1. API 레퍼런스 표의 (메서드, 경로, 접근 수준) = ``app.openapi()`` operation × ``AccessPolicyGuard`` 판정,
   기능별 문서(features/*.html)의 API 표는 그 부분집합(같은 접근 수준)
2. 설정 레퍼런스에 Settings 필드가 전부 있고, 각 행의 클래스·코드 기본값이 코드와 같다
3. Mermaid 도식이 있는 페이지는 고정 URL 하나로 불러온다(고정 삭제·다른 버전 모두 실패)
4. 허브가 모든 HTML 가이드를 링크하고, 스타일시트 경로가 실재한다
"""

from __future__ import annotations

import inspect
import json
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
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"
#: 코드 기본값을 그대로 옮기지 않고 말로 적은 행 — 값이 길거나(포맷·소개문) 예시 비밀 값이다.
DESCRIBED_DEFAULTS = {
    "DESCRIPTION": "소개 Markdown(코드 기본값)",
    "LOG_CONSOLE_FORMAT": "프로젝트 포맷",
    "LOG_FILE_FORMAT": "프로젝트 포맷",
    "ACCESS_TOKEN_SECRET_KEY": "예시 값(교체 필수)",
    "REFRESH_TOKEN_SECRET_KEY": "예시 값(교체 필수)",
    "SESSION_SECRET_KEY": "예시 값(교체 필수)",
}


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


def _expected_api_rows() -> set[tuple[str, str, str]]:
    """실제 (메서드, 경로, 접근 수준) — openapi operation 마다 가드가 판정한 수준."""
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
    return expected


def _api_rows(path: Path) -> list[tuple[str, ...]]:
    """'메서드'·'경로'·'접근 수준' 열이 있는 표의 행을 그 세 값으로 모은다."""
    rows = []
    for header, *body in (t for t in _page(path).tables if t):
        if {"메서드", "경로", "접근 수준"} <= set(header):
            columns = [header.index(name) for name in ("메서드", "경로", "접근 수준")]
            rows += [tuple(row[i] for i in columns) for row in body]
    return rows


def test_api_reference_matches_openapi_and_access_policy():
    """표의 행 집합이 실제 operation × 접근 수준과 같다 — 빠진 행·없는 행·틀린 수준 모두 실패."""
    actual = _api_rows(GUIDES / "reference" / "api.html")

    assert len(actual) == len(set(actual)), "api.html 에 같은 행이 두 번 있다"
    assert set(actual) == _expected_api_rows()


def test_feature_api_tables_are_subsets_of_the_reference():
    """기능별 문서의 API 표도 실제 operation × 접근 수준만 담는다(A-N5·X-1)."""
    expected = _expected_api_rows()
    rows = [
        (path.name, row)
        for path in sorted((GUIDES / "features").glob("*.html"))
        for row in _api_rows(path)
    ]
    assert len(rows) > 20, "기능별 API 표 수집이 헛돈다"

    wrong = [(name, row) for name, row in rows if row not in expected]

    assert not wrong, f"코드와 다른 기능별 API 행(메서드, 경로, 접근 수준): {wrong}"


def _settings_fields() -> dict[str, tuple[str, object]]:
    return {
        name: (cls.__name__, field.get_default(call_default_factory=True))
        for _, cls in inspect.getmembers(config, inspect.isclass)
        if issubclass(cls, BaseSettings) and cls is not BaseSettings
        for name, field in cls.model_fields.items()
    }


def _default_cell(name: str, value: object) -> str:
    """설정 표 '코드 기본값' 칸에 적혀야 할 글자."""
    if name in DESCRIBED_DEFAULTS:
        return DESCRIBED_DEFAULTS[name]
    if value is None:
        return "미설정"
    if value == "":
        return "빈 값"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def test_default_cell_format():
    """기본값 칸 규칙 자체가 헛돌지 않는지."""
    assert _default_cell("X", None) == "미설정"
    assert _default_cell("X", "") == "빈 값"
    assert _default_cell("X", True) == "true"
    assert _default_cell("X", ["/a", "/b"]) == '["/a", "/b"]'
    assert _default_cell("X", 3306) == "3306"


def test_configuration_reference_lists_every_settings_field():
    fields = _settings_fields()
    assert len(fields) > 60, "Settings 수집이 헛돈다"
    text = (GUIDES / "reference" / "configuration.html").read_text(encoding="utf-8")

    missing = sorted(name for name in fields if f"<code>{name}</code>" not in text)

    assert not missing, f"configuration.html 에 없는 설정: {missing}"


def test_configuration_rows_match_class_and_code_default():
    """설정 표의 클래스·코드 기본값이 코드와 같다 — 기본값만 바뀐 행도 실패(P-N5)."""
    fields = _settings_fields()
    tables = [
        t
        for t in _page(GUIDES / "reference" / "configuration.html").tables
        if t and "코드 기본값" in t[0]
    ]
    assert len(tables) == 1, "configuration.html 에 '코드 기본값' 열이 있는 표가 하나 있어야 한다"
    header, *rows = tables[0]
    name_i, cls_i, default_i = (header.index(c) for c in ("설정", "클래스", "코드 기본값"))

    wrong = [
        (row[name_i], row[cls_i], row[default_i])
        for row in rows
        if row[name_i] in fields
        and (row[cls_i], row[default_i])
        != (fields[row[name_i]][0], _default_cell(row[name_i], fields[row[name_i]][1]))
    ]

    assert not wrong, f"코드와 다른 설정 행(이름, 클래스, 기본값): {wrong}"


@pytest.mark.parametrize("guide", HTML_GUIDES, ids=lambda p: p.relative_to(GUIDES).as_posix())
def test_mermaid_pages_load_the_pinned_script(guide: Path):
    """도식이 있으면 고정 URL 을 정확히 한 번 — 고정을 지우거나 다른 버전을 섞어도 실패(D-N6)."""
    text = guide.read_text(encoding="utf-8")
    has_diagram = 'class="mermaid' in text

    assert text.count("mermaid@") == text.count(MERMAID_URL) == (1 if has_diagram else 0)


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
