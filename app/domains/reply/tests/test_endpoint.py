"""Reply 최소 API 엔드포인트 테스트 (AppRegistry 자동 등록 포함)."""
from fastapi.testclient import TestClient

from app.core.bootstrap import create_app

app = create_app()
client = TestClient(app)


def test_reply_auto_registered():
    """config.py 만으로 reply 라우터가 자동 발견·마운트된다."""
    paths = {r.path for r in app.routes}
    assert "/api/v1/reply/ping" in paths
    assert "/api/v1/reply/echo" in paths


def test_reply_ping():
    resp = client.get("/api/v1/reply/ping")
    assert resp.status_code == 200
    assert resp.json() == {"app": "reply", "status": "ok"}


def test_reply_echo():
    resp = client.post("/api/v1/reply/echo", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"app": "reply", "message": "hello"}


def test_reply_echo_rejects_empty_message():
    resp = client.post("/api/v1/reply/echo", json={"message": ""})
    assert resp.status_code == 422


def test_reply_echo_rejects_missing_message():
    resp = client.post("/api/v1/reply/echo", json={})
    assert resp.status_code == 422
