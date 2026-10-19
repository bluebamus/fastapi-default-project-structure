"""설정 필드 사용처 계약 (config-cleanup ADR-002·ADR-003).

1. **읽히지 않는 설정은 두지 않는다.** config.py 의 모든 Settings 필드는 app·scripts·migrations·
   main.py·config.py(파생 property·검사 함수) 어딘가에서 **속성으로 읽혀야** 한다. 정의만 있고
   아무도 읽지 않는 필드는 "켜면 동작할 것" 처럼 보이지만 효과가 없다(예: 지운 SMTP_*·UPLOAD_*·
   SESSION_EXPIRE_SECONDS). 자기 클래스의 validator 안에서만 읽히는 것은 사용으로 치지 않는다 —
   값 검사만 하고 아무도 쓰지 않는 필드이기 때문이다.
2. **지운 키가 `.env` 에 남아도 기동은 깨지지 않는다.** 모든 Settings 는 ``extra="ignore"`` 라
   운영 `.env` 의 옛 줄은 조용히 무시된다(지워도 되고 남아도 된다).
"""

import ast
import inspect
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

import config as config_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = ("app", "scripts", "migrations")
SOURCE_FILES = ("main.py", "config.py")
VALIDATOR_DECORATORS = {"model_validator", "field_validator"}

#: 지운 키 — `.env` 에 남아 있어도 무시돼야 한다(config-cleanup 1차·2차).
REMOVED_KEYS = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_PASSWORD": "your-app-password",
    "SMTP_TLS": "true",
    "SMTP_SSL": "true",
    "UPLOAD_DIR": "uploads",
    "UPLOAD_IMAGE_QUALITY": "999",
    "SESSION_EXPIRE_SECONDS": "not-a-number",
    "API_VERSION": "v9",
}


def _settings_classes() -> list[type[BaseSettings]]:
    return [
        obj
        for obj in vars(config_module).values()
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
    ]


def _sources() -> list[Path]:
    paths = [PROJECT_ROOT / name for name in SOURCE_FILES]
    for root in SOURCE_ROOTS:
        paths.extend(p for p in (PROJECT_ROOT / root).rglob("*.py") if "__pycache__" not in p.parts)
    return paths


def _is_validator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    # config.py 의 validator 는 모두 `@model_validator(mode=...)` 꼴이다.
    return any(
        isinstance(d, ast.Call) and getattr(d.func, "id", "") in VALIDATOR_DECORATORS
        for d in node.decorator_list
    )


class _ReadCollector(ast.NodeVisitor):
    """속성 접근 `x.FIELD` 와 `getattr(x, "FIELD")` 를 모은다(validator 본문 제외)."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not _is_validator(node):
            self.generic_visit(node)

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.names.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            self.names.add(node.args[1].value)
        self.generic_visit(node)


def _read_names() -> set[str]:
    collector = _ReadCollector()
    for path in _sources():
        collector.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return collector.names


def _all_fields() -> set[str]:
    return {name for cls in _settings_classes() for name in cls.model_fields}


def test_every_settings_field_is_read_somewhere():
    """정의만 있고 읽히지 않는 설정 필드가 없어야 한다."""
    unused = sorted(_all_fields() - _read_names())
    assert not unused, (
        f"읽는 코드가 없는 설정 필드: {unused}\n"
        "쓰는 코드를 함께 넣거나 필드를 지운다(.env.example 도). 예외 목록은 두지 않는다(config-cleanup-2)."
    )


def test_reader_sees_known_reads():
    """수집기가 죽으면 위 검사가 전부 실패하거나 통과하므로, 알려진 읽기 경로로 확인한다.

    property 안의 ``self.MYSQL_HOST``, 다른 모듈의 ``log_settings.LOG_SQL_ECHO_ENABLED``.
    """
    read = _read_names()
    assert {"MYSQL_HOST", "LOG_SQL_ECHO_ENABLED", "ADMIN_SESSION_IDLE_SECONDS"} <= read


@pytest.mark.parametrize("settings_cls", _settings_classes(), ids=lambda c: c.__name__)
def test_removed_keys_are_ignored(settings_cls, monkeypatch, tmp_path):
    """지운 키가 환경 변수·`.env` 에 남아 있어도 오류 없이 무시되고 속성으로 생기지 않는다."""
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in REMOVED_KEYS.items()), encoding="utf-8")
    for key, value in REMOVED_KEYS.items():
        monkeypatch.setenv(key, value)

    instance = settings_cls(_env_file=env_file)

    for key in REMOVED_KEYS:
        assert not hasattr(instance, key)
    assert settings_cls.model_config.get("extra") == "ignore"
