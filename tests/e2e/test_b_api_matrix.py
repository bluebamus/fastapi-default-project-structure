"""L2 — API 전수 매트릭스: operation × {정상·검증 오류·미인증·권한 부족·없음·잘못된 메서드·접근 정책}.

operation 목록은 **실제 앱**에서 뽑는다(``AccessPolicyGuard().routes``). 아래 ``SPECS`` 에 없는
operation 이 생기면 ``test_every_operation_has_a_spec`` 가 실패한다 — 새 API 는 여기 한 줄을 더해야
인벤토리 대조(test_zz_inventory)를 통과한다.

해당하지 않는 칸은 ``N/A: 사유`` 로 장부에 적는다(빈 칸 금지).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest

from tests.e2e.support import NOTES, check_schema, client, new_user, superuser

pytestmark = pytest.mark.e2e

CELLS = ("ok", "validation", "unauth", "forbidden", "notfound", "method", "policy")


def _app():
    from main import app

    return app


def _levels() -> dict[str, str]:
    from app.core.security.access import AccessPolicyGuard

    guard = AccessPolicyGuard()
    return {
        label: next(iter(guard.levels(ctx.dependant))).value for label, ctx in guard.routes(_app())
    }


LEVELS = _levels()
SPEC = _app().openapi()


@dataclass
class Ctx:
    """모듈 공용 주체: 슈퍼유저 토큰, 소유자, 다른 사용자."""

    stack: Any
    su: str
    owner: dict
    other: dict


@dataclass
class Spec:
    """operation 하나의 칸별 요청. 각 함수는 (토큰, 경로, httpx kwargs) 를 돌려준다."""

    ok: Callable[[Ctx], tuple]
    ok_status: int = 200
    verify: Callable[[Ctx, Any, str], None] | None = None  # DB 반영 확인(쓰기)
    validation: Callable[[Ctx], tuple] | str = "검증할 입력이 없다(경로 변수는 str)"
    forbidden: Callable[[Ctx], tuple] | str = "로그인만 요구 — 권한 단계 없음"
    notfound: Callable[[Ctx], tuple] | str = "컬렉션 경로 — 없는 대상이 없다"
    validation_code: str = "VALIDATION_ERROR"  # 도메인 검증(기간 역순 등)은 자기 코드를 쓴다


# ── 자원 생성기 ─────────────────────────────────────────────────────────
def _create(ctx: Ctx, path: str, body: dict, token: str) -> str:
    with client(ctx.stack, token) as c:
        resp = c.post(path, json=body)
    assert resp.status_code == 201, resp.text
    ctx.stack.wait_replica()  # 이어서 읽는 요청은 replica 로 간다
    return resp.json()["id"]


FAMILIES = {
    "blog": (
        "/api/v1/blog/posts",
        "blog_posts",
        lambda: {"title": "t", "content": "c"},
        {"title": ""},
        {"title": "t2"},
        {"title": ""},
    ),
    "sns": (
        "/api/v1/sns/posts",
        "sns_posts",
        lambda: {"content": "c"},
        {"content": "x" * 501},
        {"content": "c2"},
        {"content": ""},
    ),
    "reply": (
        "/api/v1/reply/replies",
        "replies",
        lambda: {"content": "c"},
        {"content": ""},
        {"content": "c2"},
        {"content": ""},
    ),
    "catalog": (
        "/api/v1/catalog/products",
        "catalog_products",
        lambda: {"name": f"p-{secrets.token_hex(4)}", "price": "10.00"},
        {"name": "p", "price": "0"},
        {"price": "12.50"},
        {"price": "-1"},
    ),
    "user": (
        "/api/v1/user/users",
        "users",
        lambda: {
            "username": f"m-{secrets.token_hex(5)}",
            "email": "m@example.com",
            "password": secrets.token_urlsafe(12),
        },
        {"username": "x", "email": "not-an-email", "password": "p"},
        {"email": "changed@example.com"},
        {"email": "not-an-email"},
    ),
}
PARAMS = {
    "blog": "post_id",
    "sns": "post_id",
    "reply": "reply_id",
    "catalog": "product_id",
    "user": "user_id",
}
OWNED = {"blog", "sns", "reply"}  # 로그인 작성·소유자 수정
SU_WRITE = {"catalog", "user"}


def _row(ctx: Ctx, table: str, rid: str) -> dict | None:
    rows = ctx.stack.query(f"SELECT * FROM {table} WHERE id=%s", (rid,))  # noqa: S608 - 고정 테이블명
    return rows[0] if rows else None


def _family_specs(name: str) -> dict[str, Spec]:
    base, table, body, bad, patch, bad_patch = FAMILIES[name]
    var = PARAMS[name]
    item = base + "/{" + var + "}"
    item_at = lambda rid: item.replace("{" + var + "}", str(rid))  # noqa: E731
    writer = (lambda ctx: ctx.owner["access"]) if name in OWNED else (lambda ctx: ctx.su)
    reader_list = (lambda ctx: ctx.su) if name == "user" else (lambda ctx: None)

    def fresh(ctx: Ctx) -> str:
        if name == "user":
            return ctx.owner["id"]  # 사용자 단건은 본인 기준(삭제 칸은 따로 만든다)
        return _create(ctx, base, body(), writer(ctx))

    def fresh_deletable(ctx: Ctx) -> str:
        return _create(ctx, base, body(), writer(ctx))

    item_reader = (lambda ctx: ctx.owner["access"]) if name == "user" else (lambda ctx: None)
    owner_or_su = (lambda ctx: ctx.su) if name == "catalog" else (lambda ctx: ctx.owner["access"])
    specs = {
        f"POST {base}": Spec(
            ok=lambda ctx: (writer(ctx), base, {"json": body()}),
            ok_status=201,
            verify=lambda ctx, resp, _p: _assert(_row(ctx, table, resp.json()["id"]) is not None),
            validation=lambda ctx: (writer(ctx), base, {"json": bad}),
            forbidden=(lambda ctx: (ctx.other["access"], base, {"json": body()}))
            if name in SU_WRITE
            else "로그인만 요구 — 누구나 작성",
        ),
        f"GET {base}": Spec(
            ok=lambda ctx: (reader_list(ctx), base, {}),
            validation=lambda ctx: (reader_list(ctx), base, {"params": {"limit": 0}}),
            forbidden=(lambda ctx: (ctx.other["access"], base, {}))
            if name == "user"
            else "Public 조회",
        ),
        f"GET {item}": Spec(
            ok=lambda ctx: (item_reader(ctx), item_at(fresh(ctx)), {}),
            forbidden=(lambda ctx: (ctx.other["access"], item_at(ctx.owner["id"]), {}))
            if name == "user"
            else "Public 조회",
            notfound=lambda ctx: (ctx.su, item_at(uuid.uuid4()), {}),
        ),
        f"PATCH {item}": Spec(
            ok=lambda ctx: (owner_or_su(ctx), item_at(fresh(ctx)), {"json": patch}),
            verify=lambda ctx, resp, p: _assert(
                all(str(_row(ctx, table, p.rsplit("/", 1)[-1])[k]) == v for k, v in patch.items())
            ),
            validation=lambda ctx: (owner_or_su(ctx), item_at(fresh(ctx)), {"json": bad_patch}),
            forbidden=lambda ctx: (ctx.other["access"], item_at(fresh(ctx)), {"json": patch}),
            notfound=lambda ctx: (ctx.su, item_at(uuid.uuid4()), {"json": patch}),
        ),
        f"DELETE {item}": Spec(
            ok=lambda ctx: (
                ctx.su if name in SU_WRITE else ctx.owner["access"],
                item_at(fresh_deletable(ctx)),
                {},
            ),
            ok_status=204,
            verify=lambda ctx, _resp, p: _assert(_row(ctx, table, p.rsplit("/", 1)[-1]) is None),
            forbidden=lambda ctx: (ctx.other["access"], item_at(fresh_deletable(ctx)), {}),
            notfound=lambda ctx: (ctx.su, item_at(uuid.uuid4()), {}),
        ),
    }
    return specs


def _assert(condition: bool) -> None:
    assert condition


def _home(path: str, *, limit: bool = True, notfound: str | None = None) -> Spec:
    return Spec(
        ok=lambda ctx: (ctx.su, path, {}),
        validation=(lambda ctx: (ctx.su, path, {"params": {"limit": 0}})) if limit else "입력 없음",
        forbidden=lambda ctx: (ctx.other["access"], path, {}),
        notfound=notfound or "컬렉션 경로 — 없는 대상이 없다",
    )


def _auth_specs() -> dict[str, Spec]:
    def register_body() -> dict:
        name = f"r-{secrets.token_hex(5)}"
        return {
            "username": name,
            "email": f"{name}@example.com",
            "password": secrets.token_urlsafe(12),
        }

    def fresh_refresh(ctx: Ctx) -> str:
        return new_user(ctx.stack)["refresh"]

    return {
        "POST /api/v1/auth/register": Spec(
            ok=lambda ctx: (None, "/api/v1/auth/register", {"json": register_body()}),
            ok_status=201,
            verify=lambda ctx, resp, _p: _assert(_row(ctx, "users", resp.json()["id"]) is not None),
            validation=lambda ctx: (
                None,
                "/api/v1/auth/register",
                {"json": {**register_body(), "email": "bad"}},
            ),
            forbidden="PublicWrite — 인증 없는 쓰기",
        ),
        "POST /api/v1/auth/login": Spec(
            ok=lambda ctx: (
                None,
                "/api/v1/auth/login",
                {"data": {"username": ctx.owner["username"], "password": ctx.owner["password"]}},
            ),
            validation=lambda ctx: (None, "/api/v1/auth/login", {"data": {"username": "x"}}),
            forbidden="PublicWrite — 인증 없는 쓰기(자격 실패 401 은 L3)",
        ),
        "POST /api/v1/auth/refresh": Spec(
            ok=lambda ctx: (
                None,
                "/api/v1/auth/refresh",
                {"json": {"refresh_token": fresh_refresh(ctx)}},
            ),
            validation=lambda ctx: (None, "/api/v1/auth/refresh", {"json": {}}),
            forbidden="PublicWrite — 인증 없는 쓰기(위조 토큰 401 은 L3)",
        ),
        "POST /api/v1/auth/logout": Spec(
            ok=lambda ctx: (
                None,
                "/api/v1/auth/logout",
                {"json": {"refresh_token": fresh_refresh(ctx)}},
            ),
            ok_status=204,
            validation=lambda ctx: (None, "/api/v1/auth/logout", {"json": {}}),
            forbidden="PublicWrite — 인증 없는 쓰기",
        ),
        "GET /api/v1/auth/me": Spec(ok=lambda ctx: (ctx.owner["access"], "/api/v1/auth/me", {})),
    }


def _reports_specs() -> dict[str, Spec]:
    today = date.today()
    good = {"start_date": str(today - timedelta(days=7)), "end_date": str(today)}
    reversed_ = {"start_date": str(today), "end_date": str(today - timedelta(days=7))}
    return {
        "GET /api/v1/reports/sales/daily": Spec(
            ok=lambda ctx: (ctx.su, "/api/v1/reports/sales/daily", {"params": good}),
            validation=lambda ctx: (ctx.su, "/api/v1/reports/sales/daily", {"params": reversed_}),
            validation_code="REPORT_INVALID_DATE_RANGE",
            forbidden=lambda ctx: (
                ctx.other["access"],
                "/api/v1/reports/sales/daily",
                {"params": good},
            ),
        ),
        "POST /api/v1/reports/sales/daily/snapshots": Spec(
            ok=lambda ctx: (ctx.su, "/api/v1/reports/sales/daily/snapshots", {"json": good}),
            verify=lambda ctx, resp, _p: _assert(resp.json()["deleted"] >= 0),
            validation=lambda ctx: (
                ctx.su,
                "/api/v1/reports/sales/daily/snapshots",
                {"json": reversed_},
            ),
            validation_code="REPORT_INVALID_DATE_RANGE",
            forbidden=lambda ctx: (
                ctx.other["access"],
                "/api/v1/reports/sales/daily/snapshots",
                {"json": good},
            ),
        ),
    }


SPECS: dict[str, Spec] = {
    **{k: v for fam in FAMILIES for k, v in _family_specs(fam).items()},
    **_auth_specs(),
    **_reports_specs(),
    "GET /api/v1/home/access-logs": _home("/api/v1/home/access-logs"),
    "GET /api/v1/home/access-logs/recent": _home("/api/v1/home/access-logs/recent"),
    "GET /api/v1/home/access-logs/by-ip/{ip_address}": _home(
        "/api/v1/home/access-logs/by-ip/192.0.2.250",
        notfound="목록 응답 — 없는 IP 는 빈 배열(ok 칸에서 확인)",
    ),
    "GET /api/v1/home/access-logs/by-user/{user_id}": _home(
        "/api/v1/home/access-logs/by-user/00000000-0000-0000-0000-000000000000",
        notfound="목록 응답 — 없는 사용자는 빈 배열(ok 칸에서 확인)",
    ),
    "GET /api/v1/home/access-logs/stats": _home("/api/v1/home/access-logs/stats", limit=False),
    "GET /health": Spec(
        ok=lambda ctx: (None, "/health", {}), validation="입력 없음", forbidden="Public 조회"
    ),
    "GET /ready": Spec(
        ok=lambda ctx: (None, "/ready", {}), validation="입력 없음", forbidden="Public 조회"
    ),
}
# /docs 는 DEBUG=true 일 때만 있다. E2E 는 배포 구성(DEBUG=false)이라 404 만 확인한다.
DEBUG_ONLY = {"GET /docs"}


@pytest.fixture(scope="module")
def ctx(stack) -> Ctx:
    return Ctx(
        stack=stack, su=superuser(stack)["access"], owner=new_user(stack), other=new_user(stack)
    )


def _send(ctx: Ctx, method: str, req: tuple):
    token, path, kwargs = req
    with client(ctx.stack, token) as c:
        return c.request(method, path, **kwargs)


def _response_schema(label: str, status: int) -> dict | None:
    method, path = label.split(" ", 1)
    content = SPEC["paths"][path][method.lower()]["responses"].get(str(status), {}).get("content")
    return content["application/json"]["schema"] if content else None


def _check_error(resp, status: int) -> None:
    assert resp.status_code == status, resp.text
    assert set(resp.json()) == {"error_code", "message", "detail"}, resp.json()


def test_every_operation_has_a_spec():
    assert set(LEVELS) - DEBUG_ONLY == set(SPECS), set(LEVELS) ^ set(SPECS)


@pytest.mark.parametrize("label", sorted(SPECS))
def test_ok(ctx, cover, label):
    spec = SPECS[label]
    method = label.split(" ", 1)[0]
    req = spec.ok(ctx)
    resp = _send(ctx, method, req)
    assert resp.status_code == spec.ok_status, resp.text
    schema = _response_schema(label, spec.ok_status)
    if schema is not None:
        check_schema(SPEC, schema, resp.json())
    else:
        assert not resp.content
    if spec.verify:
        spec.verify(ctx, resp, req[1])
    if "/by-ip/" in label or "/by-user/" in label:
        assert resp.json() == []  # 없는 IP·사용자는 404 가 아니라 빈 배열
    cover("api", label, "ok")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_validation(ctx, cover, label):
    spec = SPECS[label]
    if isinstance(spec.validation, str):
        cover("api", label, "validation", na=spec.validation)
        return
    resp = _send(ctx, label.split(" ", 1)[0], spec.validation(ctx))
    _check_error(resp, 422)
    body = resp.json()
    assert body["error_code"] == spec.validation_code, body
    if isinstance(body["detail"], list):
        assert all({"field", "message", "type"} <= set(d) for d in body["detail"]), body
    cover("api", label, "validation")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_unauthenticated(ctx, cover, label):
    level = LEVELS[label]
    if level in ("Public", "PublicWrite"):
        cover("api", label, "unauth", na=f"{level} 선언 — 인증을 요구하지 않는다")
        return
    token, path, kwargs = SPECS[label].ok(ctx)
    resp = _send(ctx, label.split(" ", 1)[0], (None, path, kwargs))
    _check_error(resp, 401)
    assert resp.headers.get("www-authenticate", "").lower().startswith("bearer"), resp.headers
    cover("api", label, "unauth")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_forbidden(ctx, cover, label):
    spec = SPECS[label]
    if isinstance(spec.forbidden, str):
        cover("api", label, "forbidden", na=spec.forbidden)
        return
    resp = _send(ctx, label.split(" ", 1)[0], spec.forbidden(ctx))
    _check_error(resp, 403)
    assert resp.json()["error_code"] == "FORBIDDEN"
    cover("api", label, "forbidden")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_not_found(ctx, cover, label):
    spec = SPECS[label]
    if isinstance(spec.notfound, str):
        cover("api", label, "notfound", na=spec.notfound)
        return
    resp = _send(ctx, label.split(" ", 1)[0], spec.notfound(ctx))
    _check_error(resp, 404)
    cover("api", label, "notfound")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_wrong_method(ctx, cover, label):
    """경로가 받지 않는 메서드 → 405 + ``Allow``.

    한 경로를 메서드별 라우트로 나눈 곳(``GET``+``POST`` 컬렉션, ``GET``+``PATCH``+``DELETE`` 단건)은
    Starlette 가 **마지막으로 맞은 라우트의 메서드만** ``Allow`` 에 싣는다. 사용자 결정으로 현행을 유지하고
    값만 기록한다(계획서 §3 L2) — 여기서는 ``Allow`` 가 있고 그 경로가 받는 메서드의 부분집합인지만 본다.
    """
    _method, path = label.split(" ", 1)
    allowed = {m.upper() for m in SPEC["paths"][path]}
    probe = "PUT" if "PUT" not in allowed else "TRACE"
    concrete = path.replace("{ip_address}", "192.0.2.1")
    for var in ("{post_id}", "{reply_id}", "{product_id}", "{user_id}"):
        concrete = concrete.replace(var, str(uuid.uuid4()))
    with client(ctx.stack, ctx.su) as c:
        resp = c.request(probe, concrete)
    assert resp.status_code == 405, resp.text
    observed = {m.strip() for m in resp.headers["allow"].split(",")}
    assert observed and observed <= allowed, resp.headers
    NOTES[f"405 Allow · {path}"] = (
        f"{resp.headers['allow']} (경로가 받는 메서드: {', '.join(sorted(allowed))})"
    )
    cover("api", label, "method")


@pytest.mark.parametrize("label", sorted(SPECS))
def test_access_policy_matches_declaration(ctx, cover, label):
    """선언(Public·PublicWrite·LoginRequired·SuperuserRequired)과 실제 응답이 같은가."""
    level = LEVELS[label]
    method = label.split(" ", 1)[0]
    spec = SPECS[label]
    token, path, kwargs = spec.ok(ctx)
    anonymous = _send(ctx, method, (None, path, kwargs))
    if level in ("Public", "PublicWrite"):
        assert anonymous.status_code == spec.ok_status, anonymous.text
    else:
        assert anonymous.status_code == 401
        token, path, kwargs = spec.ok(ctx)
        normal = _send(ctx, method, (ctx.other["access"], path, kwargs))
        if level == "SuperuserRequired":
            assert normal.status_code == 403, normal.text
        else:
            assert normal.status_code != 401, normal.text
    cover("api", label, "policy")


def test_docs_is_absent_in_deployed_config(ctx, cover):
    with client(ctx.stack) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
    for cell in CELLS:
        cover("api", "GET /docs", cell, na="DEBUG=false 배포 구성에서 경로 자체가 없다(404 확인)")
