"""Admin-only management screens. Everything the organisers need to change lives here."""
import datetime as dt
import decimal
import os
import secrets

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   send_file, url_for)

from webapp import config, db
from webapp.security import clean, random_password, rate_limit, roles_required, valid_email, valid_phone
from webapp.services import (audit, backups, demo, events, mailer, news, notify, pdf, reports, settings, users)
from webapp.util import hhmm, now, parse_datetime_local

bp = Blueprint("admin", __name__, url_prefix="/admin")
admin_only = roles_required("ADMIN")


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _dec(v, default=None):
    try:
        return decimal.Decimal(str(v).strip()) if str(v).strip() != "" else default
    except decimal.InvalidOperation:
        return default


# ======================================================================================= events
@bp.route("/events", endpoint="events")
@admin_only
def events_list():
    return render_template("admin/events.html", events=events.list_events(public_only=False))


def _event_form(f) -> tuple[dict, list[str]]:
    errs = []
    data = {
        "event_name": clean(f.get("event_name"), 100), "category_id": _int(f.get("category_id")),
        "description": clean(f.get("description"), 3000) or None, "rules": clean(f.get("rules"), 3000) or None,
        "prizes": clean(f.get("prizes"), 255) or None, "venue_id": _int(f.get("venue_id")) or None,
        "event_date": f.get("event_date"), "start_time": f.get("start_time"), "end_time": f.get("end_time"),
        "registration_fee": _dec(f.get("registration_fee"), decimal.Decimal(0)),
        "early_bird_fee": _dec(f.get("early_bird_fee")), "early_bird_until": parse_datetime_local(f.get("early_bird_until")),
        "registration_deadline": parse_datetime_local(f.get("registration_deadline")),
        "max_participants": _int(f.get("max_participants"), 0), "team_min": _int(f.get("team_min"), 1),
        "team_max": _int(f.get("team_max"), 1), "coordinator_name": clean(f.get("coordinator_name"), 100) or None,
        "coordinator_phone": clean(f.get("coordinator_phone"), 15) or None,
        "status": f.get("status") if f.get("status") in ("OPEN", "CLOSED", "COMPLETED", "CANCELLED") else "OPEN",
        "is_published": f.get("is_published") == "1",
    }
    if len(data["event_name"]) < 3:
        errs.append("Event name is required.")
    if not data["category_id"]:
        errs.append("Choose a category.")
    try:
        dt.date.fromisoformat(data["event_date"] or "")
        s, e = dt.time.fromisoformat(data["start_time"]), dt.time.fromisoformat(data["end_time"])
        if e <= s:
            errs.append("End time must be after the start time.")
    except (ValueError, TypeError):
        errs.append("Enter a valid date, start time and end time.")
    if data["registration_fee"] is None or data["registration_fee"] < 0:
        errs.append("Fee must be 0 or more.")
    if data["early_bird_fee"] is not None:
        if data["early_bird_fee"] > data["registration_fee"] or not data["early_bird_until"]:
            errs.append("Early-bird price must be lower than the fee and needs an end date.")
    if data["max_participants"] < 1:
        errs.append("Maximum participants must be at least 1.")
    if not (1 <= data["team_min"] <= data["team_max"] <= 10):
        errs.append("Team size: minimum 1, maximum 10, and minimum cannot exceed maximum.")
    if data["coordinator_phone"] and not valid_phone(data["coordinator_phone"]):
        errs.append("Coordinator phone must be 10 digits.")
    if data["venue_id"] and not errs:
        cap = db.get().value("SELECT capacity FROM venue WHERE venue_id = %s", (data["venue_id"],))
        if cap and data["max_participants"] > cap:
            errs.append(f"Maximum participants is more than the venue capacity ({cap}).")
    return data, errs


