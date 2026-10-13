import os
import pathlib
import subprocess
import sys

from fastapi.testclient import TestClient


def test_main_app_boots_and_serves_health():
    import main

    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    # OpenAPI 스키마는 공개 API 라 버전 간 안정적이다.
    paths = set(main.app.openapi()["paths"])
    assert any(p.startswith("/api/v1/home") for p in paths)


def test_run_server_passes_the_project_log_config(monkeypatch):
    """진입점이 uvicorn 에 프로젝트 log_config 를 넘긴다 (ADR-020).

    ``log_config`` 은 uvicorn 이 문서화한 공식 파라미터다. 이 배선이 끊겨도 서버는
    정상 기동하므로 다른 어떤 테스트도 잡지 못한다 — uvicorn 로그만 조용히 기본
    포맷으로 돌아간다. Wave 7 의 subprocess 테스트가 정상 앱과 startup 실패 앱을
    **같은 경로로** 띄우기 위해 대상 앱을 인자로 받는다.
    """
    import uvicorn

    import main
    from app.utils.logs import setup_uvicorn_logging

    captured: dict = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda target, **kwargs: captured.update(kwargs, target=target)
    )

    main.run_server()
    assert captured["target"] == "main:app"
    assert captured["log_config"] == setup_uvicorn_logging()

    main.run_server("other.module:app")
    assert captured["target"] == "other.module:app"


_UNDECLARED_ROUTE_PROBE = """
from app.features import home

@home.router.get("/v1/home/undeclared")
async def undeclared() -> None:
    return None

import main
"""


def test_main_refuses_to_start_when_a_view_declares_no_access_level():
    """앱 조립 경로(main 모듈)가 가드를 실제로 부른다 — 선언 없는 뷰가 하나라도 끼면 import 가 실패한다.

    ``main`` 은 모듈 수준에서 조립되므로 별도 프로세스에서 라우터에 뷰를 하나 더한 뒤 import 한다
    (이 세션의 ``main`` 은 이미 조립이 끝났다). 조립 끝의 ``AccessPolicyGuard().verify(app)`` 를 지우면
    import 가 성공해 이 테스트가 실패한다.
    """
    result = subprocess.run(
        [sys.executable, "-c", _UNDECLARED_ROUTE_PROBE],
        cwd=pathlib.Path(__file__).resolve().parent.parent,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert result.returncode != 0
    assert "AccessPolicyError" in result.stderr
    assert "GET /api/v1/home/undeclared: 접근 수준 선언 없음" in result.stderr
