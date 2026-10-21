"""L6 — 운영·기동: Alembic 왕복, create_superuser, 기동 거부, 로깅(형식·헤더·앱별 레벨·프로세스별 파일·회전·보관)."""

from __future__ import annotations

import re
import secrets
import socket
import socketserver
import subprocess  # noqa: S404
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from tests.e2e.stack import DB_NAME, PORTS, ROOT
from tests.e2e.support import NOTES, client

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
    # import 중 줄도 프로세스 파일에 남고(F-003, ADR-011), 파일 핸들러가 두 번 붙어 겹치지 않는다.
    routing = "[database] 라우팅 구성"
    for text in (app_log, celery_log):
        lines = text.splitlines()
        assert any(routing in line for line in lines)
        assert not any(routing in a and a == b for a, b in zip(lines, lines[1:], strict=False))
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


# ── 5. CSRF 본문 버퍼링 상한(integration-e2e ADR-015) ─────────────────────────
MIB = 1024 * 1024


def _app_memory(stack) -> tuple[int, int]:
    """앱(uvicorn) 프로세스의 (현재 RSS, 최대 RSS) 바이트 — 측정 기록용.

    Windows 의 venv ``python.exe`` 는 실제 인터프리터를 자식으로 띄우는 런처라 ``popen.pid`` 가 아니라 앱 포트를
    듣는 프로세스를 잰다.
    """
    if sys.platform == "win32":
        netstat = subprocess.run(  # noqa: S603, S607
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=True
        ).stdout
        pid = next(
            line.split()[-1]
            for line in netstat.splitlines()
            if f"127.0.0.1:{PORTS['app']} " in line and "LISTENING" in line
        )
        out = subprocess.run(  # noqa: S603, S607
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'$p = Get-Process -Id {pid}; "$($p.WorkingSet64) $($p.PeakWorkingSet64)"',
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        return int(out[0]), int(out[1])
    status = Path(f"/proc/{stack.app.popen.pid}/status").read_text()
    kib = dict(re.findall(r"^(VmRSS|VmHWM):\s+(\d+) kB", status, re.MULTILINE))
    return int(kib["VmRSS"]) * 1024, int(kib["VmHWM"]) * 1024


def _mib(value: int) -> str:
    return f"{value / MIB:+.1f} MiB"


def test_admin_csrf_body_and_field_caps(stack, cover):
    """10 MiB 초과 본문 413(Content-Length 로 먼저, 없으면 읽는 도중), 1 MiB 초과 필드 400 — 500·연결 종료 없음."""
    form = {"content-type": "application/x-www-form-urlencoded"}
    asgi_errors = stack.app.output.count("Exception in ASGI application")
    with client(stack) as c:
        c.get("/admin/login")  # 세션에 CSRF 토큰이 생겨야 본문을 읽는다
        sid = c.cookies.get("admin_session")
        base_rss, base_peak = _app_memory(stack)

        # ① Content-Length 가 10 MiB 를 넘으면 본문을 한 바이트도 보내기 전에 413 이다.
        with socket.create_connection(("127.0.0.1", PORTS["app"]), timeout=30) as raw:
            raw.sendall(
                (
                    "POST /admin/login HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    f"Content-Type: application/x-www-form-urlencoded\r\n"
                    f"Content-Length: {10 * MIB + 1}\r\nCookie: admin_session={sid}\r\n\r\n"
                ).encode()
            )
            head = raw.recv(4096).decode("latin-1")
        assert head.startswith("HTTP/1.1 413 "), head
        declared_rss, declared_peak = _app_memory(stack)

        # ② Content-Length 없이(chunked) 10 MiB 를 넘기면 읽는 도중 누적 크기로 413 이다.
        def chunks():
            for _ in range(10):
                yield b"x" * MIB
            yield b"x" * 1024

        streamed = c.post("/admin/login", content=chunks(), headers=form)
        assert streamed.status_code == 413
        streamed_rss, streamed_peak = _app_memory(stack)

        # ③ 1 MiB 를 넘는 필드 하나는 400 이고 연결은 유지된다(다음 요청을 같은 연결로 보낸다).
        big = c.post(
            "/admin/login",
            content=b"username=a&password=" + b"x" * (MIB + 1),
            headers=form,
        )
        assert big.status_code == 400, big.text
        assert big.headers.get("connection", "").lower() != "close"
        assert c.get("/admin/login").status_code == 200
        field_rss, field_peak = _app_memory(stack)
    assert stack.app.output.count("Exception in ASGI application") == asgi_errors
    NOTES["CSRF 상한 · 앱 RSS(기준 대비 현재/최대)"] = (
        f"Content-Length 413 {_mib(declared_rss - base_rss)}/{_mib(declared_peak - base_peak)}, "
        f"chunked 10 MiB+1 KiB 413 {_mib(streamed_rss - base_rss)}/{_mib(streamed_peak - base_peak)}, "
        f"필드 1 MiB+1 400 {_mib(field_rss - base_rss)}/{_mib(field_peak - base_peak)}"
    )
    cover("admin-auth", "csrf", "body-cap-413")
    cover("admin-auth", "csrf", "field-cap-400")
