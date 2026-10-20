"""L6 — 운영·기동: Alembic 왕복, create_superuser, 기동 거부, 로깅(형식·헤더·앱별 레벨·프로세스별 파일·회전·보관)."""

from __future__ import annotations

import re
import secrets
import socketserver
import subprocess  # noqa: S404
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.e2e.stack import DB_NAME, PORTS, ROOT
from tests.e2e.support import client

pytestmark = pytest.mark.e2e

LINE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} KST\] (DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"\[app=[\w.\-]+\] \[[^\]]*:[^\]]*:[^\]]*:\d+\] "
)


# ── 1. Alembic 왕복 ─────────────────────────────────────────────────────
def _schema(stack, schema: str) -> list[tuple]:
    cols = stack.query(
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY"
        " FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME, ORDINAL_POSITION",
        (schema,),
    )
    idx = stack.query(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME"
        " FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s"
        " ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
        (schema,),
    )
    return [tuple(r.values()) for r in cols] + [tuple(r.values()) for r in idx]


def test_alembic_upgrade_downgrade_upgrade_round_trip(stack, cover):
    url = f"mysql+pymysql://fastapi_e2e:{stack.db_password}@127.0.0.1:{PORTS['mysql-primary']}/{DB_NAME}_alembic"
    alembic = ["-m", "alembic", "-c", str(ROOT / "alembic.ini")]

    def run(*args: str):
        done = stack.run_tool("alembic-roundtrip", [*alembic, *args], ALEMBIC_DATABASE_URL=url)
        assert done.returncode == 0, done.stdout + done.stderr

    run("upgrade", "head")
    first = _schema(stack, f"{DB_NAME}_alembic")
    run("downgrade", "base")
    left = {r[0] for r in _schema(stack, f"{DB_NAME}_alembic")}
    assert left <= {"alembic_version"}, left
    run("upgrade", "head")
    assert _schema(stack, f"{DB_NAME}_alembic") == first
    assert _schema(stack, DB_NAME) == first  # 앱이 쓰는 스키마와도 같다
    cover("ops", "alembic", "round-trip")


# ── 2. create_superuser ─────────────────────────────────────────────────
def test_create_superuser_create_promote_and_reject(stack, cover):
    name, password = f"ops-{secrets.token_hex(4)}", secrets.token_urlsafe(16)
    stack.secrets.add(password)
    base = ["-m", "scripts.create_superuser", "--username", name]
    created = stack.run_tool(
        "superuser-new",
        [*base, "--email", f"{name}@example.com", "--password-stdin"],
        stdin=password + "\n",
    )
    assert created.returncode == 0 and "만들었습니다" in created.stdout, (
        created.stdout + created.stderr
    )
    row = stack.query("SELECT is_superuser, hashed_password FROM users WHERE username=%s", (name,))[
        0
    ]
    assert row["is_superuser"] == 1 and row["hashed_password"].startswith("$argon2id$")

    stack.execute("UPDATE users SET is_superuser=0 WHERE username=%s", (name,))
    again = stack.run_tool("superuser-promote", base)
    assert again.returncode == 0 and "승격" in again.stdout, again.stdout + again.stderr
    assert (
        stack.query("SELECT is_superuser FROM users WHERE username=%s", (name,))[0]["is_superuser"]
        == 1
    )

    bad = stack.run_tool(
        "superuser-bad",
        [
            "-m",
            "scripts.create_superuser",
            "--username",
            f"x-{name}",
            "--email",
            "not-an-email",
            "--password-stdin",
        ],
        stdin="short\n",
    )
    assert bad.returncode == 1 and "email" in bad.stderr, bad.stdout + bad.stderr
    cover("ops", "create_superuser", "create-promote-reject")


# ── 3. 기동 거부 ─────────────────────────────────────────────────────────
def _refused(stack, name: str, argv: list[str], expect: str, **env: str) -> None:
    proc = stack.spawn(name, argv, **env)
    try:
        code = proc.wait(timeout=90)
    except subprocess.TimeoutExpired:
        code = None  # 거부하지 않고 떠 버렸다 — 아래에서 실패로 드러낸다
    finally:
        proc.stop()
        stack.procs.remove(proc)
    out = proc.output
    assert code not in (None, 0), out
    assert expect in out, out


