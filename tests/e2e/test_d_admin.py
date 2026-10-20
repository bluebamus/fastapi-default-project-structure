"""L4 — 관리 화면: 실제 Chromium(Playwright) + 실제 MySQL·Redis 위의 uvicorn.

브라우저로 하는 것: 로그인, 생성·수정 폼 제출, 삭제 모달, 일괄 삭제, 기간 필터 UI, 로그아웃 링크 —
브라우저 스크립트(``base.html`` 의 CSRF 주입)가 실제로 토큰을 싣는지가 검증 대상이다(default R-005).
브라우저 밖 직접 요청(httpx)으로 하는 것: 토큰 없는 상태 변경 403, GET 로그아웃 405, 만료·폐기 확인.
"""

from __future__ import annotations

import re
import secrets
import time
import uuid
from datetime import datetime

import pytest
import redis as redis_lib
from playwright.sync_api import expect, sync_playwright

from tests.e2e.stack import SUPERUSER
from tests.e2e.support import client, fresh_ip, new_user, superuser

pytestmark = pytest.mark.e2e

CSRF_INPUT = re.compile(r'name="csrf_token" value="([^"]+)"')
CSRF_META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')

VIEWS = {
    # identity: (테이블, 생성 폼, 수정 필드)
    "post": ("blog_posts", {"title": "admin-made", "content": "body"}, "title"),
    "product": ("catalog_products", {"name": "admin-made", "price": "9.99"}, "name"),
    "user-access-log": ("user_access_logs", None, None),
    "reply": ("replies", {"content": "admin-made"}, "content"),
    "sales-order": ("sales_orders", None, None),
    "sns-post": ("sns_posts", {"content": "admin-made"}, "content"),
    "user": ("users", None, "email"),
}
DELETABLE = {"post", "product", "user-access-log", "reply", "sns-post", "user"}


def _flags():
    import app.features.admin as admin

    return {v.identity: v for v in admin.ADMIN_VIEWS}


FLAGS = _flags()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _login(browser, stack, username=SUPERUSER, password=None):
    context = browser.new_context(
        base_url=stack.base_url, extra_http_headers={"X-Forwarded-For": fresh_ip()}
    )
    page = context.new_page()
    page.goto("/admin/login")
    page.fill("#username", username)
    page.fill("#password", password or stack.superuser_password)
    page.click("button[type=submit]")
    return context, page


@pytest.fixture(scope="module")
def admin(browser, stack):
    context, page = _login(browser, stack)
    expect(page).to_have_url(re.compile(r"/admin/$"))
    page.close()
    yield context
    context.close()


@pytest.fixture(scope="module")
def owner(stack):
    return new_user(stack)


@pytest.fixture(scope="module")
def su(stack):
    return superuser(stack)["access"]


def _seed(stack, view: str, owner: dict, su: str, created_at: datetime | None = None) -> str:
    """관리 화면에 보일 행 하나를 만든다(API 가 있으면 API, 없으면 SQL)."""
    if view in ("post", "sns-post", "reply"):
        path = {
            "post": "/api/v1/blog/posts",
            "sns-post": "/api/v1/sns/posts",
            "reply": "/api/v1/reply/replies",
        }[view]
        body = {"title": "seed", "content": "seed"} if view == "post" else {"content": "seed"}
        with client(stack, owner["access"]) as c:
            rid = c.post(path, json=body).json()["id"]
    elif view == "product":
        with client(stack, su) as c:
            rid = c.post(
                "/api/v1/catalog/products",
                json={"name": f"seed-{secrets.token_hex(3)}", "price": "1.00"},
            ).json()["id"]
    elif view == "user":
        rid = new_user(stack)["id"]
    elif view == "sales-order":
        rid = str(uuid.uuid4())
        stack.execute(
            "INSERT INTO sales_orders (id, customer, total_amount, created_at) VALUES (%s,%s,%s,UTC_TIMESTAMP(6))",
            (rid, "seed", "1.00"),
        )
    else:
        rid = str(uuid.uuid4())
        stack.execute(
            "INSERT INTO user_access_logs (id, ip_address, request_path, request_method, is_bot, created_at)"
            " VALUES (%s,'192.0.2.9','/seed','GET',0,UTC_TIMESTAMP(6))",
            (rid,),
        )
    if created_at is not None:
        stack.execute(f"UPDATE {VIEWS[view][0]} SET created_at=%s WHERE id=%s", (created_at, rid))  # noqa: S608
    return rid


