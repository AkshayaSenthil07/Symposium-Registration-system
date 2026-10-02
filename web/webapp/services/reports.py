"""Dashboard figures, charts data, analytical reports and CSV export."""
import csv
import datetime as dt
import io

from webapp import db
from webapp.util import today


def dashboard(event_ids: list[int] | None = None) -> dict:
    """event_ids=None -> whole symposium (admin/cashier); a list -> coordinator's events only."""
    flt, params = "", ()
    if event_ids is not None:
        if not event_ids:
            event_ids = [0]
        flt = " AND r.event_id IN (" + ",".join(["%s"] * len(event_ids)) + ")"
        params = tuple(event_ids)
    s = db.get().one(
        "SELECT COUNT(CASE WHEN r.status = 'CONFIRMED' THEN 1 END) AS confirmed, "
        "COUNT(CASE WHEN r.status = 'PENDING' THEN 1 END) AS pending, "
        "COUNT(CASE WHEN r.status = 'WAITLISTED' THEN 1 END) AS waitlisted, "
        "COUNT(CASE WHEN r.attended THEN 1 END) AS checked_in, "
        "COUNT(DISTINCT CASE WHEN r.status IN ('PENDING','CONFIRMED') THEN r.user_id END) AS people, "
        "COUNT(CASE WHEN DATE(r.registered_at) = CURDATE() THEN 1 END) AS today "
        "FROM registration r WHERE 1=1" + flt, params)
    money = db.get().one(
        "SELECT COALESCE(SUM(CASE WHEN p.status = 'SUCCESS' THEN p.amount END), 0) AS collected, "
        "COALESCE(SUM(CASE WHEN p.status = 'SUCCESS' AND p.method = 'CASH' THEN p.amount END), 0) AS cash, "
        "COALESCE(SUM(CASE WHEN p.status = 'SUCCESS' AND p.method = 'UPI_QR' THEN p.amount END), 0) AS upi, "
        "COALESCE(SUM(CASE WHEN p.status = 'SUCCESS' AND p.method = 'GATEWAY' THEN p.amount END), 0) AS gateway, "
        "COUNT(CASE WHEN p.status = 'SUBMITTED' THEN 1 END) AS to_verify, "
        "COALESCE(SUM(CASE WHEN p.status = 'REFUNDED' THEN p.amount END), 0) AS refunded "
        "FROM payment p JOIN registration r ON r.reg_id = p.reg_id WHERE 1=1" + flt, params)
    s.update(money)
    s["participants"] = db.get().value("SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT'")
    s["colleges"] = db.get().value("SELECT COUNT(DISTINCT college_id) FROM participant_profile")
    return s


def per_event(event_ids=None) -> list[dict]:
    rows = db.get().all("SELECT event_id, event_name, registered, confirmed, attended, waitlisted, max_participants, "
                        "revenue, event_date, start_time, status FROM v_event_summary WHERE status <> 'CANCELLED' "
                        "ORDER BY registered DESC")
    if event_ids is not None:
        rows = [r for r in rows if r["event_id"] in event_ids]
    return rows


def daily(days: int = 14) -> list[dict]:
    rows = db.get().all("SELECT DATE(registered_at) AS d, COUNT(*) AS n FROM registration "
                        "WHERE registered_at >= CURDATE() - INTERVAL %s DAY GROUP BY DATE(registered_at)", (days - 1,))
    counts = {r["d"]: r["n"] for r in rows}
    t = today()
    return [{"d": d, "n": counts.get(d, 0)} for d in (t - dt.timedelta(days=i) for i in range(days - 1, -1, -1))]


def bar_chart(rows, label_key, value_key, max_key=None, width=640, row_h=30) -> dict:
    """Geometry for the SVG bar chart macro (no JavaScript needed)."""
    label_w, pad = 190, 60
    values = [r[value_key] for r in rows] + ([r[max_key] for r in rows] if max_key else [])
    top = max(values + [1])
    bars = []
    for i, r in enumerate(rows):
        v = r[value_key]
        w = (width - label_w - pad) * v / top
        cls = ""
        if max_key and r[max_key]:
            frac = v / r[max_key]
            cls = "bad" if frac >= .9 else ("warn" if frac >= .6 else "")
        bars.append({"y": i * row_h, "w": max(w, 1), "label": str(r[label_key])[:26], "value": v,
                     "cap": r[max_key] if max_key else None, "cls": cls,
                     "track": (width - label_w - pad) * (r[max_key] / top) if max_key else 0})
    return {"bars": bars, "width": width, "height": max(len(rows), 1) * row_h, "label_w": label_w}


def line_chart(rows, width=640, height=180) -> dict:
    n = len(rows)
    top = max([r["n"] for r in rows] + [1])
    left, bottom = 30, 24
    pts = []
    for i, r in enumerate(rows):
        x = left + (width - left - 10) * (i / max(n - 1, 1))
        y = 10 + (height - bottom - 10) * (1 - r["n"] / top)
        pts.append((round(x, 1), round(y, 1), r))
    line = " ".join(f"{x},{y}" for x, y, _ in pts)
    area = f"{left},{height - bottom} " + line + f" {pts[-1][0] if pts else left},{height - bottom}"
    return {"points": pts, "line": line, "area": area, "width": width, "height": height, "top": top,
            "base": height - bottom, "left": left}


