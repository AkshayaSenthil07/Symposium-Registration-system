"""Registration rules enforced by the service, triggers and procedures."""
import threading

import pytest

from webapp.services import registrations as R


def test_signup_verify_login_flow(client, db):
    r = client.post("/signup", {"full_name": "New Person", "email": "new.person@test.example", "phone": "9876500000",
                                "college": "Some College", "dept_id": "1", "year": "2", "password": "Secret@123",
                                "confirm": "Secret@123", "consent": "1"})
    assert r.status_code == 302
    body = db.value("SELECT body_text FROM email_outbox WHERE to_email = 'new.person@test.example'")
    token = body.split("/verify-email/")[1].split()[0]
    client.login("new.person@test.example")
    assert client.get(f"/verify-email/{token}").status_code == 302
    assert db.value("SELECT email_verified FROM app_user WHERE email = 'new.person@test.example'") == 1
    assert client.get(f"/verify-email/{token}").status_code == 302           # second use does nothing
    assert db.value("SELECT COUNT(*) FROM user_token WHERE used_at IS NOT NULL") >= 1


def test_unverified_cannot_register(ctx, make_user, make_event):
    u, e = make_user(verified=False), make_event()
    with pytest.raises(R.RegistrationError, match="verify"):
        R.register(u["user_id"], e)


def test_paid_registration_holds_seat(ctx, make_user, make_event, db):
    u, e = make_user(), make_event(fee=150)
    res = R.register(u["user_id"], e, method="UPI_QR")
    assert res["status"] == "PENDING"
    assert db.value("SELECT hold_expires_at > NOW() FROM registration WHERE reg_id = %s", (res["reg_id"],)) == 1


def test_free_event_confirmed_immediately(ctx, make_user, make_event):
    u, e = make_user(), make_event(fee=0)
    assert R.register(u["user_id"], e)["status"] == "CONFIRMED"


def test_duplicate_and_time_clash(ctx, make_user, make_event):
    u = make_user()
    e1, e2 = make_event(start="10:00", end="11:00"), make_event(start="10:30", end="11:30")
    R.register(u["user_id"], e1)
    with pytest.raises(R.RegistrationError, match="already registered"):
        R.register(u["user_id"], e1)
    with pytest.raises(R.RegistrationError, match="Time clash"):
        R.register(u["user_id"], e2)


def test_team_size_enforced(ctx, make_user, make_event):
    u, e = make_user(), make_event(tmin=2, tmax=3)
    with pytest.raises(R.RegistrationError, match="Team size"):
        R.register(u["user_id"], e, "Alpha", [])
    with pytest.raises(R.RegistrationError, match="Team size"):
        R.register(u["user_id"], e, "Alpha", [{"name": "A"}, {"name": "B"}, {"name": "C"}])
    with pytest.raises(R.RegistrationError, match="team name"):
        R.register(u["user_id"], e, "", [{"name": "A"}])
    assert R.register(u["user_id"], e, "Alpha", [{"name": "A"}])["status"] == "PENDING"


def test_coupon_and_early_bird(ctx, make_user, make_event, db):
    import datetime as dt
    e = make_event(fee=200, early_bird_fee=150, early_bird_until=dt.datetime.now() + dt.timedelta(days=1))
    db.run("INSERT INTO coupon (code, discount_type, discount_value, max_uses) VALUES ('T50', 'PERCENT', 50, 1)")
    q = R.quote(e, "t50")
    assert q["price"] == 150 and q["total"] == 75
    R.register(make_user()["user_id"], e, coupon_code="T50")
    with pytest.raises(R.RegistrationError, match="fully used"):
        R.register(make_user()["user_id"], e, coupon_code="T50")
    with pytest.raises(R.RegistrationError, match="not valid"):
        R.quote(e, "NOPE")


def test_waitlist_and_promotion_after_hold_expiry(app, ctx, make_user, make_event, db):
    e = make_event(fee=50, cap=1)
    a = R.register(make_user()["user_id"], e)
    b = R.register(make_user()["user_id"], e)
    assert (a["status"], b["status"]) == ("PENDING", "WAITLISTED")
    db.run("UPDATE registration SET hold_expires_at = NOW() - INTERVAL 1 MINUTE WHERE reg_id = %s", (a["reg_id"],))
    from webapp.services import jobs
    assert jobs.run_once(app)["expired"] == 1
    assert R.promote_waitlist(e) == b["reg_id"]
    assert db.value("SELECT status FROM registration WHERE reg_id = %s", (b["reg_id"],)) == "PENDING"
    assert db.value("SELECT COUNT(*) FROM payment WHERE reg_id = %s AND status = 'PENDING'", (b["reg_id"],)) == 1


def test_capacity_trigger_blocks_direct_insert(db, make_user, make_event):
    from webapp.db import DatabaseError
    e = make_event(cap=1)
    db.run("INSERT INTO registration (user_id, event_id, status, ticket_code) VALUES (%s, %s, 'PENDING', 'AAAAAAAAAAA2')",
           (make_user()["user_id"], e))
    with pytest.raises(DatabaseError, match="full"):
        db.run("INSERT INTO registration (user_id, event_id, status, ticket_code) VALUES (%s, %s, 'PENDING', 'AAAAAAAAAAA3')",
               (make_user()["user_id"], e))


def test_no_oversell_under_concurrency(app, make_user, make_event, db):
    """20 people press 'register' at the same moment for 5 seats: exactly 5 get seats."""
    e = make_event(fee=100, cap=5)
    users = [make_user()["user_id"] for _ in range(20)]
    results, errors = [], []

    def worker(uid):
        with app.test_request_context():
            try:
                results.append(R.register(uid, e)["status"])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert results.count("PENDING") == 5 and results.count("WAITLISTED") == 15
    assert db.value("SELECT fn_seats_left(%s)", (e,)) == 0


def test_students_cannot_cancel_or_see_others(app, make_user, make_event, db):
    from tests.conftest import Client
    a, b = make_user(), make_user()
    with app.test_request_context():
        reg = R.register(a["user_id"], make_event())["reg_id"]
    c = Client(app).login(b["email"])
    assert c.get(f"/me/registrations/{reg}").status_code == 404
    assert c.get(f"/me/registrations/{reg}/receipt.pdf").status_code == 404
    own = Client(app).login(a["email"])
    assert own.post(f"/me/registrations/{reg}/cancel").status_code == 404     # no such feature


def test_admin_cancel_refunds_and_frees_seat(ctx, make_user, make_event, db):
    e = make_event(fee=0, cap=1)
    reg = R.register(make_user()["user_id"], e)["reg_id"]
    db.call("sp_cancel_registration", (reg, None, "test"))
    assert db.value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "CANCELLED"
    assert db.value("SELECT fn_seats_left(%s)", (e,)) == 1
