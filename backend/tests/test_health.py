from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok_without_external_keys():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert body["data"] == {"status": "ok"}