REPORTS = {
    "events": ("Event-wise summary",
               "SELECT event_name AS Event, category_name AS Category, event_date AS Date, registered AS Registered, "
               "confirmed AS Confirmed, waitlisted AS Waitlisted, attended AS `Checked in`, seats_left AS `Seats left`, "
               "revenue AS `Revenue (Rs)` FROM v_event_summary ORDER BY event_date, start_time"),
    "colleges": ("College-wise participation",
                 "SELECT college_name AS College, participants AS Participants, registrations AS `Confirmed regs`, "
                 "gold AS Gold, silver AS Silver, bronze AS Bronze, points AS Points FROM v_college_leaderboard "
                 "WHERE participants > 0 ORDER BY points DESC, registrations DESC"),
    "departments": ("Department-wise participation",
                    "SELECT d.dept_name AS Department, COUNT(DISTINCT pp.user_id) AS Participants, "
                    "COUNT(r.reg_id) AS `Confirmed regs` FROM department d "
                    "LEFT JOIN participant_profile pp ON pp.dept_id = d.dept_id "
                    "LEFT JOIN registration r ON r.user_id = pp.user_id AND r.status = 'CONFIRMED' "
                    "GROUP BY d.dept_id, d.dept_name HAVING Participants > 0 ORDER BY `Confirmed regs` DESC"),
    "payments": ("Payments by method and status",
                 "SELECT method AS Method, status AS Status, COUNT(*) AS Transactions, SUM(amount) AS `Amount (Rs)` "
                 "FROM payment GROUP BY method, status ORDER BY method, status"),
    "pending": ("Pending and unverified payments",
                "SELECT reg_id AS `Reg ID`, full_name AS Participant, phone AS Phone, event_name AS Event, "
                "payment_method AS Method, payment_status AS Status, amount AS `Amount (Rs)`, utr AS UTR, "
                "hold_expires_at AS `Hold until` FROM v_registration_details "
                "WHERE payment_status IN ('PENDING','SUBMITTED') AND status = 'PENDING' ORDER BY event_name"),
    "late": ("Paid after the seat was released (needs action)",
             "SELECT r.reg_id AS `Reg ID`, u.full_name AS Participant, e.event_name AS Event, p.amount AS `Amount (Rs)`, "
             "p.gateway_payment_id AS `Gateway ref`, p.note AS Note FROM payment p "
             "JOIN registration r ON r.reg_id = p.reg_id JOIN app_user u ON u.user_id = r.user_id "
             "JOIN event e ON e.event_id = r.event_id WHERE p.status = 'SUCCESS' AND r.status = 'CANCELLED'"),
    "multi": ("Participants in 3+ events (GROUP BY ... HAVING)",
              "SELECT u.full_name AS Participant, u.email AS Email, COUNT(*) AS Events FROM registration r "
              "JOIN app_user u ON u.user_id = r.user_id WHERE r.status IN ('PENDING','CONFIRMED') "
              "GROUP BY u.user_id, u.full_name, u.email HAVING COUNT(*) >= 3 ORDER BY Events DESC"),
    "feedback": ("Feedback ratings by event",
                 "SELECT e.event_name AS Event, COUNT(f.reg_id) AS Responses, ROUND(AVG(f.rating), 2) AS `Avg rating` "
                 "FROM feedback f JOIN registration r ON r.reg_id = f.reg_id JOIN event e ON e.event_id = r.event_id "
                 "GROUP BY e.event_id, e.event_name ORDER BY `Avg rating` DESC"),
    "coupons": ("Coupon usage",
                "SELECT c.code AS Code, c.discount_type AS Type, c.discount_value AS Value, c.used_count AS Used, "
                "c.max_uses AS `Max uses`, IFNULL(e.event_name, 'All events') AS Event FROM coupon c "
                "LEFT JOIN event e ON e.event_id = c.event_id ORDER BY c.used_count DESC"),
    "venues": ("Venue utilisation",
               "SELECT v.venue_name AS Venue, v.capacity AS Capacity, COUNT(DISTINCT e.event_id) AS Events, "
               "COALESCE(SUM(es.registered), 0) AS Registrations FROM venue v "
               "LEFT JOIN event e ON e.venue_id = v.venue_id AND e.status <> 'CANCELLED' "
               "LEFT JOIN v_event_summary es ON es.event_id = e.event_id "
               "GROUP BY v.venue_id, v.venue_name, v.capacity ORDER BY Registrations DESC"),
}


def run(key: str) -> tuple[str, list[str], list[tuple]]:
    title, sql = REPORTS[key]
    with db.get().transaction(dictionary=False) as cur:
        cur.execute(sql)
        return title, [d[0] for d in cur.description], cur.fetchall()


def to_csv(columns: list[str], rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for row in rows:
        w.writerow(["" if v is None else _safe_cell(v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _safe_cell(v):
    """Neutralises spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not s.lstrip("-").replace(".", "").isdigit() else s
