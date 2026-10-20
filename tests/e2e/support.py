"""E2E 테스트가 함께 쓰는 도우미 — 커버리지 장부, 고유 클라이언트 IP, 사용자·토큰 발급, 응답 스키마 대조."""

from __future__ import annotations

import itertools
import secrets
from collections import defaultdict
from typing import Any

import httpx

from tests.e2e.stack import SUPERUSER, Stack

# ── 커버리지 장부 (W3) ────────────────────────────────────────────────────
# (종류, 항목, 칸) → 그 칸을 실행한 테스트 nodeid 목록, 또는 "N/A: 사유".
# test_zz_inventory 가 실제 앱에서 뽑은 인벤토리와 대조해 빈 칸이 있으면 실패한다.
LEDGER: dict[tuple[str, str, str], list[str]] = defaultdict(list)
# 판정이 아니라 **기록**할 관측값(예: 메서드 분할 경로의 405 Allow). 인벤토리 표에 함께 남는다.
NOTES: dict[str, str] = {}


def record(nodeid: str, kind: str, item: str, cell: str, na: str | None = None) -> None:
    LEDGER[(kind, item, cell)].append(f"N/A: {na}" if na else nodeid)


# ── 클라이언트 ────────────────────────────────────────────────────────────
_ips = itertools.count(1)


def fresh_ip() -> str:
    """테스트 클라이언트마다 다른 X-Forwarded-For — 레이트 리밋 카운터가 테스트끼리 섞이지 않는다."""
    n = next(_ips)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255 or 1}"


def client(stack: Stack, token: str | None = None, ip: str | None = None) -> httpx.Client:
    headers = {"X-Forwarded-For": ip or fresh_ip()}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=stack.base_url, headers=headers, timeout=30)


def login(stack: Stack, username: str, password: str) -> dict[str, Any]:
    with client(stack) as c:
        resp = c.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    stack.secrets.update({tokens["access_token"], tokens["refresh_token"]})
    return tokens


def new_user(stack: Stack) -> dict[str, Any]:
    """가입 → 로그인. ``{"id","username","password","access","refresh"}``."""
    username = f"u-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(16)
    stack.secrets.add(password)
    with client(stack) as c:
        resp = c.post(
            "/api/v1/auth/register",
            json={"username": username, "email": f"{username}@example.com", "password": password},
        )
    assert resp.status_code == 201, resp.text
    tokens = login(stack, username, password)
    return {
        "id": resp.json()["id"],
        "username": username,
        "password": password,
        "access": tokens["access_token"],
        "refresh": tokens["refresh_token"],
    }


def superuser(stack: Stack) -> dict[str, Any]:
    tokens = login(stack, SUPERUSER, stack.superuser_password)
    return {"access": tokens["access_token"], "refresh": tokens["refresh_token"]}


# ── 응답 스키마 대조 ─────────────────────────────────────────────────────
def check_schema(spec: dict, schema: dict, value: Any, where: str = "$") -> None:
    """OpenAPI(JSON Schema 부분집합) 대로인지 본다 — 타입·필수 필드·**정의 밖 필드 없음**.

    지원: $ref · anyOf · type(object·array·string·integer·number·boolean·null) · required ·
    properties. 응답 모델이 실제로 쓰는 범위다. 모르는 구성이 오면 실패로 드러낸다.
    """
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        check_schema(spec, spec["components"]["schemas"][name], value, where)
        return
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                check_schema(spec, option, value, where)
                return
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(f"{where}: anyOf 어느 것과도 맞지 않는다 — {errors}")
    kind = schema.get("type")
    py = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }
    if kind is None:
        assert not schema or set(schema) <= {"title", "description", "examples"}, (where, schema)
        return
    assert isinstance(value, py[kind]) and not (
        kind in ("integer", "number") and isinstance(value, bool)
    ), f"{where}: {kind} 이어야 하는데 {type(value).__name__}"
    if kind == "object":
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        extra = set(value) - set(props)
        assert not missing, f"{where}: 필수 필드 없음 {missing}"
        assert not extra, f"{where}: 스키마 밖 필드 {extra}"
        for key, item in value.items():
            check_schema(spec, props[key], item, f"{where}.{key}")
    elif kind == "array":
        for i, item in enumerate(value):
            check_schema(spec, schema["items"], item, f"{where}[{i}]")