def _exists(stack, view: str, rid: str) -> bool:
    return bool(stack.query(f"SELECT 1 FROM {VIEWS[view][0]} WHERE id=%s", (rid,)))  # noqa: S608


def _na(cover, view: str, cell: str, flag: str, status: int) -> None:
    cover("admin", view, cell, na=f"{flag}=False — 화면에서 막혀 있음({status} 확인)")


# ── 1. 로그인 ────────────────────────────────────────────────────────────
def test_login_success_and_wrong_password(browser, stack, cover):
    context, page = _login(browser, stack)
    expect(page).to_have_url(re.compile(r"/admin/$"))
    context.close()
    context, page = _login(browser, stack, password="wrong-password")
    expect(page.locator("body")).to_contain_text("사용자명 또는 비밀번호가 올바르지 않습니다")
    context.close()
    cover("admin-auth", "login", "success")
    cover("admin-auth", "login", "wrong-password")


def test_login_without_csrf_is_403_and_rate_limit_is_429(stack, cover):
    with client(stack) as c:
        c.get("/admin/login")
        resp = c.post(
            "/admin/login", data={"username": SUPERUSER, "password": stack.superuser_password}
        )
    assert resp.status_code == 403
    cover("admin-auth", "login", "csrf-missing")

    r = redis_lib.Redis.from_url(stack.redis_url, decode_responses=True)
    ip = fresh_ip()
    with client(stack, ip=ip) as c:
        statuses = []
        for _ in range(6):
            token = CSRF_INPUT.search(c.get("/admin/login").text).group(1)
            statuses.append(
                c.post(
                    "/admin/login",
                    data={"username": "nobody", "password": "x", "csrf_token": token},
                )
            )
    assert [s.status_code for s in statuses] == [400] * 5 + [429]
    assert 0 < int(statuses[-1].headers["retry-after"]) <= 5
    assert r.exists(f"admin:rl:login:{ip}:nobody") and r.exists(f"admin:rl:login:{ip}")
    r.close()
    cover("admin-auth", "login", "rate-limit")
    cover("redis", "admin:rl:login:", "used")


