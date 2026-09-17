def test_health_check_returns_ok(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_returns_404(client):
    response = client.get("/not-a-real-endpoint")

    assert response.status_code == 404
