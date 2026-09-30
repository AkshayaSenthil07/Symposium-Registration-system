"""Admin features: events + change notices, venue clash, backup/restore, SQL console safety."""
import datetime as dt


def _admin(app, make_user):
    from tests.conftest import Client
    return Client(app).login(make_user("ADMIN")["email"])


def _event_form(**over):
    d = {"event_name": "Admin Test Event", "category_id": "1", "venue_id": "1",
         "event_date": (dt.date.today() + dt.timedelta(days=20)).isoformat(), "start_time": "10:00",
         "end_time": "11:00", "registration_fee": "100", "max_participants": "50", "team_min": "1",
         "team_max": "1", "status": "OPEN", "is_published": "1"}
    d.update(over)
    return d


def test_event_create_clash_and_change_notice(app, make_user, db):
    a = _admin(app, make_user)
    assert a.post("/admin/events/new", _event_form()).status_code == 302
    eid = db.value("SELECT event_id FROM event WHERE event_name = 'Admin Test Event'")
    r = a.post("/admin/events/new", _event_form(event_name="Clashing", start_time="10:30", end_time="11:30"))
    assert r.status_code == 200 and "Venue clash" in r.get_data(as_text=True)
    r = a.post(f"/admin/events/{eid}/edit", _event_form(start_time="14:00", end_time="15:00", announce="1"))
    assert r.status_code == 302
    assert "Time changed" in db.value("SELECT change_note FROM event WHERE event_id = %s", (eid,))
    assert db.value("SELECT COUNT(*) FROM news_item WHERE message LIKE 'Admin Test Event%'") == 1


def test_sql_console_is_read_only(app, make_user):
    a = _admin(app, make_user)
    assert "Only one SELECT" in a.post("/admin/sql", {"sql": "DROP TABLE event"}).get_data(as_text=True)
    assert "Only one SELECT" in a.post("/admin/sql", {"sql": "SELECT 1; DELETE FROM event"}).get_data(as_text=True)
    html = a.post("/admin/sql", {"sql": "SELECT COUNT(*) AS n FROM event"}).get_data(as_text=True)
    assert "<th>n</th>" in html


def test_backup_and_restore_roundtrip(app, make_user, db):
    from webapp.services import backups
    with app.app_context():
        name = backups.create(app.config["CFG"], label="test")
        before = db.value("SELECT COUNT(*) FROM app_user")
        db.run("DELETE FROM news_item")
        db.run("INSERT INTO college (college_name) VALUES ('Temporary College XYZ')")
        raw = open(backups.path_for(name), "rb").read()
        res = backups.restore(raw, app.config["CFG"])
    assert res["counts"]["app_user"] == before
    assert db.value("SELECT COUNT(*) FROM college WHERE college_name = 'Temporary College XYZ'") == 0


def test_go_live_needs_real_admin_and_keeps_setup(app, db, make_user):
    from webapp.db import DatabaseError
    from webapp.services import demo
    db.run("UPDATE app_user SET is_demo = TRUE WHERE role = 'ADMIN'")
    with app.app_context():
        try:
            demo.go_live(None)
            raised = False
        except DatabaseError:
            raised = True
    assert raised
    make_user("ADMIN")
    venues = db.value("SELECT COUNT(*) FROM venue")
    with app.app_context():
        demo.go_live(None)
    assert db.value("SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT'") == 0
    assert db.value("SELECT COUNT(*) FROM registration") == 0
    assert db.value("SELECT COUNT(*) FROM venue") == venues
    with app.app_context():
        from webapp.services import settings
        assert settings.get("data_mode") == "live"
        settings.save({"data_mode": "demo"})             # leave the test database as we found it