# ── 2. 7 뷰 ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("view", sorted(VIEWS))
def test_list_and_detail(admin, stack, owner, su, cover, view):
    rid = _seed(stack, view, owner, su)
    page = admin.new_page()
    resp = page.goto(f"/admin/{view}/list")
    assert resp.status == 200
    detail = page.goto(f"/admin/{view}/details/{rid}")
    assert detail.status == 200
    expect(page.locator("body")).to_contain_text(rid)
    if view == "user":
        html = page.content()
        assert "hashed_password" not in html and "$argon2" not in html
    page.close()
    cover("admin", view, "list")
    cover("admin", view, "detail")


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_create(admin, stack, cover, view):
    _table, form, _ = VIEWS[view]
    page = admin.new_page()
    if not FLAGS[view].can_create:
        status = page.goto(f"/admin/{view}/create").status
        assert status in (403, 404), status
        _na(cover, view, "create", "can_create", status)
        page.close()
        return
    before = stack.query(f"SELECT COUNT(*) AS n FROM {VIEWS[view][0]}")[0]["n"]  # noqa: S608
    page.goto(f"/admin/{view}/create")
    unique = f"admin-{secrets.token_hex(4)}"
    for name, value in form.items():
        page.fill(f"[name={name}]", unique if value == "admin-made" else value)
    with page.expect_navigation():
        page.click("input[type=submit][value=Save]")
    assert page.url.endswith(f"/admin/{view}/list"), page.url
    after = stack.query(f"SELECT COUNT(*) AS n FROM {VIEWS[view][0]}")[0]["n"]  # noqa: S608
    assert after == before + 1
    page.close()
    cover("admin", view, "create")


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_edit(admin, stack, owner, su, cover, view):
    table, _form, field = VIEWS[view]
    rid = _seed(stack, view, owner, su)
    page = admin.new_page()
    if not FLAGS[view].can_edit:
        status = page.goto(f"/admin/{view}/edit/{rid}").status
        assert status in (403, 404), status
        _na(cover, view, "edit", "can_edit", status)
        page.close()
        return
    page.goto(f"/admin/{view}/edit/{rid}")
    value = f"edited-{secrets.token_hex(4)}" + ("@example.com" if field == "email" else "")
    page.fill(f"[name={field}]", value)
    with page.expect_navigation():
        page.click("input[type=submit][value=Save]")
    row = stack.query(f"SELECT {field} FROM {table} WHERE id=%s", (rid,))[0]  # noqa: S608
    assert row[field] == value
    page.close()
    cover("admin", view, "edit")


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_delete_from_the_row_modal(admin, stack, owner, su, cover, view):
    rid = _seed(stack, view, owner, su, created_at=datetime(2003, 3, 3, 3, 3, 3))
    page = admin.new_page()
    if not FLAGS[view].can_delete:
        token = CSRF_META.search(page.goto(f"/admin/{view}/list").text()).group(1)
        status = page.request.delete(
            f"/admin/{view}/delete?pks={rid}", headers={"X-CSRF-Token": token}
        ).status
        assert status in (403, 404) and _exists(stack, view, rid), status
        _na(cover, view, "delete", "can_delete", status)
        _na(cover, view, "bulk-delete", "can_delete", status)
        page.close()
        return
    page.goto(f"/admin/{view}/list?created_at=2003-03-03&created_at_op=on")
    page.locator(f'a[data-pk="{rid}"][data-bs-target="#modal-delete"]').click()
    # 성공하면 sqladmin 스크립트가 목록으로 이동한다 — 이동이 끝난 뒤에 페이지를 닫는다(닫다가 멈춘 적 있다).
    with (
        page.expect_navigation(),
        page.expect_response(lambda r: "/delete" in r.url and r.request.method == "DELETE") as info,
    ):
        page.click("#modal-delete-button")
    assert info.value.status == 200, info.value.text()
    assert not _exists(stack, view, rid)
    page.close()
    cover("admin", view, "delete")


@pytest.mark.parametrize("view", sorted(DELETABLE))
def test_bulk_delete(admin, stack, owner, su, cover, view):
    day = datetime(2004, 4, 4, 4, 4, 4)
    rids = [_seed(stack, view, owner, su, created_at=day) for _ in range(2)]
    page = admin.new_page()
    page.goto(f"/admin/{view}/list?created_at=2004-04-04&created_at_op=on")
    for rid in rids:
        page.locator(f'input[type=hidden][value="{rid}"] + input.select-box').check()
    page.click("#dropdownMenuButton")
    page.click("#action-delete")
    # 성공하면 sqladmin 스크립트가 목록으로 이동한다 — 이동이 끝난 뒤에 페이지를 닫는다(닫다가 멈춘 적 있다).
    with (
        page.expect_navigation(),
        page.expect_response(lambda r: "/delete" in r.url and r.request.method == "DELETE") as info,
    ):
        page.click("#modal-delete-button")
    assert info.value.status == 200, info.value.text()
    assert not any(_exists(stack, view, rid) for rid in rids)
    page.close()
    cover("admin", view, "bulk-delete")


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_export_csv_and_json(admin, stack, owner, su, cover, view):
    rid = _seed(stack, view, owner, su, created_at=datetime(2005, 5, 5, 5, 5, 5))
    page = admin.new_page()
    page.goto(f"/admin/{view}/list")
    for kind in ("csv", "json"):
        resp = page.request.get(f"/admin/{view}/export/{kind}")
        assert resp.status == 200, resp.status
        body = resp.text()
        assert rid in body
        if view == "user":
            assert "hashed_password" not in body and "$argon2" not in body
    page.close()
    cover("admin", view, "export")


