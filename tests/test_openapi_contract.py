"""OpenAPI 문서 계약 검사 (DOC-001 / DOC-004 / DOC-005).

라우트 인벤토리 골든 스냅샷(`test_route_inventory.py`)이 **무엇이 노출되는가**를 고정한다면,
여기서는 노출된 것들이 **문서로서 쓸 만한가**를 규칙으로 검사한다. 스냅샷이 아니라 규칙이므로
새 엔드포인트가 추가돼도 골든 파일을 갱신할 필요 없이 자동으로 검사 대상이 된다.

규칙 자체가 요구사항이다:
    - operation_id 는 존재하고 프로젝트 전역에서 고유하다      (DOC-001, DOC-005)
    - 모든 operation 에 summary·description·tag 가 있다        (DOC-001)
    - 204 는 본문이 없고, 그 외 2xx 는 응답 스키마가 있다      (DOC-001, DOC-005)
    - 선언된 태그 집합과 사용된 태그 집합이 정확히 일치한다    (DOC-004, DOC-005)
    - 공개 스키마 이름이 모듈 경로로 뭉개지지 않는다           (F-015)
    - 프로젝트가 소유한 스키마의 필드에 description 이 있다    (DOC-003)

`app.openapi()` 를 대상으로 하는 이유는 `test_route_inventory.py` 와 같다 — FastAPI 버전에 따라
`app.routes` 의 중첩 형태가 달라지지만 OpenAPI 스키마는 공개 계약이라 안정적이다.
"""

import re

import pytest

# FastAPI/Pydantic 이 자동 생성하는 스키마. 우리가 필드 설명을 붙일 수 없다.
_GENERATED_SCHEMAS = {
    "HTTPValidationError",
    "ValidationError",
}

# `Body_<operationId>` — form/multipart 요청에 대해 FastAPI 가 만들어내는 합성 모델.
_GENERATED_SCHEMA_PATTERN = re.compile(r"^Body_")

# 참조 예제가 실제로 문서에 나타나는지 확인할 DTO (DOC-005 마지막 수용 기준).
_EXAMPLE_DTOS = {
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "ProductListResponse",
    "DailySalesItem",
    "DailySalesReportResponse",
}


@pytest.fixture(scope="module")
def schema() -> dict:
    from main import app

    return app.openapi()


def _operations(schema: dict):
    """(HTTP 메서드, 경로, operation object) 를 순회한다."""
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method in http_methods:
                yield method.upper(), path, operation


def _label(method: str, path: str) -> str:
    return f"{method} {path}"


def test_operation_ids_are_unique_and_present(schema):
    """operation_id 는 SDK 생성기의 함수명이 된다 — 없으면 자동 생성되고, 겹치면 덮어써진다."""
    seen: dict[str, str] = {}
    duplicates = []
    missing = []

    for method, path, operation in _operations(schema):
        operation_id = operation.get("operationId")
        if not operation_id:
            missing.append(_label(method, path))
            continue
        if operation_id in seen:
            duplicates.append(f"{operation_id}: {seen[operation_id]} / {_label(method, path)}")
        seen[operation_id] = _label(method, path)

    assert not missing, f"operation_id 가 없는 operation: {missing}"
    assert not duplicates, f"operation_id 가 중복됨: {duplicates}"


def test_every_operation_is_documented(schema):
    """summary·description·tag 가 비면 Scalar 에서 경로만 덩그러니 남는다."""
    offenders = []
    for method, path, operation in _operations(schema):
        missing = [
            field for field in ("summary", "description", "tags") if not operation.get(field)
        ]
        if missing:
            offenders.append(f"{_label(method, path)} -> {missing}")

    assert not offenders, f"문서 메타데이터가 빠진 operation: {offenders}"


def test_success_responses_have_a_schema_except_204(schema):
    """2xx 응답은 스키마가 있어야 하고, 204 는 반대로 본문이 없어야 한다.

    204 에 본문을 달면 Starlette 이 응답을 만들 때 조용히 버리므로, 문서와 실제가 어긋난다.
    """
    without_schema = []
    body_on_204 = []

    for method, path, operation in _operations(schema):
        for code, response in operation.get("responses", {}).items():
            if not code.startswith("2"):
                continue
            if code == "204":
                if response.get("content"):
                    body_on_204.append(f"{_label(method, path)} -> 204")
                continue
            content = response.get("content", {})
            if not any("schema" in media for media in content.values()):
                without_schema.append(f"{_label(method, path)} -> {code}")

    assert not without_schema, f"성공 응답에 스키마가 없다: {without_schema}"
    assert not body_on_204, f"204 응답에 본문이 선언됨: {body_on_204}"


