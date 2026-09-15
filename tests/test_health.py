def test_health_check_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_does_not_require_api_key(client):
    # No X-API-Key header at all -- /health must stay open for load balancer / uptime checks.
    response = client.get("/health", headers={})
    assert response.status_code == 200
