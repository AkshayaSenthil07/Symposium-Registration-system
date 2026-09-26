"""Registrations, payments, attendance and results."""
from symposium import db
from symposium.services.auth import audit

PAYMENT_METHODS = {
    "UPI": "UPI (GPay / PhonePe / Paytm)",
    "CARD": "Debit / Credit Card",
    "NET_BANKING": "Net Banking",
    "CASH": "Pay at Registration Desk",
}


def register(user_id: int, event_id: int, team_name: str, method: str) -> int:
    """Calls the transactional stored procedure; returns the registration id."""
    result = db.get().call_proc("sp_register_participant", (user_id, event_id, team_name, method, 0))
    return result[4]


def cancel(reg_id: int, actor_id: int) -> None:
    db.get().call_proc("sp_cancel_registration", (reg_id, actor_id))


def my_registrations(user_id: int) -> list[dict]:
    return db.get().fetch_all(
        "SELECT * FROM v_registration_details WHERE user_id = %s "
        "ORDER BY status = 'CANCELLED', event_date, start_time", (user_id,))


def active_event_ids(user_id: int) -> dict[int, str]:
    rows = db.get().fetch_all("SELECT event_id, status FROM registration WHERE user_id = %s "
                              "AND status <> 'CANCELLED'", (user_id,))
    return {r["event_id"]: r["status"] for r in rows}


def get(reg_id: int) -> dict | None:
    return db.get().fetch_one("SELECT * FROM v_registration_details WHERE reg_id = %s", (reg_id,))


def search(event_id: int | None = None, status: str | None = None, text: str = "",
           payment_status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM v_registration_details WHERE 1=1"
    params: list = []
    if event_id:
        sql += " AND event_id = %s"
        params.append(event_id)
    if status:
        sql += " AND status = %s"
        params.append(status)
    if payment_status:
        sql += " AND payment_status = %s"
        params.append(payment_status)
    if text:
        sql += (" AND (full_name LIKE %s OR email LIKE %s OR college_name LIKE %s "
                "OR team_name LIKE %s OR transaction_ref LIKE %s OR reg_id = %s)")
        params += [f"%{text}%"] * 5 + [text if text.isdigit() else -1]
    sql += " ORDER BY event_date, event_name, full_name"
    return db.get().fetch_all(sql, tuple(params))


def set_attendance(reg_ids: list[int], present: bool, actor_id: int) -> int:
    if not reg_ids:
        return 0
    marks = ", ".join(["%s"] * len(reg_ids))
    count = db.get().execute(
        f"UPDATE registration SET attended = %s WHERE reg_id IN ({marks}) AND status = 'CONFIRMED'",
        (present, *reg_ids))
    audit(actor_id, "ATTENDANCE_BULK", f"{count} marked {'present' if present else 'absent'}")
    return count


def verify_cash_payment(reg_id: int, actor_id: int) -> None:
    changed = db.get().execute(
        "UPDATE payment SET status = 'SUCCESS', paid_at = NOW() "
        "WHERE reg_id = %s AND status = 'PENDING'", (reg_id,))
    if not changed:
        raise db.DatabaseError("No pending payment found for this registration.")
    audit(actor_id, "PAYMENT_VERIFIED", f"Cash payment for reg #{reg_id} received")


# ---------------------------------------------------------------- results
def results(event_id: int | None = None) -> list[dict]:
    sql = ("SELECT er.event_id, er.position, er.reg_id, e.event_name, e.event_date, cat.category_name, "
           "u.full_name, r.team_name, c.college_name "
           "FROM event_result er "
           "JOIN event e ON e.event_id = er.event_id "
           "JOIN event_category cat ON cat.category_id = e.category_id "
           "JOIN registration r ON r.reg_id = er.reg_id "
           "JOIN app_user u ON u.user_id = r.user_id "
           "LEFT JOIN participant_profile pp ON pp.user_id = u.user_id "
           "LEFT JOIN college c ON c.college_id = pp.college_id")
    params: tuple = ()
    if event_id:
        sql += " WHERE er.event_id = %s"
        params = (event_id,)
    sql += " ORDER BY e.event_date DESC, e.event_name, er.position"
    return db.get().fetch_all(sql, params)


def set_result(event_id: int, position: int, reg_id: int, actor_id: int) -> None:
    with db.get().cursor() as cur:
        cur.execute("SELECT attended, status FROM registration WHERE reg_id = %s AND event_id = %s",
                    (reg_id, event_id))
        row = cur.fetchone()
        if not row or row["status"] != "CONFIRMED" or not row["attended"]:
            raise db.DatabaseError("Only confirmed participants who attended can be awarded a prize.")
        cur.execute("DELETE FROM event_result WHERE event_id = %s AND (position = %s OR reg_id = %s)",
                    (event_id, position, reg_id))
        cur.execute("INSERT INTO event_result (event_id, position, reg_id) VALUES (%s, %s, %s)",
                    (event_id, position, reg_id))
        cur.execute("INSERT INTO audit_log (user_id, action, details) VALUES (%s, 'RESULT', %s)",
                    (actor_id, f"Event #{event_id}: position {position} -> reg #{reg_id}"))


def clear_result(event_id: int, position: int, actor_id: int) -> None:
    db.get().execute("DELETE FROM event_result WHERE event_id = %s AND position = %s", (event_id, position))
    audit(actor_id, "RESULT_CLEARED", f"Event #{event_id} position {position}")