@pytest.mark.parametrize("view", sorted(VIEWS))
def test_date_filters_on_after_before_and_range_ui(admin, stack, owner, su, cover, view):
    """같은 날·이후·이전(쿼리)과 기간(브라우저 UI).

    목록은 50행씩이라 실제 행이 많은 쪽 결과에서는 확인할 행이 다음 페이지로 밀린다. 그래서
    "이전" 은 과거(2006) 쌍, "이후" 는 미래(2090) 쌍으로 확인한다 — 경계 밖 실제 행이 결과에 끼지 않는다.
    """
    past = [_seed(stack, view, owner, su, created_at=datetime(2006, 6, d, 3, 0, 0)) for d in (6, 8)]
    future = [
        _seed(stack, view, owner, su, created_at=datetime(2090, 6, d, 3, 0, 0)) for d in (6, 8)
    ]
    page = admin.new_page()

    def listed(query: str) -> str:
        assert page.goto(f"/admin/{view}/list?{query}").status == 200
        return page.content()

    html = listed("created_at=2006-06-06&created_at_op=on")  # KST 6/6 12:00 → 그날
    assert past[0] in html and past[1] not in html
    html = listed("created_at=2006-06-07&created_at_op=before")
    assert past[0] in html and past[1] not in html
    html = listed("created_at=2090-06-07&created_at_op=on_or_after")
    assert future[1] in html and future[0] not in html

    page.goto(f"/admin/{view}/list")
    form = page.locator("form.local-date-range")
    form.locator("[data-range=start]").fill("2006-06-06")
    form.locator("[data-range=end]").fill("2006-06-08")
    with page.expect_navigation():
        form.locator("button[type=submit]").click()
    assert "created_at_op=between" in page.url
    html = page.content()
    assert past[0] in html and past[1] in html and future[0] not in html  # 양 끝 포함
    page.close()
    for cell in ("filter-on", "filter-on_or_after", "filter-before", "filter-between"):
        cover("admin", view, cell)


# ── 3. CSRF — 브라우저 밖 직접 요청 ────────────────────────────────────────
def test_state_changes_without_token_are_403(stack, owner, su, cover):
    with client(stack) as c:
        token = CSRF_INPUT.search(c.get("/admin/login").text).group(1)
        assert (
            c.post(
                "/admin/login",
                data={
                    "username": SUPERUSER,
                    "password": stack.superuser_password,
                    "csrf_token": token,
                },
            ).status_code
            == 302
        )
        rid = _seed(stack, "post", owner, su)
        assert c.post("/admin/post/create", data={"title": "x", "content": "y"}).status_code == 403
        assert (
            c.post(f"/admin/post/edit/{rid}", data={"title": "x", "content": "y"}).status_code
            == 403
        )
        assert c.delete(f"/admin/post/delete?pks={rid}").status_code == 403
        assert c.post("/admin/logout").status_code == 403
        assert _exists(stack, "post", rid)
        assert c.get("/admin/").status_code == 200  # 거부된 로그아웃은 세션을 건드리지 않았다
    for action in ("create", "edit", "delete", "logout"):
        cover("admin-auth", "csrf", action)


# ── 4. 로그아웃 ───────────────────────────────────────────────────────────
def test_logout_get_is_405_and_post_kills_the_old_cookie(browser, stack, cover):
    context, page = _login(browser, stack)
    expect(page).to_have_url(re.compile(r"/admin/$"))
    cookie = next(c for c in context.cookies() if c["name"] == "admin_session")
    assert page.request.get("/admin/logout").status == 405
    with page.expect_navigation():
        page.locator("a[href$='/admin/logout']").first.click()  # base.html 이 POST 폼으로 바꾼다
    expect(page).to_have_url(re.compile(r"/admin/login"))
    context.close()
    with client(stack) as c:
        c.cookies.set("admin_session", cookie["value"], path="/admin")
        resp = c.get("/admin/")
    assert resp.status_code == 302 and resp.headers["location"].endswith("/admin/login")
    cover("admin-auth", "logout", "get-405")
    cover("admin-auth", "logout", "post")


