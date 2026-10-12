"""ADMIN_DISABLED=true — 관리 화면이 앱에서 흔적 없이 사라진다 (admin-login ADR-005).

각 보장을 **별도 프로세스**로 확인한다. 이 테스트 세션은 다른 테스트가 이미 ``main`` 을 (관리 화면을 켠 채)
import 해 두어 같은 프로세스에서는 판별할 수 없다.

1. ``/admin`` 이하 경로가 모두 404 — 마운트 자체가 없다.
2. 앱이 내보내는 응답(OpenAPI·``/docs``·공개 GET 경로·오류 본문·헤더) 어디에도 ``/admin`` 이 없다.
3. 기동 로그가 관리 화면 경로를 싣지 않는다.
4. sqladmin·인증 백엔드가 import 되지 않고 세션 미들웨어가 없다.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MARK = "PROBE="

_PROBE = r"""
import json, sys
import main
from fastapi.testclient import TestClient

client = TestClient(main.app, raise_server_exceptions=False)
admin_paths = ["/admin", "/admin/", "/admin/login", "/admin/statics/css/main.css"]
schema = client.get("/openapi.json").json()
public = sorted(
    {path for path, ops in schema["paths"].items() if "get" in ops and "{" not in path}
    | {"/", "/docs", "/openapi.json", "/no-such-path", "/admin"}
)
leaks = []
for path in public:
    response = client.get(path, follow_redirects=False)
    headers = " ".join(f"{k}: {v}" for k, v in response.headers.items())
    if "/admin" in response.text or "/admin" in headers:
        leaks.append(path)
print("PROBE=" + json.dumps({
    "status": {p: client.get(p, follow_redirects=False).status_code for p in admin_paths},
    "checked": public,
    "leaks": leaks,
    "sqladmin_loaded": "sqladmin" in sys.modules,
    "backend_loaded": "app.features.auth.admin_backend" in sys.modules,
    "session_middleware": [m.cls.__name__ for m in main.app.user_middleware if "Session" in m.cls.__name__],
    "has_admin": hasattr(main, "admin"),
}))
"""


def _run(code: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ADMIN_DISABLED": "true",
        "DEBUG": "true",  # /docs·/openapi.json 까지 열어 두고 본다
        "ACCESS_LOG_ENABLED": "false",
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="module")
def probe() -> dict:
    result = _run(_PROBE)
    line = next((ln for ln in result.stdout.splitlines() if ln.startswith(_MARK)), None)
    assert line, f"프로브 실행 실패\nstderr:\n{result.stderr[-3000:]}"
    return json.loads(line[len(_MARK) :])


def test_admin_paths_are_404(probe):
    assert probe["status"] == {
        "/admin": 404,
        "/admin/": 404,
        "/admin/login": 404,
        "/admin/statics/css/main.css": 404,
    }


def test_no_response_mentions_admin_path(probe):
    assert "/openapi.json" in probe["checked"] and "/docs" in probe["checked"]
    assert len(probe["checked"]) >= 10, "확인한 경로가 너무 적다 — 헛통과 방지"
    assert probe["leaks"] == []


def test_admin_layer_objects_are_not_created(probe):
    assert probe["sqladmin_loaded"] is False
    assert probe["backend_loaded"] is False
    assert probe["session_middleware"] == []
    assert probe["has_admin"] is False


def test_startup_log_does_not_mention_admin_path():
    result = _run("import main")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-3000:]
    assert "관리 화면 비활성화 (ADMIN_DISABLED=true)" in output
    assert "/admin" not in output
