"""DB 세션 Dependency 명명 계약 — TX-005.

SQLAlchemy 세션을 제공하는 이름에 ``db_session`` 을 넣는 이유는 사용자 세션·HTTP
세션과 구분하기 위해서다. 옛 이름은 전환 기간의 deprecated 별칭이며, **같은 함수
객체**여야 한다 — 별도 래퍼로 감싸면 FastAPI 의존성 캐시 키(callable 자체)가 달라져
한 요청에서 세션이 둘로 갈라진다.
"""

from __future__ import annotations

import inspect

from app.core.db import session as db_session_module

CANONICAL_DEPENDENCIES = (
    "get_read_only_db_session",
    "get_writer_db_session",
    "get_routed_db_session",
    "get_background_db_session",
)

DEPRECATED_ALIASES = {
    "get_session": "get_routed_db_session",
    "get_read_session": "get_read_only_db_session",
    "get_write_session": "get_writer_db_session",
    "get_background_session": "get_background_db_session",
    "background_session": "background_db_session",
}


def test_canonical_dependencies_exist():
    """정식 이름 4종이 모두 존재하고 async generator 함수여야 한다."""
    for name in CANONICAL_DEPENDENCIES:
        dependency = getattr(db_session_module, name, None)
        assert dependency is not None, f"정식 Dependency {name} 이 없다"
        assert inspect.isasyncgenfunction(
            dependency
        ), f"{name} 은 요청 종료 시 세션을 닫아야 하므로 async generator 여야 한다"


def test_background_context_manager_is_renamed():
    """요청 밖 컨텍스트도 db_session 명명을 따른다."""
    assert hasattr(db_session_module, "background_db_session")


def test_deprecated_aliases_are_the_same_object():
    """옛 이름은 새 이름과 **동일한 객체**여야 한다.

    래퍼로 감싸면 Depends 캐시 키가 갈라져, 전환 중인 라우트에서 한 요청에 세션이
    두 개 열린다(커밋 주체가 둘이 되는 사고로 이어진다).
    """
    for old, new in DEPRECATED_ALIASES.items():
        assert getattr(db_session_module, old) is getattr(
            db_session_module, new
        ), f"{old} 이 {new} 와 다른 객체다 — Depends 캐시 키가 갈라진다"


def test_application_code_uses_canonical_names_only():
    """애플리케이션 코드(정의 파일 제외)에 옛 이름이 남아 있지 않아야 한다.

    옛 이름을 제거하는 마지막 단계(MIG-002 단계 9)의 선행 조건이다.
    """
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    definition_file = repo_root / "app" / "core" / "db" / "session.py"
    skip = {
        ".venv",
        ".mypy_cache",
        ".mypy_tmp",
        ".pytest_cache",
        ".pytest_tmp",
        ".ruff_cache",
        "__pycache__",
    }

    offenders: list[str] = []
    for path in (repo_root / "app").rglob("*.py"):
        if skip & set(path.parts) or path == definition_file:
            continue
        text = path.read_text(encoding="utf-8")
        for old in DEPRECATED_ALIASES:
            # get_session 은 get_read_session 의 부분 문자열이므로 경계를 본다.
            import re

            if re.search(rf"\b{old}\b", text):
                offenders.append(f"{path.relative_to(repo_root).as_posix()}: {old}")

    assert not offenders, (
        "애플리케이션 코드에 deprecated 세션 이름이 남아 있습니다:\n  "
        + "\n  ".join(sorted(offenders))
    )
