"""SNS 최소 API 엔드포인트 테스트 (AppRegistry 자동 등록 포함)."""
from fastapi.testclient import TestClient

from app.core.bootstrap import create_app

app = create_app()
client = TestClient(app)


def test_sns_auto_registered():
    """config.py 만으로 sns 라우터가 자동 발견·마운트된다."""
    paths = {r.path for r in app.routes}
    assert "/api/v1/sns/ping" in paths
    assert "/api/v1/sns/echo" in paths


def test_sns_ping():
    resp = client.get("/api/v1/sns/ping")
    assert resp.status_code == 200
    assert resp.json() == {"app": "sns", "status": "ok"}


def test_sns_echo():
    resp = client.post("/api/v1/sns/echo", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"app": "sns", "message": "hello"}


def test_sns_echo_rejects_empty_message():
    resp = client.post("/api/v1/sns/echo", json={"message": ""})
    assert resp.status_code == 422


def test_sns_echo_rejects_missing_message():
    resp = client.post("/api/v1/sns/echo", json={})
    assert resp.status_code == 422
