"""계층 규칙 — core 는 기능을 모르고, 기능끼리는 문서화된 auth→user 만 import 한다 (service-hardening C-2).

``PasswordHasher`` 를 user 기능도 쓰게 되면서 이 규칙이 실제로 시험대에 올랐다 — auth 의 해시기를 user 가
import 하는 대신 core 로 올렸다(ADR-026). 같은 지름길이 다시 생기면 여기서 막힌다. AST 로 import 문만 본다.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "app" / "features"
# (import 하는 기능, import 되는 기능) — 인증이 사용자 엔티티를 읽는 횡단 관심사라 허용한다.
ALLOWED_FEATURE_EDGES = {("auth", "user")}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _feature_of(module: str) -> str | None:
    parts = module.split(".")
    if parts[:2] == ["app", "features"] and len(parts) > 2:
        return parts[2]
    return None


def test_core_does_not_import_features():
    offenders = sorted(
        f"{path.relative_to(ROOT).as_posix()} -> {module}"
        for path in (ROOT / "app" / "core").rglob("*.py")
        for module in _imported_modules(path)
        if _feature_of(module) is not None
    )
    assert not offenders, f"core 가 기능을 import 한다: {offenders}"


def test_features_import_each_other_only_through_allowed_edges():
    offenders = []
    for path in FEATURES.rglob("*.py"):
        rel = path.relative_to(FEATURES)
        if len(rel.parts) < 2 or "tests" in rel.parts:
            continue
        owner = rel.parts[0]
        for module in _imported_modules(path):
            target = _feature_of(module)
            if target and target != owner and (owner, target) not in ALLOWED_FEATURE_EDGES:
                offenders.append(f"{path.relative_to(ROOT).as_posix()} -> {module}")
    assert not offenders, f"기능끼리 import 한다(core 로 올릴 것): {sorted(offenders)}"


def test_checks_are_not_vacuous():
    assert any(True for _ in (ROOT / "app" / "core").rglob("*.py"))
    assert len(list(FEATURES.rglob("*.py"))) > 50
