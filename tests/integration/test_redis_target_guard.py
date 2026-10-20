"""Redis 가 필요한 통합 테스트는 접속 대상을 **명시해야만** 돈다 (integration-e2e W0).

예전에는 ``REDIS_PORT`` 가 없으면 기본값 6379 로 붙었다. 그 포트에 남의 Redis 가 떠 있으면
테스트가 그 Redis 에 접속했다(실제 사고). 테스트가 띄운 자식 서버는 저장소 ``.env`` 의
Redis 를 따랐다. 두 경로 모두 "어디에 붙는지" 를 테스트가 정하지 못했다.

- 변수가 없으면 skip 이 아니라 **실패**한다 — skip 은 초록으로 읽힌다.
- 변수가 있는데 닿지 않을 때만 기존 정책(skip)을 따른다.
- 자식 서버는 fixture 가 확인한 대상을 env 로 받는다 — ``.env`` 가 바꾸지 못한다.
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess  # noqa: S404 - 하위 pytest 를 실제로 돌려 결과 집계를 본다
import sys

from tests.integration.test_uvicorn_lifecycle import ServerProcess

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
LIFECYCLE = "tests/integration/test_uvicorn_lifecycle.py"


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])  # 닫힌 뒤 반환 — 아무도 listen 하지 않는다


def _run_lifecycle(env_overrides: dict[str, str | None]) -> str:
    env = os.environ.copy()
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    env["PYTHONIOENCODING"] = "utf-8"
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", LIFECYCLE, "-q", "-p", "no:cacheprovider", "-rA"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    return done.stdout + done.stderr


def test_missing_redis_port_fails_instead_of_defaulting_to_6379() -> None:
    out = _run_lifecycle({"REDIS_PORT": None, "REDIS_HOST": "127.0.0.1"})

    assert "3 errors" in out, out
    assert "skipped" not in out, out
    assert "REDIS_PORT" in out, out


def test_missing_redis_host_fails_too() -> None:
    out = _run_lifecycle({"REDIS_PORT": str(_closed_port()), "REDIS_HOST": None})

    assert "3 errors" in out, out
    assert "REDIS_HOST" in out, out


def test_explicit_but_unreachable_target_keeps_the_skip_policy() -> None:
    out = _run_lifecycle({"REDIS_PORT": str(_closed_port()), "REDIS_HOST": "127.0.0.1"})

    assert "3 skipped" in out, out
    assert "error" not in out.strip().splitlines()[-1], out


def test_child_server_gets_the_checked_target_not_the_inherited_one(monkeypatch) -> None:
    """부모 env(또는 .env)에 다른 값이 있어도 자식은 fixture 가 확인한 대상을 받는다."""
    monkeypatch.setenv("REDIS_HOST", "somebody-else")
    monkeypatch.setenv("REDIS_PORT", "6379")
    # 부모에 비밀번호가 없으면 자식도 빈 값이다 — .env 의 REDIS_PASSWORD 가 끼어들지 못한다.
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    proc = ServerProcess(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ['REDIS_HOST'], os.environ['REDIS_PORT'], "
            "repr(os.environ['REDIS_PASSWORD']))",
        ],
        port=_closed_port(),
        redis_target=("127.0.0.1", 16391),
    )
    assert proc.wait_for_exit(30) == 0
    assert proc.output.strip() == "127.0.0.1 16391 ''", proc.output
