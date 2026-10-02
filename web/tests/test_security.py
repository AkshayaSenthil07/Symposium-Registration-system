"""Security basics: CSRF, headers, redirects, passwords, access control, lock-out, rate limiting."""
from webapp.security import hash_password, password_problems, safe_next, verify_password


def test_password_hashing():
    h = hash_password("Secret@123")
    assert h.startswith("pbkdf2_sha256$") and "Secret" not in h
    assert verify_password("Secret@123", h) and not verify_password("secret@123", h)
    assert hash_password("Secret@123") != h                     # random salt


def test_password_rules():
    assert password_problems("Secret@123") == []
    assert password_problems("short") and password_problems("alllowercase1")


def test_safe_next_blocks_open_redirects():
    assert safe_next("/me/") == "/me/"
    for bad in ("https://evil.com", "//evil.com", "/\\evil.com", None, ""):
        assert safe_next(bad) is None


def test_security_headers(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_csrf_required(client):
    r = client.c.post("/login", data={"email": "x@y.com", "password": "x"})
    assert r.status_code == 400


def test_participant_blocked_from_staff_and_admin(client, make_user):
    u = make_user()
    client.login(u["email"])
    assert client.get("/staff/").status_code == 403
    assert client.get("/admin/settings").status_code == 403


def test_role_matrix(app, make_user):
    from tests.conftest import Client
    cashier, coord = make_user("CASHIER"), make_user("COORDINATOR")
    c = Client(app).login(cashier["email"])
    assert c.get("/staff/payments").status_code == 200
    assert c.get("/admin/events").status_code == 403
    k = Client(app).login(coord["email"])
    assert k.get("/staff/scoring").status_code == 200
    assert k.get("/staff/payments").status_code == 403
    assert k.get("/staff/desk").status_code == 403


def test_account_lockout(client, make_user, db):
    u = make_user()
    for _ in range(5):
        r = client.post("/login", {"email": u["email"], "password": "wrong"})
        assert r.status_code == 401
    assert db.value("SELECT locked_until > NOW() FROM app_user WHERE user_id = %s", (u["user_id"],)) == 1
    r = client.post("/login", {"email": u["email"], "password": "Secret@123"})
    assert r.status_code == 401 and "Too many failed attempts" in r.get_data(as_text=True)


def test_unknown_email_same_message(client):
    r = client.post("/login", {"email": "nobody@test.example", "password": "whatever1A"})
    assert r.status_code == 401 and "Invalid e-mail or password" in r.get_data(as_text=True)


def test_sessions_invalidated_after_password_change(app, make_user):
    from tests.conftest import Client
    u = make_user()
    a, b = Client(app).login(u["email"]), Client(app).login(u["email"])
    r = a.post("/change-password", {"current": "Secret@123", "password": "Newpass@456", "confirm": "Newpass@456"})
    assert r.status_code == 302
    assert a.get("/me/").status_code == 200                      # the session that changed it stays in
    assert b.get("/me/").status_code == 302                      # the other session is signed out


def test_forced_password_change_for_new_staff(app, db, make_user):
    from tests.conftest import Client
    u = make_user("CASHIER")
    db.run("UPDATE app_user SET must_change_password = TRUE WHERE user_id = %s", (u["user_id"],))
    c = Client(app).login(u["email"])
    assert c.get("/staff/").headers["Location"].endswith("/change-password")


def test_csv_formula_injection_neutralised():
    from webapp.services.reports import to_csv
    out = to_csv(["name"], [["=HYPERLINK(\"http://x\")"], ["-5"]]).decode("utf-8-sig")
    assert "'=HYPERLINK" in out and "\n-5" in out.replace("\r", "")
