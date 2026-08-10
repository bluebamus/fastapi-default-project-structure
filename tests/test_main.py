from fastapi.testclient import TestClient


def test_main_app_boots_and_serves_health():
    import main

    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    # OpenAPI 스키마는 공개 API 라 버전 간 안정적이다.
    paths = set(main.app.openapi()["paths"])
    assert any(p.startswith("/api/v1/home") for p in paths)
