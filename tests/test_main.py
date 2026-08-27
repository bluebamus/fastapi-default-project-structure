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
