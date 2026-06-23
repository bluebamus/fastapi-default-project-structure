from fastapi.testclient import TestClient


def test_create_app_registers_home_routes_and_health():
    from app.core.bootstrap import create_app
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert any(p.startswith("/api/v1/home") for p in paths)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
