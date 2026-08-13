"""DB 세션 Dependency 명명 계약 — TX-005 / MIG-002 단계 9 완료.

SQLAlchemy 세션을 제공하는 이름에 ``db_session`` 을 넣는 이유는 사용자 세션·HTTP
세션과 구분하기 위해서다.

전환 기간에 두었던 옛 이름은 **제거됐다**. 이 파일은 이제 두 가지를 지킨다 —
정식 이름이 존재할 것, 그리고 옛 이름이 되살아나지 않을 것. 옛 이름이 다시 생기면
"어느 쪽을 써야 하나"가 다시 열리고, 래퍼로 되살릴 경우 FastAPI 의존성 캐시 키
(callable 자체)가 갈라져 한 요청에서 세션이 둘로 열린다.
"""

from __future__ import annotations

import inspect
import pathlib
import re

from app.core.db import session as db_session_module

CANONICAL_DEPENDENCIES = (
    "get_read_only_db_session",
    "get_writer_db_session",
    "get_routed_db_session",
    "get_background_db_session",
)

# 제거된 옛 이름. 되살아나면 안 된다.
REMOVED_ALIASES = (
    "get_session",
    "get_read_session",
    "get_write_session",
    "get_background_session",
    "background_session",
)


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


def test_removed_aliases_are_gone():
    """옛 이름은 모듈에서 제거된 상태여야 한다 (MIG-002 단계 9)."""
    survivors = [name for name in REMOVED_ALIASES if hasattr(db_session_module, name)]

    assert not survivors, (
        f"제거했어야 할 옛 세션 이름이 남아 있습니다: {survivors}. "
        "정식 이름(get_*_db_session)만 공개합니다."
    )


def test_application_code_uses_canonical_names_only():
    """애플리케이션 코드에 옛 이름이 남아 있지 않아야 한다.

    모듈 속성 검사만으로는 부족하다 — 다른 모듈이 자기 이름으로 별칭을 다시 만들 수 있다.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    skip = {
        ".venv",
        ".mypy_cache",
        ".mypy_tmp",
        ".pytest_cache",
        ".pytest_tmp",
        ".ruff_cache",
        "__pycache__",
    }
    # get_session 은 get_read_session 의 부분 문자열이므로 단어 경계를 본다.
    patterns = {old: re.compile(rf"\b{old}\b") for old in REMOVED_ALIASES}

    offenders: list[str] = []
    for path in (repo_root / "app").rglob("*.py"):
        if skip & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{path.relative_to(repo_root).as_posix()}: {old}"
            for old, pattern in patterns.items()
            if pattern.search(text)
        )

    assert not offenders, "애플리케이션 코드에 제거된 세션 이름이 남아 있습니다:\n  " + "\n  ".join(
        sorted(offenders)
    )
