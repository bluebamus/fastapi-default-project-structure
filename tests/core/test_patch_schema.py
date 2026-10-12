"""null PATCH 거부 — service-hardening ADR-008 ① (F-010).

``{"title": null}`` 처럼 **보낸** null 이 NOT NULL 컬럼으로 내려가 500 이 났다. 모든 Update
스키마는 ``PatchSchema`` 를 상속하고, nullable 로 선언한 필드만 null 을 받는다.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel, ValidationError

import app.features
from app.core.schemas import PatchSchema


def _update_schemas() -> list[type[BaseModel]]:
    found: dict[str, type[BaseModel]] = {}
    for feature in pkgutil.iter_modules(app.features.__path__):
        package = f"app.features.{feature.name}.schemas"
        try:
            schemas = importlib.import_module(package)
        except ModuleNotFoundError:
            continue
        for module in pkgutil.iter_modules(schemas.__path__):
            loaded = importlib.import_module(f"{package}.{module.name}")
            for name, obj in inspect.getmembers(loaded, inspect.isclass):
                if name.endswith("Update") and issubclass(obj, BaseModel):
                    found[f"{obj.__module__}.{name}"] = obj
    return [found[key] for key in sorted(found)]


UPDATE_SCHEMAS = _update_schemas()


def test_update_schemas_are_discovered():
    names = {schema.__name__ for schema in UPDATE_SCHEMAS}
    assert {"PostUpdate", "ReplyUpdate", "SnsPostUpdate", "UserUpdate", "ProductUpdate"} <= names


@pytest.mark.parametrize("schema", UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_every_update_schema_inherits_patch_schema(schema):
    assert issubclass(schema, PatchSchema), f"{schema.__name__} 가 PatchSchema 를 상속하지 않는다"


@pytest.mark.parametrize("schema", UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_explicit_null_is_rejected_for_non_nullable_fields(schema):
    for field in sorted(set(schema.model_fields) - schema.nullable_fields):
        with pytest.raises(ValidationError, match=field):
            schema.model_validate({field: None})


@pytest.mark.parametrize("schema", UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_unset_fields_are_still_optional(schema):
    assert schema.model_validate({}).model_fields_set == set()


@pytest.mark.parametrize("schema", UPDATE_SCHEMAS, ids=lambda s: s.__name__)
def test_nullable_fields_accept_null(schema):
    for field in schema.nullable_fields:
        assert getattr(schema.model_validate({field: None}), field) is None


def test_nullable_allowlist_names_real_fields():
    """허용 목록의 오타는 조용히 아무것도 허용하지 않는다 — 실제 필드여야 한다."""
    for schema in UPDATE_SCHEMAS:
        assert schema.nullable_fields <= set(schema.model_fields), schema.__name__


def test_no_patch_field_is_nullable():
    """null 로 비울 수 있는 PATCH 필드가 없다 — 모델과 맞춘 목록.

    nullable 컬럼이던 ``author`` 는 서버가 인증 주체로 채우는 값이 되어 수정 스키마에서 빠졌다
    (service-hardening ADR-018).
    """
    allowed = {schema.__name__: schema.nullable_fields for schema in UPDATE_SCHEMAS}
    assert allowed["PostUpdate"] == frozenset()
    assert allowed["ReplyUpdate"] == frozenset()
    assert allowed["SnsPostUpdate"] == frozenset()
    assert allowed["UserUpdate"] == frozenset()
    assert allowed["ProductUpdate"] == frozenset()