# ── 5. 만료·다른 세션 폐기 ────────────────────────────────────────────────
def _httpx_admin(stack, username=SUPERUSER, password=None):
    c = client(stack)
    token = CSRF_INPUT.search(c.get("/admin/login").text).group(1)
    resp = c.post(
        "/admin/login",
        data={
            "username": username,
            "password": password or stack.superuser_password,
            "csrf_token": token,
        },
    )
    assert resp.status_code == 302, resp.text
    return c


def _alive(c) -> bool:
    return c.get("/admin/").status_code == 200


def test_idle_and_absolute_session_expiry(stack, cover):
    """미사용 60초·절대 120초(설정 최솟값)로 앱을 다시 띄워 실제 시간으로 확인한다."""
    with stack.app_with(ADMIN_SESSION_IDLE_SECONDS="60", ADMIN_SESSION_MAX_AGE_SECONDS="120"):
        idle, busy = _httpx_admin(stack), _httpx_admin(stack)
        started = time.monotonic()
        while time.monotonic() - started < 62:
            assert _alive(busy)
            time.sleep(20)
        time.sleep(max(0.0, 62 - (time.monotonic() - started)))
        assert not _alive(idle), "미사용 60초가 지났는데 세션이 살아 있다"
        while time.monotonic() - started < 110:
            assert _alive(busy), "쓰고 있는 세션이 절대 만료 전에 끊겼다"
            time.sleep(20)
        time.sleep(max(0.0, 122 - (time.monotonic() - started)))
        assert not _alive(busy), "절대 만료 120초가 지났는데 세션이 살아 있다"
        idle.close()
        busy.close()
    cover("admin-auth", "session", "idle-expiry")
    cover("admin-auth", "session", "absolute-expiry")


@pytest.mark.parametrize(
    "action",
    ["deactivate", "demote", "delete"],
)
def test_admin_screen_change_kills_the_other_browsers_session(browser, stack, su, cover, action):
    name, password = f"su-{secrets.token_hex(4)}", secrets.token_urlsafe(16)
    stack.secrets.add(password)
    with client(stack, su) as c:
        target = c.post(
            "/api/v1/user/users",
            json={
                "username": name,
                "email": f"{name}@example.com",
                "password": password,
                "is_superuser": True,
            },
        ).json()["id"]
    victim = _httpx_admin(stack, name, password)
    assert _alive(victim)

    context, page = _login(browser, stack)
    if action == "delete":
        page.goto("/admin/user/list?search=" + name)
        page.locator(f'a[data-pk="{target}"][data-bs-target="#modal-delete"]').click()
        with page.expect_navigation(), page.expect_response(lambda r: "/delete" in r.url) as info:
            page.click("#modal-delete-button")
        assert info.value.status == 200
    else:
        page.goto(f"/admin/user/edit/{target}")
        page.uncheck("[name=is_active]" if action == "deactivate" else "[name=is_superuser]")
        with page.expect_navigation():
            page.click("input[type=submit][value=Save]")
    context.close()
    assert not _alive(victim), f"{action} 뒤에도 다른 브라우저의 관리 세션이 살아 있다"
    victim.close()
    cover("admin-auth", "session", f"revoke-on-{action}")


# ── 6. ADMIN_DISABLED ────────────────────────────────────────────────────
def test_admin_disabled_has_no_admin_at_all(stack, cover):
    with stack.app_with(ADMIN_DISABLED="true") as proc:
        with client(stack) as c:
            assert c.get("/admin/").status_code == 404
            assert c.get("/admin/login").status_code == 404
            assert c.get("/health").status_code == 200
        startup = proc.output.split("Application startup complete")[0]
    assert "/admin" not in startup, "ADMIN_DISABLED=true 인데 기동 로그에 관리 화면 경로가 나온다"
    cover("admin-auth", "admin-disabled", "404")
