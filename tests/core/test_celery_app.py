"""중앙 Celery 앱 계약 — service-hardening ADR-012 (F-018).

태스크는 기능별 ``tasks.py`` 에 있고, 워커의 include 는 모델 등록과 같은 기능 패키지 탐색
(``models_registry.iter_task_modules``)이 만든다. 중앙 패키지(app/celery)가 기능을 import 하면
기능 하나를 지울 때 워커 전체가 import 오류로 죽는다.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import sys

import pytest

import app.features
from app.core.db import models_registry

CELERY_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "celery"


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")
    assert list(celery_app.conf.include) == models_registry.iter_task_modules()
    assert "app.features.home.tasks" in celery_app.conf.include


def test_include_has_no_central_task_module():
    """중앙 태스크 모듈(기능을 import 하던 ``app.celery.tasks``)이 없고 include 에도 없다."""
    from app.celery.app import celery_app

    assert not (CELERY_DIR / "tasks.py").exists()
    assert all(m.startswith("app.features.") for m in celery_app.conf.include)


def test_celery_package_does_not_import_features():
    """app/celery 의 어떤 모듈도 ``app.features`` 를 import 하지 않는다(AST 검사)."""
    offenders: list[str] = []
    for path in sorted(CELERY_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            offenders += [
                f"{path.name}:{node.lineno} {n}"
                for n in names
                if n == "app.features" or n.startswith("app.features.")
            ]
    assert offenders == []


def test_discovery_lists_home_tasks():
    assert "app.features.home.tasks" in models_registry.iter_task_modules()


@pytest.fixture
def fake_features(tmp_path, monkeypatch):
    """``app.features`` 의 탐색 경로를 임시 디렉터리로 바꾼다 — 실제 기능 패키지는 건드리지 않는다."""
    monkeypatch.setattr(app.features, "__path__", [str(tmp_path)])
    prefix = "app.features.zz_fake_"
    yield tmp_path
    for name in [m for m in sys.modules if m.startswith(prefix)]:
        del sys.modules[name]


def _make_feature(root: pathlib.Path, name: str, *, with_tasks: bool) -> None:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if with_tasks:
        # 탐색이 태스크 모듈을 import 하면 이 줄이 터진다 — 실제 태스크 모듈은 celery_app 을
        # import 하므로, Celery 앱 생성 중에 import 하면 순환 import 가 된다.
        (pkg / "tasks.py").write_text(
            "raise RuntimeError('imported at discovery')\n", encoding="utf-8"
        )
    importlib.invalidate_caches()


def test_discovery_skips_features_without_tasks_and_does_not_import_them(fake_features):
    _make_feature(fake_features, "zz_fake_with", with_tasks=True)
    _make_feature(fake_features, "zz_fake_without", with_tasks=False)

    assert models_registry.iter_task_modules() == ["app.features.zz_fake_with.tasks"]
    assert "app.features.zz_fake_with.tasks" not in sys.modules


def test_removing_a_feature_removes_its_tasks_from_include(fake_features):
    """기능 디렉터리를 지우면 include 에서도 빠진다 — 손볼 중앙 목록이 없다."""
    _make_feature(fake_features, "zz_fake_a", with_tasks=True)
    _make_feature(fake_features, "zz_fake_b", with_tasks=True)
    assert models_registry.iter_task_modules() == [
        "app.features.zz_fake_a.tasks",
        "app.features.zz_fake_b.tasks",
    ]

    for path in sorted((fake_features / "zz_fake_a").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (fake_features / "zz_fake_a").rmdir()
    sys.modules.pop("app.features.zz_fake_a", None)
    importlib.invalidate_caches()

    assert models_registry.iter_task_modules() == ["app.features.zz_fake_b.tasks"]


def test_celery_uses_utc_internally():
    """Celery 내부 시각은 UTC 다 — DB 저장 시각과 같은 기준(service-hardening ADR-010)."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE
