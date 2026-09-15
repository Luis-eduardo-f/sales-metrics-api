import pytest

PROTECTED_ENDPOINTS = ["/metrics/revenue", "/metrics/top-products", "/customers"]


@pytest.mark.parametrize("path", PROTECTED_ENDPOINTS)
def test_missing_api_key_returns_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


@pytest.mark.parametrize("path", PROTECTED_ENDPOINTS)
def test_invalid_api_key_returns_401(client, path):
    response = client.get(path, headers={"X-API-Key": "totally-wrong-key"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key."


@pytest.mark.parametrize("path", PROTECTED_ENDPOINTS)
def test_valid_api_key_returns_200(client, auth_headers, path):
    response = client.get(path, headers=auth_headers)
    assert response.status_code == 200


def test_customer_summary_also_requires_api_key(client):
    response = client.get("/customers/1/summary")
    assert response.status_code == 401
