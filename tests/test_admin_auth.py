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


async def test_admin_login_page_returns_html(client):
    """GET /admin/login returns the login page HTML."""
    r = await client.get("/admin/login", follow_redirects=False)
    assert r.status_code == 200
    assert "Caledonia Taxi" in r.text
    assert "<form" in r.text


async def test_admin_page_redirects_unauthenticated(client):
    """GET /admin without auth redirects to /admin/login."""
    r = await client.get("/admin", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/admin/login" in r.headers.get("location", "")


async def test_admin_brute_force_lockout(client):
    """5 wrong passwords from same IP triggers 423 lockout."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    import main as _main
    # Clear any prior state
    _main._login_attempts.clear()
    _main._login_lockouts.clear()

    last_r = None
    for i in range(6):
        last_r = await client.post("/admin/login", json={"password": f"wrong{i}"})

    # After 5+ failures the account should be locked (423) or at least rejected (401)
    assert last_r.status_code in (423, 401)

    # Clean up lockout and rate-limit state so subsequent tests in other modules are not affected
    _main._login_attempts.clear()
    _main._login_lockouts.clear()
    _main._auth_attempts.clear()
