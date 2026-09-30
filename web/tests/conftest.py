"""Test fixtures. Tests run against a throw-away database `symposium_test`.

Run:   set MYSQL_ROOT_PASSWORD=...   (PowerShell: $env:MYSQL_ROOT_PASSWORD="...")
       python -m pytest -q
Tests are skipped when MYSQL_ROOT_PASSWORD is not set.
"""
import datetime as dt
import os
import re
import sys

import mysql.connector
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manage import split_sql  # noqa: E402
from webapp import config  # noqa: E402

TEST_DB = "symposium_test"
ROOT_PW = os.environ.get("MYSQL_ROOT_PASSWORD")
PW = "Secret@123"


def _root(database=None):
    cfg = config.load()["mysql"]
    return mysql.connector.connect(host=cfg["host"], port=int(cfg["port"]), user="root", password=ROOT_PW,
                                   database=database, autocommit=True)


@pytest.fixture(scope="session")
def app():
    if not ROOT_PW:
        pytest.skip("set MYSQL_ROOT_PASSWORD to run the database tests")
    conn = _root()
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cur.execute(f"CREATE DATABASE {TEST_DB} CHARACTER SET utf8mb4")
    cur.execute(f"USE {TEST_DB}")
    with open(config.SCHEMA_PATH, encoding="utf-8") as fh:
        for stmt in split_sql(fh.read()):
            cur.execute(stmt)
    cur.execute("INSERT INTO department (dept_name) VALUES ('CSE'), ('IT')")
    cur.execute("INSERT INTO event_category (category_name) VALUES ('Technical')")
    cur.execute("INSERT INTO venue (venue_name, capacity) VALUES ('Hall A', 200), ('Hall B', 200)")
    cur.execute("INSERT INTO app_setting VALUES ('data_mode', 'demo')")      # mock gateway allowed in tests
    conn.close()
    from webapp import create_app
    cfg = config.load()["mysql"]
    params = {"host": cfg["host"], "port": int(cfg["port"]), "user": "root", "password": ROOT_PW, "database": TEST_DB}
    application = create_app({"TESTING": True, "START_JOBS": False, "DB_PARAMS": params, "DB_RO_PARAMS": params,
                              "WTF_CSRF_ENABLED": True})
    yield application
    conn = _root()
    conn.cursor().execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture()
def db(app):
    from webapp import db as dbmod
    return dbmod.get()


class Client:
    """Test client that knows the CSRF token and can sign in."""

    def __init__(self, app):
        self.c = app.test_client()
        self.token = None

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, **kw):
        if self.token is None:
            self._token()
        data = dict(data or {})
        data.setdefault("csrf_token", self.token)
        return self.c.post(url, data=data, **kw)

    def _token(self):
        html = self.c.get("/login").get_data(as_text=True)
        self.token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def login(self, email, password=PW):
        r = self.post("/login", {"email": email, "password": password})
        assert r.status_code == 302, r.get_data(as_text=True)[:300]
        return self


@pytest.fixture()
def client(app):
    return Client(app)


_counter = {"n": 0}


@pytest.fixture()
def make_user(app, db):
    def factory(role="PARTICIPANT", verified=True):
        from webapp.security import hash_password
        _counter["n"] += 1
        n = _counter["n"]
        email = f"user{n}@test.example"
        uid = db.run("INSERT INTO app_user (full_name, email, phone, password_hash, role, email_verified) "
                     "VALUES (%s, %s, %s, %s, %s, %s)", (f"User {n}", email, f"90000{n:05d}", hash_password(PW),
                                                         role, verified))
        if role == "PARTICIPANT":
            db.run("INSERT INTO college (college_name) VALUES (%s)", (f"College {n}",))
            cid = db.value("SELECT college_id FROM college WHERE college_name = %s", (f"College {n}",))
            db.run("INSERT INTO participant_profile VALUES (%s, %s, 1, 2, NULL)", (uid, cid))
        return {"user_id": uid, "email": email}
    return factory


@pytest.fixture()
def make_event(db):
    def factory(fee=100, cap=50, start="10:00", end="11:00", days=10, tmin=1, tmax=1, venue=None, **extra):
        _counter["n"] += 1
        cols = {"event_name": f"Event {_counter['n']}", "category_id": 1, "venue_id": venue,
                "event_date": dt.date.today() + dt.timedelta(days=days), "start_time": start, "end_time": end,
                "registration_fee": fee, "max_participants": cap, "team_min": tmin, "team_max": tmax, **extra}
        return db.run(f"INSERT INTO event ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                      tuple(cols.values()))
    return factory


@pytest.fixture()
def ctx(app):
    with app.test_request_context():
        yield
