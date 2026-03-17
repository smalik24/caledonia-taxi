import pytest

async def test_login_correct_password(client):
    r = await client.post("/admin/login", json={"password": "admin1234"})
    assert r.status_code == 200
    assert "admin_session" in r.cookies

async def test_login_wrong_password(client):
    r = await client.post("/admin/login", json={"password": "wrong"})
    assert r.status_code == 401

async def test_admin_stats_requires_auth(client):
    r = await client.get("/api/admin/stats")
    assert r.status_code == 401

async def test_admin_stats_with_valid_session(client):
    login = await client.post("/admin/login", json={"password": "admin1234"})
    token = login.cookies["admin_session"]
    r = await client.get("/api/admin/stats", cookies={"admin_session": token})
    assert r.status_code == 200

async def test_logout_clears_cookie(client):
    login = await client.post("/admin/login", json={"password": "admin1234"})
    token = login.cookies["admin_session"]
    logout = await client.get("/admin/logout", cookies={"admin_session": token})
    assert logout.status_code == 200
    r = await client.get("/api/admin/stats")
    assert r.status_code == 401