@bp.route("/events/new", methods=["GET", "POST"], endpoint="event_new")
@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"], endpoint="event_edit")
@admin_only
def event_form(event_id=None):
    e = events.get(event_id, public_only=False) if event_id else None
    if event_id and not e:
        abort(404)
    if request.method == "POST":
        data, errs = _event_form(request.form)
        clash = None if errs else events.venue_clash(data["venue_id"], data["event_date"], data["start_time"],
                                                     data["end_time"], event_id)
        if clash and request.form.get("allow_clash") != "1":
            errs.append(f"Venue clash: \"{clash['event_name']}\" uses the same venue at an overlapping time. "
                        "Change the venue/time, or tick 'allow venue sharing' if this is intended.")
        if not errs:
            try:
                eid, change = events.save(data, g.user["user_id"], event_id)
            except db.DatabaseError as exc:
                errs.append(str(exc))
            else:
                msg = "Event saved."
                if change and request.form.get("announce") == "1":
                    news.save({"message": f"{data['event_name']}: {change}.", "link_url": url_for(
                        "public.event_detail", event_id=eid), "priority": "IMPORTANT", "starts_at": now(),
                        "ends_at": now() + dt.timedelta(days=7), "is_active": True}, g.user["user_id"])
                    n = notify.event_changed(eid, change + ".")
                    msg += f" Change announced in flash news and e-mailed to {n} registrant(s)."
                flash(msg, "success")
                return redirect(url_for("admin.events"))
        for m in errs:
            flash(m, "error")
        e = dict(e or {}, **{k: v for k, v in data.items()})
    return render_template("admin/event_form.html", e=e, event_id=event_id, categories=events.categories(),
                           venues=events.venues(), hhmm=hhmm,
                           staff=db.get().all("SELECT user_id, full_name, role FROM app_user WHERE role IN "
                                              "('ADMIN','COORDINATOR') AND is_active ORDER BY full_name"),
                           assigned={s["user_id"] for s in events.staff_for(event_id)} if event_id else set())


@bp.route("/events/<int:event_id>/staff", methods=["POST"])
@admin_only
def event_staff(event_id):
    ids = [int(x) for x in request.form.getlist("staff") if x.isdigit()]
    events.set_staff(event_id, ids, g.user["user_id"])
    flash("Coordinators / judges updated.", "success")
    return redirect(url_for("admin.event_edit", event_id=event_id))


