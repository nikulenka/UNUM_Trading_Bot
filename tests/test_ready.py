import pytest

from app.api import ready as ready_module


@pytest.mark.smoke
def test_ready_returns_200_when_dependency_is_available(client, monkeypatch):
    monkeypatch.setattr(ready_module, "is_database_connected", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.smoke
def test_ready_returns_503_when_dependency_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(ready_module, "is_database_connected", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database not ready"