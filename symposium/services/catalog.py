"""Events and master data (venues, categories, colleges, departments, settings)."""
from symposium import db
from symposium.services.auth import audit

EVENT_FIELDS = ("event_name", "category_id", "description", "venue_id", "event_date", "start_time",
                "end_time", "registration_fee", "max_participants", "coordinator_name",
                "coordinator_phone", "status")


# ---------------------------------------------------------------- events
def list_events(search: str = "", category: str | None = None, status: str | None = None,
                upcoming_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM v_event_summary WHERE 1=1"
    params: list = []
    if search:
        sql += " AND (event_name LIKE %s OR coordinator_name LIKE %s OR description LIKE %s)"
        params += [f"%{search}%"] * 3
    if category:
        sql += " AND category_name = %s"
        params.append(category)
    if status:
        sql += " AND status = %s"
        params.append(status)
    if upcoming_only:
        sql += " AND event_date >= CURDATE() AND status IN ('OPEN','CLOSED')"
    sql += " ORDER BY event_date, start_time"
    return db.get().fetch_all(sql, tuple(params))


def get_event(event_id: int) -> dict | None:
    return db.get().fetch_one("SELECT * FROM v_event_summary WHERE event_id = %s", (event_id,))


def save_event(data: dict, actor_id: int, event_id: int | None = None) -> int:
    values = tuple(data.get(f) for f in EVENT_FIELDS)
    database = db.get()
    if event_id is None:
        placeholders = ", ".join(["%s"] * len(EVENT_FIELDS))
        event_id = database.execute(
            f"INSERT INTO event ({', '.join(EVENT_FIELDS)}) VALUES ({placeholders})", values)
        audit(actor_id, "EVENT_CREATED", f"Event #{event_id} {data['event_name']}")
    else:
        if data["max_participants"] is not None:
            taken = database.scalar("SELECT COUNT(*) FROM registration WHERE event_id=%s "
                                    "AND status <> 'CANCELLED'", (event_id,))
            if data["max_participants"] < taken:
                raise db.DatabaseError(f"Capacity cannot be lower than current registrations ({taken}).")
        sets = ", ".join(f"{f} = %s" for f in EVENT_FIELDS)
        database.execute(f"UPDATE event SET {sets} WHERE event_id = %s", values + (event_id,))
        audit(actor_id, "EVENT_UPDATED", f"Event #{event_id} {data['event_name']}")
    return event_id


def delete_event(event_id: int) -> None:
    db.get().execute("DELETE FROM event WHERE event_id = %s", (event_id,))


def set_event_status(event_id: int, status: str, actor_id: int) -> None:
    db.get().execute("UPDATE event SET status = %s WHERE event_id = %s", (status, event_id))
    audit(actor_id, "EVENT_STATUS", f"Event #{event_id} -> {status}")


# ---------------------------------------------------------------- simple master tables
MASTER_TABLES = {
    # key: (table, pk, columns (name, label), order by)
    "venue": ("venue", "venue_id", [("venue_name", "Venue"), ("location", "Location"),
                                    ("capacity", "Capacity")], "venue_name"),
    "category": ("event_category", "category_id", [("category_name", "Category")], "category_name"),
    "college": ("college", "college_id", [("college_name", "College"), ("city", "City")], "college_name"),
    "department": ("department", "dept_id", [("dept_name", "Department")], "dept_name"),
}


def master_rows(kind: str) -> list[dict]:
    table, pk, cols, order = MASTER_TABLES[kind]
    names = ", ".join(c for c, _ in cols)
    return db.get().fetch_all(f"SELECT {pk}, {names} FROM {table} ORDER BY {order}")


def master_save(kind: str, data: dict, row_id: int | None = None) -> None:
    table, pk, cols, _ = MASTER_TABLES[kind]
    names = [c for c, _ in cols]
    values = tuple(data.get(c) for c in names)
    if row_id is None:
        db.get().execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES "
                         f"({', '.join(['%s'] * len(names))})", values)
    else:
        db.get().execute(f"UPDATE {table} SET {', '.join(f'{c} = %s' for c in names)} "
                         f"WHERE {pk} = %s", values + (row_id,))


def master_delete(kind: str, row_id: int) -> None:
    table, pk, _, _ = MASTER_TABLES[kind]
    db.get().execute(f"DELETE FROM {table} WHERE {pk} = %s", (row_id,))


def categories() -> list[dict]:
    return db.get().fetch_all("SELECT category_id, category_name FROM event_category ORDER BY category_name")


def venues() -> list[dict]:
    return db.get().fetch_all("SELECT venue_id, venue_name, capacity FROM venue ORDER BY venue_name")


def colleges() -> list[dict]:
    return db.get().fetch_all("SELECT college_id, college_name FROM college ORDER BY college_name")


def departments() -> list[dict]:
    return db.get().fetch_all("SELECT dept_id, dept_name FROM department ORDER BY dept_name")


# ---------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "symposium_name": "Symposium",
    "tagline": "Technical Symposium",
    "host_institution": "",
    "contact_email": "",
    "contact_phone": "",
}


def settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    for row in db.get().fetch_all("SELECT setting_key, setting_value FROM app_setting"):
        data[row["setting_key"]] = row["setting_value"]
    return data


def save_settings(values: dict, actor_id: int) -> None:
    with db.get().cursor() as cur:
        for key, value in values.items():
            cur.execute("INSERT INTO app_setting (setting_key, setting_value) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)", (key, value))
    audit(actor_id, "SETTINGS_UPDATED", "Symposium details updated")
