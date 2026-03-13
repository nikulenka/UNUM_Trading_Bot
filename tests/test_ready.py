import pytest


@pytest.mark.smoke
def test_ready_returns_ready(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"