def test_declared_and_used_tags_match_exactly(schema):
    """tags_metadata 와 실제 라우터 태그가 정확히 일치해야 한다 (DOC-004).

    선언만 있고 안 쓰이면 Scalar 에 빈 섹션이 남고(과거 `Analytics`),
    선언 없이 쓰이면 설명 없는 태그가 나타난다(과거 `Auth`).
    """
    declared = {tag["name"] for tag in schema.get("tags", [])}
    used = {tag for _, _, operation in _operations(schema) for tag in operation.get("tags", [])}

    assert not (declared - used), (
        f"tags_metadata 에 선언했지만 쓰지 않는 태그: {sorted(declared - used)}. "
        "라우터에 연결하거나 tags_metadata 에서 제거할 것."
    )
    assert not (used - declared), (
        f"라우터가 쓰지만 tags_metadata 에 없는 태그: {sorted(used - declared)}. "
        "app/core/tags_metadata.py 에 설명과 함께 추가할 것."
    )


def test_tag_descriptions_do_not_claim_unimplemented(schema):
    """구현이 끝난 기능의 태그 설명에 '미구현/예정' 문구가 남으면 안 된다 (DOC-004).

    설명이 코드보다 오래된 것은 문서가 없는 것보다 나쁘다 — 읽는 사람이 잘못 믿는다.
    """
    stale_markers = ("미구현", "예정")
    offenders = [
        f"{tag['name']}: {marker!r}"
        for tag in schema.get("tags", [])
        for marker in stale_markers
        if marker in tag.get("description", "")
    ]

    assert not offenders, (
        f"태그 설명에 오래된 문구가 남음: {offenders}. "
        "실제 제공 기능으로 갱신하거나, 정말 미구현이면 태그 자체를 제거할 것."
    )


def test_schema_names_are_not_module_qualified(schema):
    """공개 스키마 이름이 모듈 경로로 뭉개지지 않아야 한다.

    서로 다른 모듈에 같은 이름의 Pydantic 모델이 있으면 FastAPI 는 충돌을 피하려고
    `app__features__auth__schemas__auth_schema__UserResponse` 같은 키를 만든다. 이 이름은
    Scalar 문서와 생성된 클라이언트 SDK 에 그대로 노출된다. 모델 이름을 전역에서 고유하게
    지어 해결한다.
    """
    offenders = sorted(
        name for name in schema.get("components", {}).get("schemas", {}) if "__" in name
    )

    assert not offenders, (
        f"모듈 경로로 뭉개진 스키마 이름: {offenders}. "
        "같은 이름의 Pydantic 모델이 둘 이상이다 — 한쪽 클래스명을 고유하게 바꿀 것."
    )


def test_project_schema_fields_have_descriptions(schema):
    """프로젝트가 소유한 스키마의 필드에는 description 이 있어야 한다 (DOC-003).

    FastAPI 가 자동 생성하는 스키마는 우리가 손댈 수 없으므로 제외한다.
    """
    offenders = []
    for name, definition in schema.get("components", {}).get("schemas", {}).items():
        if name in _GENERATED_SCHEMAS or _GENERATED_SCHEMA_PATTERN.match(name):
            continue
        missing = sorted(
            field
            for field, spec in definition.get("properties", {}).items()
            if not spec.get("description")
        )
        if missing:
            offenders.append(f"{name}: {missing}")

    assert not offenders, (
        f"description 이 없는 공개 필드: {offenders}. " "Field(..., description=...) 를 붙일 것."
    )


def test_reference_example_dtos_are_published(schema):
    """ORM/Raw 참조 예제의 DTO 가 실제로 OpenAPI 에 실려야 한다 (DOC-005).

    예제 라우터가 통째로 빠져도 위 규칙 검사들은 전부 통과한다 — 검사 대상이 사라질 뿐이다.
    이 테스트가 "예제가 문서에 존재한다"를 따로 못 박는다.
    """
    published = set(schema.get("components", {}).get("schemas", {}))
    missing = sorted(_EXAMPLE_DTOS - published)

    assert not missing, f"참조 예제 DTO 가 OpenAPI 에 없다: {missing}"


def test_contract_checks_are_not_vacuous(schema):
    """검사 대상이 실제로 존재하는지 확인한다.

    라우팅이 깨져 operation 이 0개가 되면 위 규칙들은 조용히 전부 통과한다.
    """
    assert len(list(_operations(schema))) >= 30
    assert len(schema.get("components", {}).get("schemas", {})) >= 20