UVICORN = ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORTS["app"])]


def test_startup_refuses_undeclared_route(stack, cover):
    _refused(
        stack,
        "refuse-policy",
        [
            "-m",
            "uvicorn",
            "tests.e2e.apps.undeclared_route:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORTS["app"]),
        ],
        "GET /api/e2e-undeclared: 접근 수준 선언 없음",
    )
    cover("ops", "startup-refusal", "access-policy")


def test_startup_refuses_legacy_admin_variable(stack, cover):
    _refused(
        stack,
        "refuse-legacy-admin",
        UVICORN,
        "설정 ADMIN 은 ADMIN_DISABLED 로 바뀌었습니다",
        ADMIN="false",
    )
    cover("ops", "startup-refusal", "legacy-ADMIN")


@pytest.mark.parametrize(
    ("env", "expect"),
    [
        ({"ADMIN_SESSION_IDLE_SECONDS": "30"}, "ADMIN_SESSION_IDLE_SECONDS"),
        (
            {"ADMIN_SESSION_IDLE_SECONDS": "7200", "ADMIN_SESSION_MAX_AGE_SECONDS": "3600"},
            "ADMIN_SESSION_IDLE_SECONDS 는 ADMIN_SESSION_MAX_AGE_SECONDS 이하여야 합니다",
        ),
    ],
    ids=["idle-below-minimum", "idle-above-max-age"],
)
def test_startup_refuses_bad_admin_session_settings(stack, cover, env, expect):
    _refused(stack, "refuse-admin-session", UVICORN, expect, **env)
    cover("ops", "startup-refusal", "ADMIN_SESSION_*")


class _OldRedis(socketserver.BaseRequestHandler):
    """``INFO`` 에 ``redis_version:6.0.0`` 으로 답하는 최소 RESP 서버(그 밖의 명령은 +OK/+PONG).

    fakeredis 는 ``INFO`` 를 지원하지 않아 앱이 "확인 불가 → 경고 후 계속" 경로로 빠진다 — 버전 미달
    거부를 보려면 버전을 실제로 말하는 서버가 필요하다.
    """

    def handle(self) -> None:
        reader = self.request.makefile("rb")
        while True:
            header = reader.readline()
            if not header:
                return
            if not header.startswith(b"*"):
                continue
            args = []
            for _ in range(int(header[1:])):
                size = int(reader.readline()[1:])
                args.append(reader.read(size + 2)[:-2].upper())
            if args and args[0] == b"INFO":
                body = b"# Server\r\nredis_version:6.0.0\r\n"
                self.request.sendall(b"$%d\r\n%s\r\n" % (len(body), body))
            elif args and args[0] == b"PING":
                self.request.sendall(b"+PONG\r\n")
            else:
                self.request.sendall(b"+OK\r\n")


def test_startup_refuses_redis_below_minimum_version(stack, cover):
    """Redis 자리에 6.0.0 이라고 답하는 서버를 둔다 — 앱은 GETDEL(6.2) 이 없는 서버로 뜨지 않는다."""
    stack.stop_app()
    stack.stop_worker()
    stack.stop_service("redis")
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    fake = socketserver.ThreadingTCPServer(("127.0.0.1", PORTS["redis"]), _OldRedis)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    try:
        _refused(stack, "refuse-redis-version", UVICORN, "최소 6.2.0 이상이 필요하다")
    finally:
        fake.shutdown()
        fake.server_close()
        stack.start_service("redis")
        stack.start_app()
        stack.start_worker()
    cover("ops", "startup-refusal", "redis-min-version")


