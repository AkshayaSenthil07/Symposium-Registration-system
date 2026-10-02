"""Dashboard statistics, analytical reports, participants and audit log."""
import csv
import datetime as dt

from symposium import config, db


def dashboard_stats() -> dict:
    return db.get().fetch_one("""
        SELECT
          (SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT')                  AS participants,
          (SELECT COUNT(*) FROM event WHERE status <> 'CANCELLED')                     AS events,
          (SELECT COUNT(*) FROM registration WHERE status = 'CONFIRMED')               AS confirmed,
          (SELECT COUNT(*) FROM registration WHERE status = 'PENDING')                 AS pending,
          (SELECT COALESCE(SUM(amount), 0) FROM payment WHERE status = 'SUCCESS')      AS revenue,
          (SELECT COALESCE(SUM(amount), 0) FROM payment WHERE status = 'PENDING')      AS pending_amount,
          (SELECT COUNT(DISTINCT pp.college_id) FROM participant_profile pp)            AS colleges,
          (SELECT COUNT(*) FROM registration WHERE registered_at >= CURDATE())         AS today
    """)


def registrations_per_event() -> list[dict]:
    return db.get().fetch_all(
        "SELECT event_name, registered, max_participants FROM v_event_summary "
        "WHERE status <> 'CANCELLED' ORDER BY registered DESC")


def revenue_by_category() -> list[dict]:
    return db.get().fetch_all(
        "SELECT category_name, SUM(revenue) AS revenue, SUM(registered) AS registered "
        "FROM v_event_summary GROUP BY category_name ORDER BY revenue DESC")


def daily_registrations(days: int = 14) -> list[dict]:
    rows = db.get().fetch_all(
        "SELECT DATE(registered_at) AS day, COUNT(*) AS n FROM registration "
        "WHERE registered_at >= CURDATE() - INTERVAL %s DAY GROUP BY DATE(registered_at)", (days - 1,))
    counts = {r["day"]: r["n"] for r in rows}
    today = dt.date.today()
    return [{"day": d, "n": counts.get(d, 0)}
            for d in (today - dt.timedelta(days=i) for i in range(days - 1, -1, -1))]


# Pre-built analytical reports: title -> SQL (each demonstrates joins / grouping)
REPORTS = {
    "Event-wise summary":
        "SELECT event_name AS Event, category_name AS Category, event_date AS Date, "
        "registered AS Registered, confirmed AS Confirmed, attended AS Attended, "
        "seats_left AS `Seats Left`, revenue AS `Revenue (Rs)` FROM v_event_summary ORDER BY event_date",
    "College-wise participation":
        "SELECT college_name AS College, participants AS Participants, registrations AS Registrations, "
        "gold AS Gold, silver AS Silver, bronze AS Bronze, points AS Points "
        "FROM v_college_leaderboard ORDER BY points DESC, registrations DESC",
    "Department-wise participation":
        "SELECT d.dept_name AS Department, COUNT(DISTINCT pp.user_id) AS Participants, "
        "COUNT(r.reg_id) AS Registrations FROM department d "
        "LEFT JOIN participant_profile pp ON pp.dept_id = d.dept_id "
        "LEFT JOIN registration r ON r.user_id = pp.user_id AND r.status <> 'CANCELLED' "
        "GROUP BY d.dept_id, d.dept_name ORDER BY Registrations DESC",
    "Year-of-study distribution":
        "SELECT CONCAT('Year ', pp.year_of_study) AS Year, COUNT(*) AS Participants "
        "FROM participant_profile pp GROUP BY pp.year_of_study ORDER BY pp.year_of_study",
    "Payment method breakdown":
        "SELECT method AS Method, status AS Status, COUNT(*) AS Transactions, "
        "SUM(amount) AS `Amount (Rs)` FROM payment GROUP BY method, status ORDER BY method, status",
    "Pending cash payments":
        "SELECT reg_id AS `Reg ID`, full_name AS Participant, phone AS Phone, event_name AS Event, "
        "amount AS `Amount (Rs)`, transaction_ref AS Reference FROM v_registration_details "
        "WHERE payment_status = 'PENDING' ORDER BY event_name, full_name",
    "Multi-event participants (HAVING)":
        "SELECT u.full_name AS Participant, u.email AS Email, COUNT(*) AS Events "
        "FROM registration r JOIN app_user u ON u.user_id = r.user_id "
        "WHERE r.status <> 'CANCELLED' GROUP BY u.user_id, u.full_name, u.email "
        "HAVING COUNT(*) >= 3 ORDER BY Events DESC, Participant",
    "Events above average registrations (sub-query)":
        "SELECT event_name AS Event, registered AS Registered FROM v_event_summary "
        "WHERE registered > (SELECT AVG(registered) FROM v_event_summary) ORDER BY registered DESC",
    "Venue utilisation":
        "SELECT v.venue_name AS Venue, v.capacity AS Capacity, COUNT(DISTINCT e.event_id) AS Events, "
        "COALESCE(SUM(es.registered), 0) AS `Total Registrations` FROM venue v "
        "LEFT JOIN event e ON e.venue_id = v.venue_id "
        "LEFT JOIN v_event_summary es ON es.event_id = e.event_id "
        "GROUP BY v.venue_id, v.venue_name, v.capacity ORDER BY `Total Registrations` DESC",
}


def run_report(title: str) -> tuple[list[str], list[tuple]]:
    with db.get().cursor(dictionary=False) as cur:
        cur.execute(REPORTS[title])
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def participants(search: str = "") -> list[dict]:
    sql = "SELECT * FROM v_participant_details"
    params: tuple = ()
    if search:
        sql += " WHERE full_name LIKE %s OR email LIKE %s OR college_name LIKE %s OR phone LIKE %s"
        params = (f"%{search}%",) * 4
    return db.get().fetch_all(sql + " ORDER BY full_name", params)


def admins() -> list[dict]:
    return db.get().fetch_all("SELECT user_id, full_name, email, phone, is_active, last_login "
                              "FROM app_user WHERE role = 'ADMIN' ORDER BY full_name")


def audit_log(search: str = "", limit: int = 500) -> list[dict]:
    sql = ("SELECT a.log_id, a.created_at, COALESCE(u.full_name, 'System') AS who, a.action, a.details "
           "FROM audit_log a LEFT JOIN app_user u ON u.user_id = a.user_id")
    params: list = []
    if search:
        sql += " WHERE a.action LIKE %s OR a.details LIKE %s OR u.full_name LIKE %s"
        params = [f"%{search}%"] * 3
    sql += " ORDER BY a.log_id DESC LIMIT %s"
    params.append(limit)
    return db.get().fetch_all(sql, tuple(params))


def export_csv(filename: str, columns: list[str], rows: list) -> str:
    path = config.export_path(filename)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM so Excel opens it cleanly
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    return path
