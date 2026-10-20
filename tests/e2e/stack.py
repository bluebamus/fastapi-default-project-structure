"""E2E 스택 — compose(MySQL primary·replica, Redis) + 실제 uvicorn·Celery 하위 프로세스 (integration-e2e W2).

한 실행이 하는 일:

1. 고정 포트(§0 표)가 비어 있는지 본다 — 점유돼 있으면 남의 서버다. 멈춘다.
2. 실행마다 비밀값(DB·JWT·세션 키·슈퍼유저 비밀번호)을 새로 만든다.
3. ``compose.e2e.yaml`` 을 ``-p itest-default`` 로 띄우고 GTID 복제를 붙인다.
4. 앱·워커에 줄 모든 DSN·Redis URL 의 host 가 127.0.0.1 이고 포트가 표의 값인지 검사한다.
5. Alembic upgrade → 슈퍼유저 생성 → uvicorn(앱) · Celery worker 기동.

자식 프로세스는 **빈 작업 디렉터리**에서 띄운다. 설정은 작업 디렉터리의 ``.env`` 를 읽으므로,
저장소에서 띄우면 개발자의 ``.env`` 가 접속 대상을 바꾼다(W0 와 같은 사고). 필요한 값은 전부
환경 변수로 넘기고 ``ENV=development`` 로 띄워 배포 설정 검사(예시 비밀값·짧은 키)도 실제로 돈다.

Docker 는 PATH 에 있으면 그대로, 없고 Windows 면 WSL 안의 docker 를 쓴다. WSL 은 붙잡는
프로세스가 없으면 VM 이 내려가며 컨테이너를 죽이므로 실행 동안 keepalive 를 띄운다.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess  # noqa: S404 - 하네스가 의도적으로 실제 프로세스를 띄운다
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pymysql

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "itest-default"
COMPOSE_FILE = "compose.e2e.yaml"
HOST = "127.0.0.1"
# 계획서 §0 의 default 행. 여기 말고 다른 곳에 포트를 적지 않는다.
PORTS = {"mysql-primary": 13321, "mysql-replica": 13322, "redis": 16391, "app": 18091}
DB_NAME = "fastapi_e2e"
DB_USER = "fastapi_e2e"
SUPERUSER = "e2e-admin"
INHERITED_ENV = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "LANG",
        "LC_ALL",
        "VIRTUAL_ENV",
        "USERNAME",
        "USER",
        "LOGNAME",
    }
)
READY_TIMEOUT = 90.0
STOP_TIMEOUT = 30.0


class StackError(RuntimeError):
    """스택을 안전하게 세울 수 없다 — 테스트를 진행하지 않는다."""


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=0.5):
            return True
    except OSError:
        return False


def _secret() -> str:
    return secrets.token_urlsafe(32)  # 43자 — 설정 검사의 최소 32자를 넘는다


def check_targets(env: dict[str, str]) -> None:
    """모든 접속 대상이 127.0.0.1 + 표의 포트인지 본다. 아니면 ``StackError``.

    대상: MySQL writer·replica, Redis, (있으면) ALEMBIC_DATABASE_URL. 남의 DB·Redis 에 붙는 순간
    데이터를 지우는 스위트라 하나라도 어긋나면 시작하지 않는다.
    """
    targets = [
        ("MYSQL_HOST/PORT", env["MYSQL_HOST"], int(env["MYSQL_PORT"]), PORTS["mysql-primary"]),
        ("REDIS_HOST/PORT", env["REDIS_HOST"], int(env["REDIS_PORT"]), PORTS["redis"]),
    ]
    for entry in json.loads(env.get("MYSQL_REPLICA_HOSTS", "[]")):
        host, _, port = entry.rpartition(":")
        targets.append(("MYSQL_REPLICA_HOSTS", host, int(port), PORTS["mysql-replica"]))
    if env.get("ALEMBIC_DATABASE_URL"):
        url = urlsplit(env["ALEMBIC_DATABASE_URL"])
        targets.append(
            ("ALEMBIC_DATABASE_URL", url.hostname or "", url.port or 0, PORTS["mysql-primary"])
        )
    bad = [
        f"{name}={host}:{port}"
        for name, host, port, want in targets
        if host != HOST or port != want
    ]
    if bad:
        raise StackError("접속 대상이 E2E 전용 스택이 아니다 — 중단: " + ", ".join(bad))


class Proc:
    """자식 프로세스 하나. 출력은 실행 디렉터리의 파일로 남긴다(CI artifact·비밀값 grep 대상)."""

    def __init__(self, name: str, argv: list[str], env: dict[str, str], cwd: Path, log: Path):
        self.name = name
        self.log = log
        self._file = log.open("w", encoding="utf-8", errors="replace")
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self.popen = subprocess.Popen(  # noqa: S603
            argv, cwd=cwd, env=env, stdout=self._file, stderr=subprocess.STDOUT, **kwargs
        )

    @property
    def output(self) -> str:
        if not self._file.closed:
            self._file.flush()
        return self.log.read_text(encoding="utf-8", errors="replace")

    def alive(self) -> bool:
        return self.popen.poll() is None

    def wait(self, timeout: float) -> int:
        try:
            return self.popen.wait(timeout=timeout)
        finally:
            self._file.flush()

    def stop(self) -> int | None:
        """정상 종료 신호(Windows CTRL_BREAK, POSIX SIGTERM) → 시간 안에 안 끝나면 kill."""
        if self.popen.poll() is None:
            graceful = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM
            self.popen.send_signal(graceful)
            try:
                self.popen.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                self.popen.kill()
                self.popen.wait(timeout=STOP_TIMEOUT)
        self._file.close()
        return self.popen.returncode


class Stack:
    """E2E 스택의 수명·접속 정보·자식 프로세스를 한곳에서 관리한다."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.work_dir = run_dir / "cwd"  # .env 가 없는 작업 디렉터리
        self.app_log_dir = run_dir / "applogs"
        for path in (self.work_dir, self.app_log_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.wsl = shutil.which("docker") is None
        if self.wsl and not (sys.platform == "win32" and shutil.which("wsl")):
            raise StackError("docker 를 찾지 못했다(PATH 에도 WSL 에도 없음)")
        self.root_password = _secret()
        self.db_password = _secret()
        self.repl_password = secrets.token_urlsafe(24)  # 복제 계정 비밀번호는 최대 32자
        self.superuser_password = _secret()
        self.env = {
            "ENV": "development",
            "DEBUG": "false",
            "ADMIN_DISABLED": "false",
            "TIME_ZONE": "Asia/Seoul",
            "MYSQL_HOST": HOST,
            "MYSQL_PORT": str(PORTS["mysql-primary"]),
            "MYSQL_USER": DB_USER,
            "MYSQL_PASSWORD": self.db_password,
            "MYSQL_DATABASE": DB_NAME,
            "DB_ROUTER_ENABLED": "true",
            "DB_REPLICATION_ENABLED": "true",
            "DB_READ_STICKY_AFTER_WRITE": "true",
            "MYSQL_REPLICA_HOSTS": json.dumps([f"{HOST}:{PORTS['mysql-replica']}"]),
            "REDIS_HOST": HOST,
            "REDIS_PORT": str(PORTS["redis"]),
            "REDIS_DB": "0",
            "REDIS_PASSWORD": "",
            "ACCESS_TOKEN_SECRET_KEY": _secret(),
            "REFRESH_TOKEN_SECRET_KEY": _secret(),
            "SESSION_SECRET_KEY": _secret(),
            # 테스트 클라이언트마다 다른 X-Forwarded-For 를 실어 레이트 리밋 카운터를 나눈다.
            "TRUSTED_PROXY_HOPS": "1",
            "AUTH_LOGIN_WINDOW_SECONDS": "5",
            "AUTH_REGISTER_WINDOW_SECONDS": "5",
            "LOG_FILE_ENABLED": "true",
            "LOG_DIR": str(self.app_log_dir),
            "PYTHONPATH": str(ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # 실행 로그 어디에도 나오면 안 되는 값 — 테스트가 발급받은 토큰도 여기 더한다.
        self.secrets: set[str] = {
            self.root_password,
            self.db_password,
            self.repl_password,
            self.superuser_password,
            self.env["ACCESS_TOKEN_SECRET_KEY"],
            self.env["REFRESH_TOKEN_SECRET_KEY"],
            self.env["SESSION_SECRET_KEY"],
        }
        self.procs: list[Proc] = []
        self.app: Proc | None = None
        self.worker: Proc | None = None
        self._keepalive: subprocess.Popen | None = None
        self._serial = 0
        self.compose_up = False

    # ── docker ───────────────────────────────────────────────────────────
    def compose(self, *args: str, stdin: str | None = None, check: bool = True):
        compose_env = {
            "E2E_MYSQL_ROOT_PASSWORD": self.root_password,
            "E2E_MYSQL_PASSWORD": self.db_password,
        }
        base = ["docker", "compose", "-p", PROJECT, "-f", COMPOSE_FILE, *args]
        if self.wsl:
            argv = ["wsl", "-e", "env", *(f"{k}={v}" for k, v in compose_env.items()), *base]
            env = None
        else:
            argv, env = base, {**os.environ, **compose_env}
        done = subprocess.run(  # noqa: S603
            argv,
            cwd=ROOT,
            env=env,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if check and done.returncode != 0:
            raise StackError(
                f"docker compose {args[0]} 실패(exit={done.returncode}): {done.stderr[-2000:]}"
            )
        return done

    def sql(self, service: str, statement: str) -> str:
        """컨테이너 안의 mysql 클라이언트로 root 로 실행한다. 비밀번호는 컨테이너 환경에서 읽는다."""
        shell = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B'
        return self.compose("exec", "-T", service, "sh", "-c", shell, stdin=statement).stdout

    def stop_service(self, service: str) -> None:
        self.compose("stop", service)

    def start_service(self, service: str) -> None:
        self.compose("start", service)
        self.compose("up", "-d", "--wait", service)

    # ── 기동·정리 ────────────────────────────────────────────────────────
    def preflight(self) -> None:
        busy = [f"{name}:{port}" for name, port in PORTS.items() if _port_open(port)]
        if busy:
            raise StackError("E2E 포트가 이미 쓰이고 있다(남의 서버) — 중단: " + ", ".join(busy))
        check_targets(self.env)

    def up(self) -> None:
        if self.wsl:
            # ponytail: 실행 길이를 모른다 — 6시간 붙잡고, 정리에서 반드시 끈다.
            self._keepalive = subprocess.Popen(  # noqa: S603
                ["wsl", "-e", "sleep", "21600"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self.compose_up = True
        self.compose("up", "-d", "--wait")
        unreachable = [f"{n}:{p}" for n, p in PORTS.items() if n != "app" and not _port_open(p)]
        if unreachable:
            raise StackError(
                "compose 는 떴는데 127.0.0.1 에서 닿지 않는다(WSL2 localhost 전달 확인) — "
                + ", ".join(unreachable)
            )
        self.bootstrap_mysql(fresh_primary=True)

    def down(self) -> None:
        for proc in list(self.procs):
            proc.stop()
        self.procs.clear()
        if self.compose_up:
            self.compose("down", check=False)  # tmpfs 라 -v 없이 전부 사라진다
            self.compose_up = False
        if self._keepalive is not None:
            self._keepalive.kill()
            self._keepalive.wait(timeout=STOP_TIMEOUT)
            self._keepalive = None

    # ── MySQL ────────────────────────────────────────────────────────────
    def bootstrap_mysql(self, *, fresh_primary: bool) -> None:
        """복제를 붙이고 스키마·슈퍼유저를 만든다.

        ``fresh_primary`` 면 primary 의 GTID·binlog 를 비우고 시작한다(entrypoint 가 남긴 것이 replica
        의 같은 객체와 충돌하지 않게). 그 뒤의 모든 변경(Alembic 포함)은 binlog 로 replica 에 간다.
        """
        if fresh_primary:
            self.sql(
                "mysql-primary",
                "RESET BINARY LOGS AND GTIDS;"
                "SET sql_log_bin=0;"
                f"CREATE USER IF NOT EXISTS 'repl'@'%' IDENTIFIED BY '{self.repl_password}';"
                "GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';"
                # L6 의 Alembic 왕복은 별도 스키마에서 한다(본 스키마를 지우지 않게).
                f"CREATE DATABASE IF NOT EXISTS {DB_NAME}_alembic;"
                f"GRANT ALL ON {DB_NAME}_alembic.* TO '{DB_USER}'@'%';"
                "SET sql_log_bin=1;",
            )
        self.attach_replica()
        if fresh_primary:
            self.run_tool(
                "alembic", ["-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"]
            )
            self.create_superuser()
        self.wait_replica()

    def attach_replica(self) -> None:
        self.sql(
            "mysql-replica",
            "STOP REPLICA; RESET REPLICA ALL; RESET BINARY LOGS AND GTIDS;"
            "CHANGE REPLICATION SOURCE TO SOURCE_HOST='mysql-primary', SOURCE_PORT=3306,"
            f" SOURCE_USER='repl', SOURCE_PASSWORD='{self.repl_password}',"
            " SOURCE_AUTO_POSITION=1, GET_SOURCE_PUBLIC_KEY=1;"
            "START REPLICA;",
        )

    def wait_replica(self, timeout: int = 60) -> None:
        executed = (
            self.sql("mysql-primary", "SELECT @@GLOBAL.gtid_executed;").strip().replace("\n", "")
        )
        if not executed:
            return
        waited = self.sql(
            "mysql-replica", f"SELECT WAIT_FOR_EXECUTED_GTID_SET('{executed}', {timeout});"
        ).strip()
        if waited != "0":
            status = self.sql("mysql-replica", "SHOW REPLICA STATUS\\G")
            raise StackError(f"replica 가 {timeout}초 안에 따라오지 못했다:\n{status[-3000:]}")

    def db(self, replica: bool = False) -> pymysql.connections.Connection:
        port = PORTS["mysql-replica" if replica else "mysql-primary"]
        return pymysql.connect(
            host=HOST,
            port=port,
            user=DB_USER,
            password=self.db_password,
            database=DB_NAME,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def query(self, sql: str, args: tuple = (), replica: bool = False) -> list[dict]:
        with self.db(replica) as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def execute(self, sql: str, args: tuple | list = ()) -> int:
        with self.db() as conn, conn.cursor() as cur:
            if args and isinstance(args, list):
                return cur.executemany(sql, args)
            return cur.execute(sql, args)

    # ── 자식 프로세스 ────────────────────────────────────────────────────
    def child_env(self, **overrides: str) -> dict[str, str]:
        # 부모 환경은 OS 가 프로세스를 띄우는 데 필요한 것만 물려준다 — 개발자 셸의 설정 변수
        # (LOG_*·ADMIN·TRUSTED_PROXY_HOPS 등)가 새면 실행마다 결과가 달라진다.
        env = {k: v for k, v in os.environ.items() if k.upper() in INHERITED_ENV}
        env.update(self.env)
        env.update(overrides)
        check_targets(env)
        return env

    def _log_path(self, name: str) -> Path:
        self._serial += 1
        return self.run_dir / f"{self._serial:02d}-{name}.log"

    def run_tool(self, name: str, args: list[str], stdin: str | None = None, **overrides: str):
        """끝나는 도구(alembic·create_superuser)를 실행한다. 출력은 실행 디렉터리에 남긴다."""
        done = subprocess.run(  # noqa: S603
            [sys.executable, *args],
            cwd=self.work_dir,
            env=self.child_env(**overrides),
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        self._log_path(name).write_text(done.stdout + done.stderr, encoding="utf-8")
        if done.returncode != 0 and name in ("alembic", "create_superuser"):
            raise StackError(
                f"{name} 실패(exit={done.returncode}):\n{(done.stdout + done.stderr)[-3000:]}"
            )
        return done

    def create_superuser(self) -> None:
        self.run_tool(
            "create_superuser",
            [
                "-m",
                "scripts.create_superuser",
                "--username",
                SUPERUSER,
                "--email",
                "e2e-admin@example.com",
                "--password-stdin",
            ],
            stdin=self.superuser_password + "\n",
        )

    def spawn(self, name: str, argv: list[str], **overrides: str) -> Proc:
        proc = Proc(
            name,
            [sys.executable, *argv],
            self.child_env(**overrides),
            self.work_dir,
            self._log_path(name),
        )
        self.procs.append(proc)
        return proc

    def start_app(self, **overrides: str) -> Proc:
        """uvicorn 을 앱 포트로 띄우고 /health 가 200 이 될 때까지 기다린다."""
        if _port_open(PORTS["app"]):
            raise StackError(f"앱 포트 {PORTS['app']} 가 이미 쓰이고 있다")
        proc = self.spawn(
            "app",
            [
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                HOST,
                "--port",
                str(PORTS["app"]),
                "--app-dir",
                str(ROOT),
            ],
            **overrides,
        )
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if not proc.alive():
                raise StackError(
                    f"앱이 기동 중에 끝났다(exit={proc.popen.returncode}):\n{proc.output[-4000:]}"
                )
            try:
                if httpx.get(self.base_url + "/health", timeout=1).status_code == 200:
                    self.app = proc
                    return proc
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise StackError(f"앱이 {READY_TIMEOUT:.0f}초 안에 준비되지 않았다:\n{proc.output[-4000:]}")

    def stop_app(self) -> None:
        if self.app is not None:
            self.app.stop()
            self.procs.remove(self.app)
            self.app = None

    @contextmanager
    def app_with(self, **overrides: str) -> Iterator[Proc]:
        """설정을 바꿔 앱을 다시 띄우고, 끝나면 기본 설정으로 되돌린다."""
        self.stop_app()
        try:
            yield self.start_app(**overrides)
        finally:
            self.stop_app()
            self.start_app()

    def start_worker(self) -> Proc:
        # Windows 에는 prefork(fork)가 없다 — solo 로 같은 태스크 코드를 돈다. Linux(CI)는 운영 기본값.
        pool = ["--pool=solo"] if sys.platform == "win32" else ["--pool=prefork", "--concurrency=1"]
        proc = self.spawn(
            "worker",
            ["-m", "celery", "-A", "app.celery.app:celery_app", "worker", "-l", "INFO", *pool],
        )
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if not proc.alive():
                raise StackError(f"worker 가 기동 중에 끝났다:\n{proc.output[-4000:]}")
            if " ready." in proc.output:
                self.worker = proc
                return proc
            time.sleep(0.2)
        raise StackError(f"worker 가 준비되지 않았다:\n{proc.output[-4000:]}")

    def stop_worker(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.procs.remove(self.worker)
            self.worker = None

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{PORTS['app']}"

    @property
    def redis_url(self) -> str:
        return f"redis://{HOST}:{PORTS['redis']}/0"
