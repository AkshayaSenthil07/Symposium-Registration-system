"""Events and master data."""
import datetime as dt

from webapp import db
from webapp.services import audit
from webapp.util import fmt_date, fmt_time, now

EVENT_FIELDS = ("event_name", "category_id", "description", "rules", "prizes", "venue_id", "event_date",
                "start_time", "end_time", "registration_fee", "early_bird_fee", "early_bird_until",
                "registration_deadline", "max_participants", "team_min", "team_max", "coordinator_name",
                "coordinator_phone", "status", "is_published")


def list_events(public_only=True, category_id=None, search="", status=None) -> list[dict]:
    sql = "SELECT * FROM v_event_summary WHERE 1=1"
    params: list = []
    if public_only:
        sql += " AND is_published AND status <> 'CANCELLED'"
    if category_id:
        sql += " AND category_id = %s"
        params.append(category_id)
    if status:
        sql += " AND status = %s"
        params.append(status)
    if search:
        sql += " AND (event_name LIKE %s OR description LIKE %s OR coordinator_name LIKE %s)"
        params += [f"%{search}%"] * 3
    sql += " ORDER BY event_date < CURDATE(), event_date, start_time, event_name"   # finished events last
    return [decorate(e) for e in db.get().all(sql, tuple(params))]


def get(event_id: int, public_only=True) -> dict | None:
    e = db.get().one("SELECT * FROM v_event_summary WHERE event_id = %s", (event_id,))
    if e and public_only and (not e["is_published"]):
        return None
    return decorate(e) if e else None


def decorate(e: dict) -> dict:
    """Adds computed flags used by the templates."""
    t = now()
    start = dt.datetime.combine(e["event_date"], dt.time()) + e["start_time"]
    e["starts_at"] = start
    e["is_past"] = e["event_date"] < t.date()
    e["deadline_passed"] = bool(e["registration_deadline"] and e["registration_deadline"] < t)
    e["early_bird_active"] = bool(e["early_bird_fee"] is not None and e["early_bird_until"]
                                  and t <= e["early_bird_until"])
    e["is_team"] = e["team_max"] > 1
    e["recently_changed"] = bool(e["changed_at"] and (t - e["changed_at"]).days < 7)
    e["can_register"] = (e["status"] == "OPEN" and not e["is_past"] and not e["deadline_passed"])
    fill = (e["registered"] / e["max_participants"]) if e["max_participants"] else 1
    e["fill_pct"] = min(100, round(fill * 100))
    return e


def categories() -> list[dict]:
    return db.get().all("SELECT category_id, category_name FROM event_category ORDER BY category_name")


def venues() -> list[dict]:
    return db.get().all("SELECT venue_id, venue_name, location, capacity FROM venue ORDER BY venue_name")


def schedule() -> dict:
    """Published events grouped by date."""
    days: dict = {}
    for e in list_events():
        days.setdefault(e["event_date"], []).append(e)
    return days


# ------------------------------------------------------------------ admin
def venue_clash(venue_id, event_date, start, end, exclude_id=None) -> dict | None:
    if not venue_id:
        return None
    return db.get().one(
        "SELECT event_name, start_time, end_time FROM event WHERE venue_id = %s AND event_date = %s "
        "AND status <> 'CANCELLED' AND start_time < %s AND end_time > %s AND event_id <> %s LIMIT 1",
        (venue_id, event_date, end, start, exclude_id or 0))


