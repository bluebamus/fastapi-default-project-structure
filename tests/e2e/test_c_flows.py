"""L3 — 연동 시나리오: HTTP 응답뿐 아니라 DB·Redis 상태까지 확인한다."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import redis as redis_lib
from celery import Celery

from tests.e2e.support import client, fresh_ip, login, new_user, superuser

pytestmark = pytest.mark.e2e

CSRF_INPUT = re.compile(r'name="csrf_token" value="([^"]+)"')


def _claims(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@pytest.fixture(scope="module")
def r(stack):
    client_ = redis_lib.Redis.from_url(stack.redis_url, decode_responses=True)
    yield client_
    client_.close()


@pytest.fixture(scope="module")
def su(stack):
    return superuser(stack)["access"]


def _admin_login(stack, username: str, password: str):
    """관리 화면 로그인(httpx) — 로그인 화면의 hidden CSRF 토큰을 실어 POST."""
    c = client(stack)
    token = CSRF_INPUT.search(c.get("/admin/login").text).group(1)
    resp = c.post(
        "/admin/login", data={"username": username, "password": password, "csrf_token": token}
    )
    assert resp.status_code == 302, resp.text
    return c


# ── 1. 토큰 수명 ─────────────────────────────────────────────────────────
def test_token_lifecycle_rotation_reuse_and_logout(stack, r, cover):
    user = new_user(stack)
    with client(stack, user["access"]) as c:
        me = c.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["username"] == user["username"]

    first = _claims(user["refresh"])
    assert r.exists(f"auth:rt:{first['jti']}")
    assert first["fam"] in r.smembers(f"auth:user:{user['id']}:fams")

    with client(stack) as c:
        rotated = c.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh"]})
        assert rotated.status_code == 200, rotated.text
        new_refresh = rotated.json()["refresh_token"]
        stack.secrets.update({new_refresh, rotated.json()["access_token"]})
        assert not r.exists(f"auth:rt:{first['jti']}")  # 쓴 토큰은 GETDEL 로 소비됐다
        # 이전 refresh 재사용 → 401 이고 family 전체가 폐기된다(새 토큰도 거부)
        assert (
            c.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh"]}).status_code
            == 401
        )
        assert r.exists(f"auth:fam:{first['fam']}:revoked")
        assert (
            c.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401
        )

    again = login(stack, user["username"], user["password"])
    with client(stack) as c:
        assert (
            c.post(
                "/api/v1/auth/logout", json={"refresh_token": again["refresh_token"]}
            ).status_code
            == 204
        )
        assert (
            c.post(
                "/api/v1/auth/logout", json={"refresh_token": again["refresh_token"]}
            ).status_code
            == 204
        )
        reuse = c.post("/api/v1/auth/refresh", json={"refresh_token": again["refresh_token"]})
    assert reuse.status_code == 401
    assert reuse.headers["www-authenticate"] == "Bearer"  # refresh 의 401 도 challenge (결정 3)
    assert r.exists(f"auth:fam:{_claims(again['refresh_token'])['fam']}:revoked")
    for prefix in ("auth:rt:", "auth:fam:", "auth:user:"):
        cover("redis", prefix, "used")


# ── 2. 레이트 리밋 ───────────────────────────────────────────────────────
def test_login_and_register_rate_limits_recover_after_the_window(stack, r, cover):
    user = new_user(stack)
    ip = fresh_ip()
    with client(stack, ip=ip) as c:
        for _ in range(5):
            bad = c.post(
                "/api/v1/auth/login", data={"username": user["username"], "password": "wrong-pass"}
            )
            assert bad.status_code == 401
            assert bad.headers["www-authenticate"] == "Bearer"  # 로그인 실패 401 도 (결정 3)
        blocked = c.post(
            "/api/v1/auth/login", data={"username": user["username"], "password": user["password"]}
        )
        assert blocked.status_code == 429
        assert 0 < int(blocked.headers["retry-after"]) <= 5
        key = f"auth:rl:login:{ip}:{user['username'].lower()}"
        assert 0 < r.ttl(key) <= 5 and int(r.get(key)) >= 6
        assert r.exists(f"auth:rl:login:{ip}")  # IP 단위 카운터
        time.sleep(6)  # 창(AUTH_LOGIN_WINDOW_SECONDS=5)이 지나면 회복
        ok = c.post(
            "/api/v1/auth/login", data={"username": user["username"], "password": user["password"]}
        )
        assert ok.status_code == 200
        stack.secrets.update({ok.json()["access_token"], ok.json()["refresh_token"]})
        assert not r.exists(key)  # 성공하면 IP+사용자명 카운터를 지운다

    ip = fresh_ip()
    with client(stack, ip=ip) as c:
        codes = []
        for _ in range(6):
            name = f"rl-{secrets.token_hex(5)}"
            codes.append(
                c.post(
                    "/api/v1/auth/register",
                    json={
                        "username": name,
                        "email": f"{name}@example.com",
                        "password": secrets.token_urlsafe(12),
                    },
                ).status_code
            )
        assert codes == [201] * 5 + [429], codes
        assert 0 < r.ttl(f"auth:rl:register:{ip}") <= 5
    cover("redis", "auth:rl:login:", "used")
    cover("redis", "auth:rl:register:", "used")


# ── 3. 소유권 ────────────────────────────────────────────────────────────
def test_ownership_on_posts_and_replies(stack, su):
    owner, other = new_user(stack), new_user(stack)
    with (
        client(stack, owner["access"]) as o,
        client(stack, other["access"]) as x,
        client(stack, su) as s,
    ):
        post = o.post("/api/v1/blog/posts", json={"title": "t", "content": "c"}).json()
        reply = o.post("/api/v1/reply/replies", json={"content": "c", "post_id": post["id"]}).json()
        stack.wait_replica()
        for path in (f"/api/v1/blog/posts/{post['id']}", f"/api/v1/reply/replies/{reply['id']}"):
            body = {"title": "x"} if "blog" in path else {"content": "x"}
            assert x.patch(path, json=body).status_code == 403
            assert x.delete(path).status_code == 403
            assert o.patch(path, json=body).status_code == 200
            assert s.patch(path, json=body).status_code == 200  # 슈퍼유저는 남의 것도 고친다
            assert o.delete(path).status_code == 204
        assert post["author_id"] == owner["id"]


# ── 4. 사용자 비활성화·강등·삭제 → 폐기 집합 ──────────────────────────────
def _make_superuser(stack, su: str) -> dict:
    name = f"su-{secrets.token_hex(5)}"
    password = secrets.token_urlsafe(16)
    stack.secrets.add(password)
    with client(stack, su) as c:
        created = c.post(
            "/api/v1/user/users",
            json={
                "username": name,
                "email": f"{name}@example.com",
                "password": password,
                "is_superuser": True,
            },
        )
    assert created.status_code == 201, created.text
    stack.wait_replica()
    tokens = login(stack, name, password)
    return {
        "id": created.json()["id"],
        "name": name,
        "password": password,
        "refresh": tokens["refresh_token"],
    }


@pytest.mark.parametrize(
    ("change", "refresh_revoked"),
    [({"is_active": False}, True), ({"is_superuser": False}, False), (None, True)],
    ids=["deactivate", "demote", "delete"],
)
def test_user_changes_revoke_the_documented_sets(stack, r, su, cover, change, refresh_revoked):
    """비활성화·삭제는 refresh·관리 세션 모두, 강등은 관리 세션만 폐기한다(default 의 규칙 — 강등 시 refresh 유지)."""
    target = _make_superuser(stack, su)
    admin = _admin_login(stack, target["name"], target["password"])
    index = f"admin:user_sessions:{target['id']}"
    assert r.scard(index) == 1
    session_key = next(iter(r.smembers(index)))
    sid = admin.cookies.get("admin_session")
    expected_key = (
        "admin:sess:"
        + hmac.new(
            stack.env["SESSION_SECRET_KEY"].encode(), sid.encode(), hashlib.sha256
        ).hexdigest()
    )
    assert session_key == expected_key and r.exists(session_key)

    with client(stack, su) as c:
        path = f"/api/v1/user/users/{target['id']}"
        resp = c.delete(path) if change is None else c.patch(path, json=change)
    assert resp.status_code in (200, 204), resp.text

    assert not r.exists(session_key) and not r.exists(index)
    page = admin.get("/admin/")
    assert page.status_code == 302 and page.headers["location"].endswith("/admin/login")
    admin.close()
    with client(stack) as c:
        refreshed = c.post("/api/v1/auth/refresh", json={"refresh_token": target["refresh"]})
    assert refreshed.status_code == (401 if refresh_revoked else 200), refreshed.text
    if refreshed.status_code == 200:
        stack.secrets.update({refreshed.json()["access_token"], refreshed.json()["refresh_token"]})
        assert (
            _claims(refreshed.json()["access_token"])["su"] is False
        )  # 재발급 토큰은 강등이 반영된다
    cover("redis", "admin:sess:", "used")
    cover("redis", "admin:user_sessions:", "used")


# ── 5. 접속 로그 → 조회 → 보존 삭제(worker) ───────────────────────────────
def test_access_log_records_ip_xff_and_user_then_api_reads_it(stack, su, cover):
    user = new_user(stack)
    marker = f"/api/v1/blog/posts?skip=0&limit=1&tag={uuid.uuid4().hex}"
    with client(stack, user["access"]) as c:
        c.headers["X-Forwarded-For"] = "198.51.100.7, 203.0.113.9"
        assert c.get("/api/v1/auth/me").status_code == 200
        assert c.get(marker).status_code == 200
    rows = []
    for _ in range(50):  # 접속 로그는 응답 뒤 background 로 쌓인다
        rows = stack.query(
            "SELECT * FROM user_access_logs WHERE user_id=%s AND request_path=%s",
            (user["id"], "/api/v1/auth/me"),
        )
        if rows:
            break
        time.sleep(0.2)
    assert rows, "접속 로그가 쌓이지 않았다"
    row = rows[0]
    assert row["ip_address"] == "203.0.113.9"  # TRUSTED_PROXY_HOPS=1 → 오른쪽 끝
    assert row["forwarded_for"] == "198.51.100.7, 203.0.113.9"
    assert row["response_status"] == 200
    stack.wait_replica()
    with client(stack, su) as c:
        by_user = c.get(f"/api/v1/home/access-logs/by-user/{user['id']}").json()
        by_ip = c.get("/api/v1/home/access-logs/by-ip/203.0.113.9").json()
    assert any(item["id"] == row["id"] for item in by_user)
    assert any(item["id"] == row["id"] for item in by_ip)


def _celery(stack) -> Celery:
    return Celery("e2e", broker=stack.redis_url, backend=stack.redis_url)


def test_retention_purge_task_runs_on_the_worker_in_batches(stack, cover):
    """보존(365일) 경계 양쪽에 행을 넣고 worker 로 삭제 태스크를 돌린다 — 5,000행 배치가 반복된다."""
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(days=365)
    tag = f"/e2e-retention/{uuid.uuid4().hex}"
    rows = [
        (str(uuid.uuid4()), "192.0.2.1", tag, "GET", 0, cutoff - timedelta(days=1))
        for _ in range(5001)
    ]
    rows.append((str(uuid.uuid4()), "192.0.2.1", tag, "GET", 0, cutoff - timedelta(seconds=60)))
    keep = str(uuid.uuid4())
    rows.append((keep, "192.0.2.1", tag, "GET", 0, cutoff + timedelta(seconds=120)))
    stack.execute(
        "INSERT INTO user_access_logs (id, ip_address, request_path, request_method, is_bot, created_at)"
        " VALUES (%s,%s,%s,%s,%s,%s)",
        rows,
    )
    deleted = _celery(stack).send_task("home.purge_expired_access_logs").get(timeout=120)
    assert deleted == 5002  # 배치 5,000 을 넘는다 → 두 번째 배치까지 돌았다
    left = stack.query("SELECT id FROM user_access_logs WHERE request_path=%s", (tag,))
    assert [row["id"] for row in left] == [keep]
    assert "home.purge_expired_access_logs" in stack.worker.output
    cover("celery", "home.purge_expired_access_logs", "worker")


# ── 6. 매출 ─────────────────────────────────────────────────────────────
def test_sales_snapshot_then_daily_report_split_on_local_business_day(stack, su):
    """KST 23:59:59 와 다음날 00:00:00 주문은 다른 영업일이다(UTC 로 저장, TIME_ZONE 으로 묶는다)."""
    customer = f"c-{secrets.token_hex(4)}"
    stack.execute(
        "INSERT INTO sales_orders (id, customer, total_amount, created_at) VALUES (%s,%s,%s,%s)",
        [
            (
                str(uuid.uuid4()),
                customer,
                "10.00",
                datetime(2001, 2, 3, 14, 59, 59),
            ),  # KST 2/3 23:59:59
            (
                str(uuid.uuid4()),
                customer,
                "20.00",
                datetime(2001, 2, 3, 15, 0, 0),
            ),  # KST 2/4 00:00:00
        ],
    )
    stack.wait_replica()
    period = {"start_date": "2001-02-03", "end_date": "2001-02-04"}
    with client(stack, su) as c:
        daily = c.get("/api/v1/reports/sales/daily", params=period).json()["items"]
        first = c.post("/api/v1/reports/sales/daily/snapshots", json=period).json()
        second = c.post("/api/v1/reports/sales/daily/snapshots", json=period).json()
    assert [(i["sales_date"], i["order_count"], i["gross_amount"]) for i in daily] == [
        ("2001-02-03", 1, "10.00"),
        ("2001-02-04", 1, "20.00"),
    ]
    assert (first["inserted"], second["deleted"], second["inserted"]) == (2, 2, 2)  # 멱등
    snap = stack.query(
        "SELECT sales_date, order_count, gross_amount FROM sales_daily_snapshots"
        " WHERE sales_date BETWEEN %s AND %s ORDER BY sales_date",
        ("2001-02-03", "2001-02-04"),
    )
    assert [(str(s["sales_date"]), s["order_count"], str(s["gross_amount"])) for s in snap] == [
        ("2001-02-03", 1, "10.00"),
        ("2001-02-04", 1, "20.00"),
    ]


# ── 7. Celery ───────────────────────────────────────────────────────────
def test_aggregate_task_round_trips_through_the_worker(stack, cover):
    total = stack.query("SELECT COUNT(*) AS n FROM user_access_logs")[0]["n"]
    result = _celery(stack).send_task("home.aggregate_access_stats").get(timeout=60)
    assert result["total"] >= total
    cover("celery", "home.aggregate_access_stats", "worker")
    cover("redis", "celery-broker-backend", "used")  # 같은 Redis 가 broker·결과 backend


def test_beat_registers_the_daily_purge_schedule(stack, cover):
    beat = stack.spawn(
        "beat",
        [
            "-m",
            "celery",
            "-A",
            "app.celery.app:celery_app",
            "beat",
            "-l",
            "DEBUG",
            "--schedule",
            str(stack.run_dir / "beat-schedule"),
        ],
        # beat 은 기동 시 "Current schedule" 을 DEBUG 로 찍는다 — 프로젝트 레벨 필터가 막지 않게 연다.
        LOG_LEVEL="DEBUG",
        LOG_CONSOLE_LEVEL="DEBUG",
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and "home.purge_expired_access_logs" not in beat.output:
            time.sleep(0.3)
    finally:
        beat.stop()
        stack.procs.remove(beat)
    out = beat.output
    assert "home.purge_expired_access_logs" in out, out
    assert re.search(r"<crontab: 30 3 \* \* \*", out), out
    cover("celery", "beat:home.purge_expired_access_logs", "schedule")


# ── 8. 읽기/쓰기 분리 ────────────────────────────────────────────────────
def test_reads_go_to_replica_and_writer_sessions_see_their_own_writes(stack):
    """replica 적용을 멈추면 방금 쓴 글이 조회(GET, replica)에는 없고 수정(PATCH, writer)에는 있다."""
    user = new_user(stack)
    stack.sql("mysql-replica", "STOP REPLICA SQL_THREAD;")
    try:
        with client(stack, user["access"]) as c:
            post = c.post("/api/v1/blog/posts", json={"title": "t", "content": "c"}).json()
            assert (
                c.get(f"/api/v1/blog/posts/{post['id']}").status_code == 404
            )  # replica 에 아직 없다
            assert (
                c.patch(f"/api/v1/blog/posts/{post['id']}", json={"title": "u"}).status_code == 200
            )
    finally:
        stack.sql("mysql-replica", "START REPLICA SQL_THREAD;")
    stack.wait_replica()
    with client(stack) as c:
        assert c.get(f"/api/v1/blog/posts/{post['id']}").json()["title"] == "u"


async def test_routing_session_is_sticky_to_the_writer_after_a_write(stack):
    """연결 대상(@@server_id)으로 확인: 쓰기 전 읽기는 replica(2), 쓰기 뒤 같은 세션은 primary(1)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.db.router import DatabaseRouter, create_routing_sessionmaker

    def url(port: int) -> str:
        return f"mysql+aiomysql://fastapi_e2e:{stack.db_password}@127.0.0.1:{port}/fastapi_e2e"

    writer, reader = create_async_engine(url(13321)), create_async_engine(url(13322))
    try:
        maker = create_routing_sessionmaker(
            DatabaseRouter(writer, [reader], sticky_after_write=True)
        )
        async with maker() as session:
            assert (await session.execute(text("SELECT @@server_id"))).scalar() == 2
        async with maker() as session:
            await session.execute(
                text("UPDATE users SET updated_at = updated_at WHERE id = 'none'")
            )
            assert (await session.execute(text("SELECT @@server_id"))).scalar() == 1  # sticky
            await session.rollback()
    finally:
        await writer.dispose()
        await reader.dispose()
