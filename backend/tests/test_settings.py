def test_the_settings_hold_the_approval_limit(client):
    assert client.get("/api/settings").json() == {"current": {"approval_limit": 1000.0}}
