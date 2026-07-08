from fastapi.testclient import TestClient


def test_main_app_boots_and_serves_health():
    import main

    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    paths = {r.path for r in main.app.routes}
    assert any(p.startswith("/api/v1/home") for p in paths)