# ── 4. 로깅 ─────────────────────────────────────────────────────────────
def _project_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[20")]


def test_every_run_path_uses_the_same_format_and_headers(stack, cover):
    """uvicorn CLI(앱)·``python main.py``(run_server)·Celery worker 의 모든 로그 줄이 같은 형식이다."""
    stack.stop_app()
    run_server = stack.spawn(
        "app-main-py",
        [str(ROOT / "main.py")],
        SERVER_HOST="127.0.0.1",
        SERVER_PORT=str(PORTS["app"]),
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(stack.base_url + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
    finally:
        run_server.stop()
        stack.procs.remove(run_server)
        stack.start_app()
    outputs = {
        "uvicorn CLI": next(p for p in stack.run_dir.glob("*-app.log")).read_text(encoding="utf-8"),
        "python main.py": run_server.output,
        "celery worker": stack.worker.output,
    }
    for name, text in outputs.items():
        lines = _project_lines(text)
        assert lines, name
        bad = [line for line in lines if not LINE.match(line)]
        assert not bad, f"{name}: 형식이 다른 줄 {bad[:5]}"
    assert (
        "[app=uvicorn]" in outputs["uvicorn CLI"] and "[app=uvicorn]" in outputs["python main.py"]
    )
    assert "[app=celery]" in outputs["celery worker"]
    assert "Finished server process" in outputs["python main.py"]
    cover("logging", "format", "all-run-paths")


def test_per_app_levels_drop_only_that_header(stack, cover):
    with stack.app_with(LOG_APP_LEVELS="uvicorn=WARNING") as proc:
        for _ in range(3):
            httpx.get(stack.base_url + "/health", timeout=5)
        with client(stack) as c:
            c.get("/api/v1/blog/posts")
        time.sleep(1)
        out = proc.output
    assert (
        '"GET /health' not in out and '"GET /api/v1/blog/posts' not in out
    )  # uvicorn INFO 접속 줄이 빠졌다
    assert re.search(r"INFO\s+\[app=core\]", out)  # 다른 헤더의 INFO 는 그대로
    cover("logging", "app-levels", "LOG_APP_LEVELS")


def test_process_files_are_separate(stack, cover):
    logs = stack.app_log_dir
    app_log = (logs / "app.log").read_text(encoding="utf-8")
    celery_log = (logs / "celery.log").read_text(encoding="utf-8")
    assert "[app=uvicorn]" in app_log and "[app=celery]" not in app_log
    assert "[app=celery]" in celery_log and "[app=uvicorn]" not in celery_log
    error_log = (logs / "error.log").read_text(encoding="utf-8")  # 장애 주입(L5)이 남긴 ERROR
    assert error_log and all(
        re.search(r"\] (ERROR|CRITICAL)\s", line) for line in _project_lines(error_log)
    )
    cover("logging", "files", "per-process")


def test_size_rotation_and_retention(stack, cover):
    rot = stack.run_dir / "rotation"
    rot.mkdir()
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    expired = rot / "app.log.2000-01-01"
    recent = rot / f"app.log.{today - timedelta(days=1)}"
    expired.write_text("old\n", encoding="utf-8")
    recent.write_text("recent\n", encoding="utf-8")
    with stack.app_with(LOG_DIR=str(rot), LOG_MAX_SIZE_MB="1", LOG_RETENTION_DAYS="30"):
        filler = "x" * 1800
        with httpx.Client(base_url=stack.base_url, timeout=30) as c:
            for i in range(800):
                c.get(f"/rotation-{i}?pad={filler}")
        time.sleep(2)
    rotated = sorted(p.name for p in rot.glob(f"app.log.{today}*"))
    assert rotated, sorted(p.name for p in rot.iterdir())
    assert all(p.stat().st_size <= 1024 * 1024 for p in rot.glob("app.log*"))
    assert not expired.exists(), "보관 일수(30)를 넘긴 회전 파일이 남아 있다"
    assert recent.exists(), "보관 일수 안의 회전 파일이 지워졌다"
    cover("logging", "files", "rotation-retention")


# ── 5. CSRF 본문 버퍼링 상한(측정) ───────────────────────────────────────
def test_admin_csrf_form_body_over_10_mib_is_413(stack, cover):
    with client(stack) as c:
        c.get("/admin/login")  # 세션에 CSRF 토큰이 생겨야 본문을 읽는다
        body = "username=a&password=" + "x" * (10 * 1024 * 1024 + 1)
        resp = c.post(
            "/admin/login",
            content=body,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
    assert resp.status_code == 413
    cover("admin-auth", "csrf", "body-cap-413")