@bp.route("/events/<int:event_id>/status", methods=["POST"])
@admin_only
def event_status(event_id):
    status = request.form.get("status")
    if status in ("OPEN", "CLOSED", "COMPLETED", "CANCELLED"):
        events.set_status(event_id, status, g.user["user_id"])
        if status == "CANCELLED":
            e = events.get(event_id, public_only=False)
            n = notify.event_changed(event_id, f"{e['event_name']} has been cancelled by the organisers. Paid fees "
                                               "will be refunded as per the refund policy.")
            flash(f"Event cancelled and {n} registrant(s) e-mailed. Refund paid registrations from Registrations.", "info")
        else:
            flash(f"Event marked {status.lower()}.", "success")
    return redirect(url_for("admin.events"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@admin_only
def event_delete(event_id):
    try:
        events.delete(event_id, g.user["user_id"])
        flash("Event deleted.", "success")
    except db.DatabaseError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.events"))


# ======================================================================================= flash news
@bp.route("/news", methods=["GET", "POST"], endpoint="news")
@admin_only
def news_page():
    if request.method == "POST":
        f = request.form
        nid = _int(f.get("news_id"))
        if f.get("action") == "delete" and nid:
            news.delete(nid, g.user["user_id"])
            flash("News item deleted.", "success")
            return redirect(url_for("admin.news"))
        msg = clean(f.get("message"), 300)
        link = clean(f.get("link_url"), 255)
        if link and not ((link.startswith("/") and not link.startswith("//")) or link.startswith("https://")):
            flash("Link must start with / (a page on this site) or https://", "error")
        elif len(msg) < 5:
            flash("Write the news message (at least 5 characters).", "error")
        else:
            news.save({"message": msg, "link_url": link or None,
                       "priority": f.get("priority") if f.get("priority") in ("INFO", "IMPORTANT", "URGENT") else "INFO",
                       "starts_at": parse_datetime_local(f.get("starts_at")) or now(),
                       "ends_at": parse_datetime_local(f.get("ends_at")), "is_active": f.get("is_active") == "1"},
                      g.user["user_id"], nid)
            flash("News saved - it appears in the rolling banner on the home page.", "success")
            return redirect(url_for("admin.news"))
    edit = news.get(_int(request.args.get("edit"))) if request.args.get("edit") else None
    return render_template("admin/news.html", items=news.all_items(), edit=edit)


# ======================================================================================= participants
@bp.route("/participants")
@admin_only
def participants():
    q = clean(request.args.get("q"), 80)
    sql, params = "SELECT * FROM v_participant_details", ()
    if q:
        sql += " WHERE full_name LIKE %s OR email LIKE %s OR phone LIKE %s OR college_name LIKE %s"
        params = (f"%{q}%",) * 4
    rows = db.get().all(sql + " ORDER BY full_name LIMIT 1000", params)
    if request.args.get("format") == "csv":
        cols = ["user_id", "full_name", "email", "phone", "college_name", "dept_name", "year_of_study", "gender",
                "active_registrations", "email_verified", "is_active", "created_at"]
        return Response(reports.to_csv(cols, [[r[c] for c in cols] for r in rows]), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=participants.csv"})
    return render_template("admin/participants.html", rows=rows, q=q)


@bp.route("/participants/<int:user_id>", methods=["GET", "POST"])
@admin_only
def participant_detail(user_id):
    p = db.get().one("SELECT * FROM v_participant_details WHERE user_id = %s", (user_id,))
    if not p:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "toggle":
            db.get().run("UPDATE app_user SET is_active = NOT is_active WHERE user_id = %s", (user_id,))
            audit.log(g.user["user_id"], "USER_TOGGLED", f"User #{user_id}")
            flash("Account status changed.", "success")
        elif action == "verify":
            users.mark_verified(user_id)
            flash("E-mail marked as verified.", "success")
        elif action == "reset":
            token = users.issue_token(user_id, "RESET")
            mailer.queue(p["email"], f"Reset your password - {settings.get('symposium_name')}", "reset",
                         name=p["full_name"].split()[0],
                         link=current_app.config["BASE_URL"] + url_for("auth.reset", token=token))
            flash("A password-reset link was e-mailed to the participant.", "success")
        return redirect(url_for("admin.participant_detail", user_id=user_id))
    from webapp.services import registrations
    return render_template("admin/participant_detail.html", p=p, regs=registrations.mine(user_id))


# ======================================================================================= staff accounts
@bp.route("/staff", methods=["GET", "POST"])
@admin_only
def staff_users():
    temp = None
    if request.method == "POST":
        f = request.form
        action = f.get("action")
        if action == "create":
            name, email, phone = clean(f.get("full_name"), 100), clean(f.get("email"), 120).lower(), clean(f.get("phone"), 15)
            role = f.get("role") if f.get("role") in ("ADMIN", "CASHIER", "COORDINATOR") else None
            if len(name) < 3 or not valid_email(email) or not role or (phone and not valid_phone(phone)):
                flash("Enter a name, valid e-mail, role and (optional) 10-digit phone.", "error")
            else:
                temp = random_password()
                try:
                    users.create_staff(name, email, phone, role, temp, g.user["user_id"])
                except db.DatabaseError as exc:
                    flash(str(exc), "error")
                    temp = None
                else:
                    flash(f"{role.title()} account created. Share the temporary password below privately - they "
                          "must change it at first sign-in.", "success")
        elif action in ("toggle", "reset"):
            uid = _int(f.get("user_id"))
            if uid == g.user["user_id"]:
                flash("You cannot change your own account here.", "error")
            elif action == "toggle":
                db.get().run("UPDATE app_user SET is_active = NOT is_active WHERE user_id = %s AND role <> 'PARTICIPANT'", (uid,))
                audit.log(g.user["user_id"], "STAFF_TOGGLED", f"User #{uid}")
                flash("Account status changed.", "success")
            else:
                temp = random_password()
                users.set_password(uid, temp, g.user["user_id"], "STAFF_PASSWORD_RESET")
                db.get().run("UPDATE app_user SET must_change_password = TRUE WHERE user_id = %s", (uid,))
                flash("Temporary password set - share it privately.", "success")
    rows = db.get().all("SELECT u.user_id, u.full_name, u.email, u.phone, u.role, u.is_active, u.is_demo, u.last_login, "
                        "GROUP_CONCAT(e.event_name ORDER BY e.event_date SEPARATOR ', ') AS events FROM app_user u "
                        "LEFT JOIN event_staff es ON es.user_id = u.user_id LEFT JOIN event e ON e.event_id = es.event_id "
                        "WHERE u.role <> 'PARTICIPANT' GROUP BY u.user_id ORDER BY FIELD(u.role, 'ADMIN', 'CASHIER', "
                        "'COORDINATOR'), u.full_name")
    return render_template("admin/staff.html", rows=rows, temp=temp)


# ======================================================================================= coupons
@bp.route("/coupons", methods=["GET", "POST"])
@admin_only
def coupons():
    if request.method == "POST":
        f = request.form
        if f.get("action") == "toggle":
            db.get().run("UPDATE coupon SET is_active = NOT is_active WHERE coupon_id = %s", (_int(f.get("coupon_id")),))
            flash("Coupon updated.", "success")
        else:
            code = clean(f.get("code"), 30).upper().replace(" ", "")
            kind = f.get("discount_type") if f.get("discount_type") in ("PERCENT", "FLAT") else None
            value = _dec(f.get("discount_value"))
            if not code or not kind or not value or value <= 0 or (kind == "PERCENT" and value > 100):
                flash("Enter a code, type and a valid discount (percent must be 1-100).", "error")
            else:
                try:
                    db.get().run("INSERT INTO coupon (code, discount_type, discount_value, event_id, max_uses, valid_until) "
                                 "VALUES (%s, %s, %s, %s, %s, %s)", (code, kind, value, _int(f.get("event_id")) or None,
                                                                     _int(f.get("max_uses")) or None,
                                                                     parse_datetime_local(f.get("valid_until"))))
                    audit.log(g.user["user_id"], "COUPON_CREATED", code)
                    flash(f"Coupon {code} created.", "success")
                except db.DatabaseError as exc:
                    flash(str(exc), "error")
        return redirect(url_for("admin.coupons"))
    rows = db.get().all("SELECT c.*, e.event_name FROM coupon c LEFT JOIN event e ON e.event_id = c.event_id "
                        "ORDER BY c.is_active DESC, c.code")
    return render_template("admin/coupons.html", rows=rows, events=events.list_events(public_only=False))


# ======================================================================================= master lists
MASTERS = {
    "venue": ("Venues", "venue", "venue_id", [("venue_name", "Name", 100), ("location", "Location", 150),
                                               ("capacity", "Capacity", 0)]),
    "category": ("Event categories", "event_category", "category_id", [("category_name", "Name", 50)]),
    "college": ("Colleges", "college", "college_id", [("college_name", "Name", 150), ("city", "City", 60)]),
    "department": ("Departments", "department", "dept_id", [("dept_name", "Name", 100)]),
}


@bp.route("/lists", methods=["GET", "POST"])
@admin_only
def masters():
    kind = request.values.get("kind", "venue")
    if kind not in MASTERS:
        abort(404)
    title, table, pk, cols = MASTERS[kind]
    if request.method == "POST":
        f = request.form
        rid = _int(f.get("id"))
        try:
            if f.get("action") == "delete" and rid:
                db.get().run(f"DELETE FROM {table} WHERE {pk} = %s", (rid,))
                flash("Deleted.", "success")
            else:
                vals = []
                for c, _label, maxlen in cols:
                    v = clean(f.get(c), maxlen or 10)
                    if maxlen == 0:
                        v = _int(v)
                        if not v or v < 1:
                            raise db.DatabaseError("Capacity must be a positive number.")
                    vals.append(v or None)
                if not vals[0]:
                    raise db.DatabaseError("Name is required.")
                if rid:
                    db.get().run(f"UPDATE {table} SET {', '.join(c + ' = %s' for c, _, _ in cols)} WHERE {pk} = %s",
                                 tuple(vals) + (rid,))
                else:
                    db.get().run(f"INSERT INTO {table} ({', '.join(c for c, _, _ in cols)}) "
                                 f"VALUES ({', '.join(['%s'] * len(cols))})", tuple(vals))
                flash("Saved.", "success")
            audit.log(g.user["user_id"], "LIST_CHANGED", f"{title}")
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin.masters", kind=kind))
    rows = db.get().all(f"SELECT {pk} AS id, {', '.join(c for c, _, _ in cols)} FROM {table} ORDER BY 2")
    return render_template("admin/masters.html", kind=kind, kinds=MASTERS, title=title, cols=cols, rows=rows,
                           edit=next((r for r in rows if r["id"] == _int(request.args.get("edit"))), None))


# ======================================================================================= feedback
@bp.route("/feedback")
@admin_only
def feedback():
    rows = db.get().all("SELECT f.*, e.event_name, u.full_name FROM feedback f JOIN registration r ON r.reg_id = f.reg_id "
                        "JOIN event e ON e.event_id = r.event_id JOIN app_user u ON u.user_id = r.user_id "
                        "ORDER BY f.created_at DESC LIMIT 500")
    summary = db.get().all("SELECT e.event_name, COUNT(*) AS n, ROUND(AVG(f.rating), 2) AS avg FROM feedback f "
                           "JOIN registration r ON r.reg_id = f.reg_id JOIN event e ON e.event_id = r.event_id "
                           "GROUP BY e.event_id, e.event_name ORDER BY avg DESC")
    return render_template("admin/feedback.html", rows=rows, summary=summary)


# ======================================================================================= reports & SQL
@bp.route("/reports", endpoint="reports")
@admin_only
def reports_page():
    key = request.args.get("r", "events")
    if key not in reports.REPORTS:
        abort(404)
    title, cols, rows = reports.run(key)
    fmt = request.args.get("format")
    if fmt == "csv":
        return Response(reports.to_csv(cols, rows), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={key}.csv"})
    if fmt == "pdf":
        return Response(pdf.table(title, settings.get("symposium_name"), cols, rows, landscape=len(cols) > 5),
                        mimetype="application/pdf", headers={"Content-Disposition": f"inline; filename={key}.pdf"})
    return render_template("admin/reports.html", key=key, title=title, cols=cols, rows=rows,
                           all_reports=reports.REPORTS, sql=reports.REPORTS[key][1])


SQL_SAMPLES = {
    "Event summary (view)": "SELECT event_name, registered, confirmed, seats_left, revenue FROM v_event_summary",
    "Seats left (stored function)": "SELECT event_name, fn_seats_left(event_id) AS seats_left, fn_event_price(event_id) AS price FROM event",
    "Triggers": "SELECT TRIGGER_NAME, ACTION_TIMING, EVENT_MANIPULATION, EVENT_OBJECT_TABLE FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()",
    "Foreign keys": "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL",
    "Index use (EXPLAIN)": "EXPLAIN SELECT * FROM registration WHERE event_id = 1 AND status = 'CONFIRMED'",
    "Payments by method (GROUP BY)": "SELECT method, status, COUNT(*) AS n, SUM(amount) AS total FROM payment GROUP BY method, status",
    "Top colleges": "SELECT college_name, points, registrations FROM v_college_leaderboard ORDER BY points DESC LIMIT 5",
}


@bp.route("/sql", methods=["GET", "POST"])
@admin_only
@rate_limit("sql", limit=60, window=300)
def sql_console():
    if not settings.flag("sql_console_enabled"):
        flash("The SQL console is switched off in Settings.", "info")
        return redirect(url_for("staff.dashboard"))
    sql = request.form.get("sql") or request.args.get("sample") and SQL_SAMPLES.get(request.args["sample"]) or \
        SQL_SAMPLES["Event summary (view)"]
    cols, rows, error = [], [], None
    ro = db.readonly()
    if request.method == "POST" or request.args.get("sample"):
        text = (sql or "").strip().rstrip(";").strip()
        first = text.split(None, 1)[0].upper() if text else ""
        if ";" in text or first not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"):
            error = "Only one SELECT / SHOW / DESCRIBE / EXPLAIN statement is allowed."
        elif ro is None:
            error = "The read-only database user is not configured (run manage.py init-db)."
        else:
            try:
                cols, rows = ro.read_only_query(text)
                audit.log(g.user["user_id"], "SQL_CONSOLE", text[:200])
            except db.DatabaseError as exc:
                error = str(exc)
    return render_template("admin/sql.html", sql=sql, cols=cols, rows=rows, error=error, samples=SQL_SAMPLES)


# ======================================================================================= audit & outbox
@bp.route("/audit", endpoint="audit")
@admin_only
def audit_page():
    q = clean(request.args.get("q"), 60)
    sql = ("SELECT a.*, IFNULL(u.full_name, 'System') AS who FROM audit_log a LEFT JOIN app_user u "
           "ON u.user_id = a.user_id")
    params: tuple = ()
    if q:
        sql += " WHERE a.action LIKE %s OR a.details LIKE %s OR u.full_name LIKE %s"
        params = (f"%{q}%",) * 3
    return render_template("admin/audit.html", rows=db.get().all(sql + " ORDER BY a.log_id DESC LIMIT 500", params), q=q)


@bp.route("/outbox", methods=["GET", "POST"])
@admin_only
def outbox():
    if request.method == "POST":
        if request.form.get("action") == "retry":
            db.get().run("UPDATE email_outbox SET status = 'QUEUED', attempts = 0 WHERE status = 'FAILED'")
            mailer.wake()
            flash("Failed e-mails queued again.", "success")
        return redirect(url_for("admin.outbox"))
    view = db.get().one("SELECT * FROM email_outbox WHERE mail_id = %s", (_int(request.args.get("id")),)) \
        if request.args.get("id") else None
    rows = db.get().all("SELECT mail_id, to_email, subject, status, attempts, last_error, created_at, sent_at "
                        "FROM email_outbox ORDER BY mail_id DESC LIMIT 300")
    return render_template("admin/outbox.html", rows=rows, view=view, mode=current_app.config["MAIL_MODE"])


# ======================================================================================= settings
SETTING_GROUPS = [
    ("Branding & contact", [("symposium_name", "Symposium name", "text"), ("tagline", "Tagline", "text"),
                            ("college_name", "College", "text"), ("host_institution", "Organising department", "text"),
                            ("symposium_dates", "Dates shown on the home page", "text"),
                            ("venue_address", "Address", "text"), ("contact_email", "Contact e-mail", "email"),
                            ("contact_phone", "Contact phone", "text"), ("about_text", "About (home page)", "textarea")]),
    ("Registration rules", [("registrations_open", "Online registrations open", "bool"),
                            ("signups_open", "New sign-ups allowed", "bool"),
                            ("max_events_per_participant", "Max events per participant (0 = no limit)", "number"),
                            ("online_hold_minutes", "Minutes to hold a seat for online payment", "number"),
                            ("desk_hold_minutes", "Minutes to hold a seat for 'pay at desk'", "number")]),
    ("Payments", [("pay_upi_qr", "Accept UPI QR (direct to college account)", "bool"),
                  ("upi_id", "College UPI ID (e.g. collegename@okaxis)", "text"),
                  ("upi_payee_name", "Payee name shown in UPI apps", "text"),
                  ("pay_gateway", "Accept online gateway (Razorpay)", "bool"),
                  ("gateway_convenience_fee", "Convenience fee added to gateway payments (Rs, 0 = none)", "number"),
                  ("pay_cash", "Allow 'pay at the registration desk'", "bool")]),
    ("Policies (shown in the footer)", [("terms_text", "Terms & conditions", "textarea"),
                                        ("privacy_note", "Privacy policy", "textarea"),
                                        ("refund_policy", "Refund policy", "textarea")]),
    ("Advanced", [("sql_console_enabled", "Enable the read-only SQL console", "bool")]),
]


@bp.route("/settings", methods=["GET", "POST"])
@admin_only
def settings_page():
    cfg = current_app.config["CFG"]
    if request.method == "POST":
        section = request.form.get("section")
        if section == "site":
            values = {}
            for _group, fields in SETTING_GROUPS:
                for key, _label, kind in fields:
                    if kind == "bool":
                        values[key] = "1" if request.form.get(key) == "1" else "0"
                    elif key in request.form:
                        v = clean(request.form.get(key), 5000)
                        if kind == "number":
                            v = str(max(0, _int(v, 0)))
                        values[key] = v
            if values.get("upi_id") and "@" not in values["upi_id"]:
                flash("The UPI ID must look like name@bank.", "error")
            else:
                settings.save(values)
                audit.log(g.user["user_id"], "SETTINGS_SAVED", "Site settings")
                flash("Settings saved.", "success")
        elif section == "logo":
            f = request.files.get("logo")
            if f and f.filename:
                ext = os.path.splitext(f.filename.lower())[1]
                head = f.stream.read(12)
                f.stream.seek(0)
                if ext not in (".png", ".jpg", ".jpeg") or not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8")):
                    flash("Upload a PNG or JPG image.", "error")
                else:
                    suffix = ".png" if head.startswith(b"\x89PNG") else ".jpg"
                    name = f"logo-{secrets.token_hex(4)}{suffix}"
                    f.save(os.path.join(config.UPLOAD_DIR, name))
                    settings.save({"logo_path": name})
                    flash("Logo updated.", "success")
            elif request.form.get("remove"):
                settings.save({"logo_path": ""})
                flash("Logo removed.", "success")
        elif section == "gateway":
            p = cfg["payment"]
            mode = request.form.get("gateway_mode")
            if mode in ("mock", "test", "live"):
                p["gateway_mode"] = mode
            p["razorpay_key_id"] = clean(request.form.get("razorpay_key_id"), 60)
            for key in ("razorpay_key_secret", "razorpay_webhook_secret"):
                if request.form.get(key):                        # blank = keep the existing secret
                    p[key] = request.form.get(key).strip()
            if mode in ("test", "live") and not (p["razorpay_key_id"] and p["razorpay_key_secret"]):
                flash("Enter the Razorpay Key ID and Key Secret for test/live mode.", "error")
            else:
                config.save(cfg)
                current_app.config["GATEWAY_MODE"] = p["gateway_mode"]
                audit.log(g.user["user_id"], "GATEWAY_SETTINGS", f"mode={p['gateway_mode']}")
                flash("Payment gateway settings saved.", "success")
        elif section == "mail":
            m = cfg["mail"]
            m["mode"] = "smtp" if request.form.get("mode") == "smtp" else "demo"
            for key in ("smtp_host", "smtp_port", "smtp_user", "from_address"):
                m[key] = clean(request.form.get(key), 120)
            if request.form.get("smtp_password"):
                m["smtp_password"] = request.form.get("smtp_password").strip()
            config.save(cfg)
            current_app.config["MAIL_MODE"] = m["mode"]
            audit.log(g.user["user_id"], "MAIL_SETTINGS", f"mode={m['mode']}")
            if request.form.get("test") and m["mode"] == "smtp":
                ok, msg = mailer.test_connection(cfg)
                flash(msg, "success" if ok else "error")
            else:
                flash("E-mail settings saved.", "success")
        return redirect(url_for("admin.settings_page"))
    return render_template("admin/settings.html", groups=SETTING_GROUPS, s=settings.all_settings(), cfg=cfg,
                           webhook_url=current_app.config["BASE_URL"] + url_for("payments.razorpay_webhook"))


# ======================================================================================= backups
@bp.route("/backups", methods=["GET", "POST"], endpoint="backups")
@admin_only
def backups_page():
    cfg = current_app.config["CFG"]
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "create":
                flash(f"Backup created: {backups.create(cfg)}", "success")
            elif action == "restore":
                if not users.check_password(g.user["user_id"], request.form.get("password", "")):
                    flash("Password incorrect - restore cancelled.", "error")
                else:
                    f = request.files.get("file")
                    name = request.form.get("name")
                    raw = f.read() if f and f.filename else (open(backups.path_for(name), "rb").read()
                                                             if backups.path_for(name) else None)
                    if not raw:
                        flash("Choose a backup to restore.", "error")
                    else:
                        res = backups.restore(raw, cfg)
                        audit.log(None, "BACKUP_RESTORED", f"from {res['created']}")
                        flash(f"Restored the backup from {res['created']}. A safety backup of the previous data was "
                              f"saved as {res['safety_backup']}. Please sign in again.", "success")
                        return redirect(url_for("auth.login"))
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin.backups"))
    return render_template("admin/backups.html", items=backups.listing(), cfg=cfg)


@bp.route("/backups/<name>")
@admin_only
def backup_download(name):
    path = backups.path_for(name)
    if not path:
        abort(404)
    audit.log(g.user["user_id"], "BACKUP_DOWNLOADED", name)
    return send_file(path, as_attachment=True, download_name=name)


# ======================================================================================= demo / go live
@bp.route("/data", methods=["GET", "POST"])
@admin_only
def data_mode():
    if request.method == "POST":
        action = request.form.get("action")
        if not users.check_password(g.user["user_id"], request.form.get("password", "")):
            flash("Password incorrect.", "error")
            return redirect(url_for("admin.data_mode"))
        try:
            if action == "demo":
                backups.create(current_app.config["CFG"], label="predemo")
                flash(demo.load_demo(g.user["user_id"]), "success")
            elif action == "golive":
                if request.form.get("confirm_text") != "GO LIVE":
                    flash("Type GO LIVE in capitals to confirm.", "error")
                    return redirect(url_for("admin.data_mode"))
                backups.create(current_app.config["CFG"], label="prelive")
                msg = demo.go_live(g.user["user_id"])
                if g.user["is_demo"]:
                    return redirect(url_for("auth.login"))
                flash(msg + " A backup was saved first, just in case.", "success")
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin.data_mode"))
    counts = db.get().one("SELECT (SELECT COUNT(*) FROM app_user WHERE is_demo) AS demo_users, "
                          "(SELECT COUNT(*) FROM event WHERE is_demo) AS demo_events, "
                          "(SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT' AND NOT is_demo) AS real_people, "
                          "(SELECT COUNT(*) FROM app_user WHERE role = 'ADMIN' AND NOT is_demo AND is_active) AS real_admins")
    sample = os.path.exists(os.path.join(config.UPLOAD_DIR, "sample_bank_statement.csv"))
    return render_template("admin/data_mode.html", c=counts, sample=sample)


@bp.route("/data/sample-statement.csv")
@admin_only
def sample_statement():
    path = os.path.join(config.UPLOAD_DIR, "sample_bank_statement.csv")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name="sample_bank_statement.csv")
