"""L5 — 장애 주입: 이 스택의 컨테이너·프로세스만 멈췄다 켠다.

데이터는 tmpfs 라 MySQL 컨테이너를 멈추면 그 서버의 데이터가 사라진다. 그래서 primary 정지는 이 파일의
마지막 테스트이고, 끝나면 스택을 처음부터 다시 세운다(복제·스키마·슈퍼유저·앱·워커).
"""

from __future__ import annotations

import re
import time

import httpx
import pytest
from celery import Celery

from tests.e2e.stack import SUPERUSER
from tests.e2e.support import NOTES, client, new_user, superuser

pytestmark = pytest.mark.e2e

CSRF_INPUT = re.compile(r'name="csrf_token" value="([^"]+)"')
CSRF_META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')
LEAKS = re.compile(
    r"traceback|pymysql|aiomysql|operationalerror|redis|connectionerror|errno|1332[12]|16391|select |insert ",
    re.IGNORECASE,
)


def _no_internals(resp: httpx.Response) -> None:
    assert resp.status_code >= 500, resp.text
    assert not LEAKS.search(resp.text), f"5xx 응답에 내부 정보가 있다: {resp.text}"


def _admin(stack) -> httpx.Client:
    c = client(stack)
    token = CSRF_INPUT.search(c.get("/admin/login").text).group(1)
    data = {"username": SUPERUSER, "password": stack.superuser_password, "csrf_token": token}
    assert c.post("/admin/login", data=data).status_code == 302
    return c


def _wait(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise AssertionError("회복을 기다리다 시간이 다 됐다")


def _ready(stack) -> int:
    return httpx.get(stack.base_url + "/ready", timeout=10).status_code


def test_redis_down_admin_fails_closed_and_api_follows_policy(stack, cover):
    user = new_user(stack)
    admin = _admin(stack)
    page = admin.get(f"/admin/user/edit/{user['id']}")
    token = CSRF_META.search(page.text).group(1)
    stack.stop_service("redis")
    try:
        # 관리 화면: 503 fail-closed, 사용자 변경은 저장되지 않는다
        blocked = admin.get("/admin/")
        assert (
            blocked.status_code == 503 and "관리 세션 저장소를 사용할 수 없습니다" in blocked.text
        )
        change = admin.post(
            f"/admin/user/edit/{user['id']}",
            data={
                "username": user["username"],
                "email": user["username"] + "@example.com",
                "csrf_token": token,
            },
        )
        assert change.status_code == 503
        assert (
            stack.query("SELECT is_active FROM users WHERE id=%s", (user["id"],))[0]["is_active"]
            == 1
        )
        # API: 레이트 리밋·refresh 저장소가 Redis 다 — 내부 정보 없는 5xx(fail-closed, residual R-005).
        # 처리되지 않은 예외라 uvicorn 이 응답 뒤 연결을 닫는다 — 요청마다 새 연결을 쓴다(관측값은 NOTES).
        with client(stack) as c:
            login = c.post(
                "/api/v1/auth/login",
                data={"username": user["username"], "password": user["password"]},
            )
        _no_internals(login)
        with client(stack) as c:
            refresh = c.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh"]})
        _no_internals(refresh)
        NOTES["Redis 정지 · API 로그인/refresh"] = (
            f"{login.status_code} {login.json()['error_code']} / {refresh.status_code} "
            f"{refresh.json()['error_code']} — 처리되지 않은 redis ConnectionError, 응답 뒤 연결 종료"
        )
        with client(stack) as c:
            assert (
                c.get("/api/v1/blog/posts").status_code == 200
            )  # Redis 를 쓰지 않는 조회는 그대로
        with client(stack) as c:
            assert c.get("/health").status_code == 200
        assert _ready(stack) == 503
    finally:
        stack.start_service("redis")
    _wait(lambda: _ready(stack) == 200)
    with client(stack) as c:
        assert (
            c.post(
                "/api/v1/auth/login",
                data={"username": user["username"], "password": user["password"]},
            ).status_code
            == 200
        )
    admin.close()
    _admin(stack).close()  # 새 로그인으로 관리 화면도 회복
    cover("fault", "redis", "stop-start")


def test_worker_down_does_not_affect_api_and_backlog_runs_after_restart(stack, cover):
    stack.stop_worker()
    try:
        user = new_user(stack)
        with client(stack, user["access"]) as c:
            assert (
                c.post("/api/v1/blog/posts", json={"title": "t", "content": "c"}).status_code == 201
            )
        pending = Celery("e2e", broker=stack.redis_url, backend=stack.redis_url).send_task(
            "home.aggregate_access_stats"
        )
        time.sleep(2)
        assert pending.state == "PENDING"
    finally:
        stack.start_worker()
    assert pending.get(timeout=60)["total"] >= 0
    cover("fault", "worker", "stop-start")


def test_replica_down_and_back(stack, cover):
    """replica 가 없으면 읽기(replica 경로)는 실패한다 — 코드에 primary 대체가 없다. 쓰기와 /ready 는 primary 만 본다."""
    user = new_user(stack)
    stack.stop_service("mysql-replica")
    try:
        with client(stack, user["access"]) as c:
            _no_internals(c.get("/api/v1/blog/posts"))
            created = c.post("/api/v1/blog/posts", json={"title": "t", "content": "c"})
            assert created.status_code == 201
            assert (
                c.patch(
                    f"/api/v1/blog/posts/{created.json()['id']}", json={"title": "u"}
                ).status_code
                == 200
            )
        assert _ready(stack) == 200
    finally:
        stack.start_service("mysql-replica")
        stack.attach_replica()  # tmpfs 라 빈 서버로 돌아온다 — primary binlog 로 처음부터 다시 따라간다
        stack.wait_replica(timeout=120)
    with client(stack) as c:
        _wait(lambda: c.get(f"/api/v1/blog/posts/{created.json()['id']}").status_code == 200)
        assert c.get(f"/api/v1/blog/posts/{created.json()['id']}").json()["title"] == "u"
    cover("fault", "replica", "stop-start")


def test_primary_down_ready_503_health_200_and_clean_500(stack, cover):
    user = new_user(stack)
    stack.stop_service("mysql-primary")
    try:
        assert _ready(stack) == 503
        with client(stack, user["access"]) as c:
            assert c.get("/health").status_code == 200
            _no_internals(c.post("/api/v1/blog/posts", json={"title": "t", "content": "c"}))
    finally:
        # primary 데이터는 사라졌다(tmpfs). replica 도 비우고 처음부터 다시 세운다.
        stack.stop_app()
        stack.stop_worker()
        stack.stop_service("mysql-replica")
        stack.start_service("mysql-primary")
        stack.start_service("mysql-replica")
        stack.bootstrap_mysql(fresh_primary=True)
        stack.start_app()
        stack.start_worker()
    assert _ready(stack) == 200
    superuser(stack)
    cover("fault", "primary", "stop-start")
