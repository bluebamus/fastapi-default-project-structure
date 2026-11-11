"""OpenAPI 계약 — 클라이언트(SDK 생성기·문서 UI)가 기대는 규칙.

- operation_id 는 존재하고 고유하다(SDK 함수명이 된다).
- 204 는 본문이 없고, 그 외 2xx 는 응답 스키마가 있다.
- 공개 스키마 이름이 모듈 경로로 뭉개지지 않는다.
- 422 문서는 앱이 실제로 보내는 ``ErrorResponse`` 를 설명한다.
"""

import pytest


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


def _resolve(schema: dict, node: dict) -> dict:
    while "$ref" in node:
        node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def test_422_documents_the_body_the_app_actually_sends(schema):
    """모든 operation 의 422 문서가 실제 422 본문(``ErrorResponse``)을 설명한다.

    FastAPI 는 422 를 기본 ``HTTPValidationError``(``{"detail": [...]}``)로 광고하지만, 전역
    ``RequestValidationError`` 핸들러는 ``ErrorResponse``(``error_code``·``message``·``detail``)를 보낸다.
    실제 요청으로 받은 본문을 각 operation 의 422 스키마(필수 키·허용 키)에 대어 본다.
    """
    from fastapi.testclient import TestClient

    from main import app

    response = TestClient(app).get("/api/v1/blog/posts", params={"skip": "x"})
    assert response.status_code == 422
    body = response.json()

    checked = 0
    offenders = []
    for method, path, operation in _operations(schema):
        documented = operation.get("responses", {}).get("422")
        if documented is None:
            continue
        checked += 1
        target = _resolve(schema, documented["content"]["application/json"]["schema"])
        properties = set(target.get("properties", {}))
        required = set(target.get("required", []))
        if not (required <= set(body) <= properties):
            offenders.append(f"{_label(method, path)} -> {sorted(properties)}")

    assert checked >= 30, "422 를 문서화한 operation 이 사라졌다 — 검사가 비었다"
    assert not offenders, f"422 문서가 실제 본문 {sorted(body)} 과 다르다: {offenders}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]