def save(data: dict, actor_id: int, event_id: int | None = None) -> tuple[int, str | None]:
    """Creates or updates an event. Returns (event_id, change description or None)."""
    values = tuple(data.get(f) for f in EVENT_FIELDS)
    change = None
    with db.get().transaction() as cur:
        if event_id is None:
            cur.execute(f"INSERT INTO event ({', '.join(EVENT_FIELDS)}) "
                        f"VALUES ({', '.join(['%s'] * len(EVENT_FIELDS))})", values)
            event_id = cur.lastrowid
            audit.log(actor_id, "EVENT_CREATED", data["event_name"], cur=cur)
            return event_id, None
        cur.execute("SELECT e.*, v.venue_name FROM event e LEFT JOIN venue v ON v.venue_id = e.venue_id "
                    "WHERE event_id = %s FOR UPDATE", (event_id,))
        old = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS n FROM registration WHERE event_id = %s "
                    "AND status IN ('PENDING','CONFIRMED')", (event_id,))
        taken = cur.fetchone()["n"]
        if int(data["max_participants"]) < taken:
            raise db.DatabaseError(f"Capacity cannot be lower than the current registrations ({taken}).")
        parts = []
        if str(old["event_date"]) != str(data["event_date"]):
            parts.append(f"date moved to {fmt_date(dt.date.fromisoformat(str(data['event_date'])))}")
        if _t(old["start_time"]) != _t(data["start_time"]) or _t(old["end_time"]) != _t(data["end_time"]):
            parts.append(f"time changed to {_t(data['start_time'])}-{_t(data['end_time'])}")
        if (old["venue_id"] or 0) != (data["venue_id"] or 0):
            cur.execute("SELECT venue_name FROM venue WHERE venue_id = %s", (data["venue_id"] or 0,))
            v = cur.fetchone()
            parts.append(f"venue changed to {v['venue_name'] if v else 'Online'}")
        if old["status"] != data["status"] and data["status"] == "CANCELLED":
            parts.append("event cancelled")
        sets = ", ".join(f"{f} = %s" for f in EVENT_FIELDS)
        extra = ""
        extra_params: tuple = ()
        if parts:
            change = "; ".join(parts)
            change = change[0].upper() + change[1:]
            extra = ", change_note = %s, changed_at = NOW()"
            extra_params = (change[:255],)
        cur.execute(f"UPDATE event SET {sets}{extra} WHERE event_id = %s", values + extra_params + (event_id,))
        audit.log(actor_id, "EVENT_UPDATED", f"{data['event_name']}" + (f" ({change})" if change else ""), cur=cur)
    return event_id, change


def _t(value) -> str:
    if isinstance(value, dt.timedelta):
        m = int(value.total_seconds()) // 60
        return f"{m // 60:02d}:{m % 60:02d}"
    return str(value)[:5]


def registrant_emails(event_id: int) -> list[dict]:
    return db.get().all("SELECT u.email, u.full_name FROM registration r JOIN app_user u ON u.user_id = r.user_id "
                        "WHERE r.event_id = %s AND r.status IN ('PENDING','CONFIRMED','WAITLISTED')", (event_id,))


def set_status(event_id: int, status: str, actor_id: int) -> None:
    db.get().run("UPDATE event SET status = %s WHERE event_id = %s", (status, event_id))
    audit.log(actor_id, "EVENT_STATUS", f"Event #{event_id} -> {status}")


def delete(event_id: int, actor_id: int) -> None:
    paid = db.get().value("SELECT COUNT(*) FROM payment p JOIN registration r ON r.reg_id = p.reg_id "
                          "WHERE r.event_id = %s AND p.status = 'SUCCESS' AND p.amount > 0", (event_id,))
    if paid:
        raise db.DatabaseError(f"{paid} participant(s) have paid for this event. Cancel the event instead "
                               "of deleting it, so refunds can be tracked.")
    db.get().run("DELETE FROM event WHERE event_id = %s", (event_id,))
    audit.log(actor_id, "EVENT_DELETED", f"Event #{event_id}")


def staff_for(event_id: int) -> list[dict]:
    return db.get().all("SELECT u.user_id, u.full_name, u.email, u.role FROM event_staff es "
                        "JOIN app_user u ON u.user_id = es.user_id WHERE es.event_id = %s ORDER BY u.full_name",
                        (event_id,))


def set_staff(event_id: int, user_ids: list[int], actor_id: int) -> None:
    with db.get().transaction() as cur:
        cur.execute("DELETE FROM event_staff WHERE event_id = %s", (event_id,))
        for uid in user_ids:
            cur.execute("INSERT INTO event_staff (event_id, user_id) VALUES (%s, %s)", (event_id, uid))
        audit.log(actor_id, "EVENT_STAFF", f"Event #{event_id}: {len(user_ids)} staff", cur=cur)


def events_for_staff(user: dict) -> list[dict]:
    """Admins see every event; coordinators only the ones assigned to them."""
    if user["role"] == "ADMIN":
        return list_events(public_only=False)
    rows = db.get().all("SELECT es.event_id FROM event_staff es WHERE es.user_id = %s", (user["user_id"],))
    ids = {r["event_id"] for r in rows}
    return [e for e in list_events(public_only=False) if e["event_id"] in ids]


def can_manage(user: dict, event_id: int) -> bool:
    if user["role"] == "ADMIN":
        return True
    if user["role"] != "COORDINATOR":
        return False
    return bool(db.get().value("SELECT 1 FROM event_staff WHERE event_id = %s AND user_id = %s",
                               (event_id, user["user_id"])))


def describe_slot(e: dict) -> str:
    return f"{fmt_date(e['event_date'])}, {fmt_time(e['start_time'])} - {fmt_time(e['end_time'])}"
