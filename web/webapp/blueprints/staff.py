"""Staff area shared by admins, cashiers and coordinators.

ADMIN        everything
CASHIER      desk registration, payment verification, reconciliation, check-in, registrations (read)
COORDINATOR  check-in, registrations, scoring & results - only for events assigned to them
"""
import datetime as dt
import re

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   url_for)

from webapp import db
from webapp.security import (STAFF_ROLES, clean, random_password, rate_limit, roles_required, valid_email,
                             valid_phone)
from webapp.services import (audit, cashdesk, events, notify, pdf, registrations, reports, results, settings,
                             users)
from webapp.util import now, today

bp = Blueprint("staff", __name__, url_prefix="/staff")
CODE_RE = re.compile(r"([A-HJ-NP-Z2-9]{12})")


def _event_scope():
    """None = all events; list = the coordinator's events."""
    if g.user["role"] == "COORDINATOR":
        return [e["event_id"] for e in events.events_for_staff(g.user)]
    return None


def _can_see(event_id):
    scope = _event_scope()
    return scope is None or event_id in scope


# ------------------------------------------------------------------ dashboard
@bp.route("/")
@roles_required(*STAFF_ROLES)
def dashboard():
    scope = _event_scope()
    per_event = reports.per_event(scope)
    todays = [e for e in per_event if e["event_date"] == today()]
    return render_template("staff/dashboard.html", s=reports.dashboard(scope), todays=todays,
                           bar=reports.bar_chart(per_event[:12], "event_name", "registered", "max_participants"),
                           line=reports.line_chart(reports.daily(14)) if scope is None else None,
                           to_verify=len(cashdesk.queue("SUBMITTED")) if g.user["role"] != "COORDINATOR" else 0)


# ------------------------------------------------------------------ QR check-in
@bp.route("/checkin", methods=["GET", "POST"])
@roles_required(*STAFF_ROLES)
@rate_limit("checkin", limit=600, window=600)
def checkin():
    raw = (request.values.get("code") or "").strip().upper()
    m = CODE_RE.search(raw.split("CODE=")[-1]) if raw else None
    code = m.group(1) if m else ""
    result = None
    if raw and not code:
        result = {"kind": "bad", "title": "Not a valid ticket", "msg": "That code is not a ticket from this website."}
    elif code:
        r = db.get().one("SELECT * FROM v_registration_details WHERE ticket_code = %s", (code,))
        if not r:
            result = {"kind": "bad", "title": "Ticket not found", "msg": "No registration has this ticket code."}
        elif not _can_see(r["event_id"]):
            result = {"kind": "bad", "title": "Different event", "msg": f"This ticket is for {r['event_name']}, "
                      "which is not assigned to you."}
        elif r["status"] != "CONFIRMED":
            result = {"kind": "bad", "title": f"Not confirmed ({r['status'].title()})", "r": r,
                      "msg": "Payment is not complete. Send the participant to the registration desk."}
        elif r["attended"]:
            result = {"kind": "warn", "title": "Already checked in", "r": r,
                      "msg": f"Checked in at {r['checked_in_at'].strftime('%I:%M %p, %d %b')}."}
        elif request.method == "POST" and request.form.get("confirm") == "1":
            n = db.get().run("UPDATE registration SET attended = TRUE, checked_in_at = NOW(), checked_in_by = %s "
                             "WHERE reg_id = %s AND status = 'CONFIRMED' AND NOT attended", (g.user["user_id"], r["reg_id"]))
            r = registrations.get(r["reg_id"])
            result = {"kind": "ok", "title": "Checked in ✓" if n else "Already checked in", "r": r,
                      "msg": "Welcome! Entry recorded.", "done": True}
        else:
            warn = "" if r["event_date"] == today() else f" Note: this event is on {r['event_date'].strftime('%d %b')}."
            result = {"kind": "ok", "title": "Valid ticket", "r": r, "msg": "Confirm entry below." + warn,
                      "confirm": True}
    team = registrations.team(result["r"]["reg_id"]) if result and result.get("r") else []
    return render_template("staff/checkin.html", result=result, code=code, team=team)


# ------------------------------------------------------------------ registration desk (walk-ins)
@bp.route("/desk", methods=["GET", "POST"])
@roles_required("ADMIN", "CASHIER")
def desk():
    q = clean(request.values.get("q"), 120)
    people = []
    if q:
        like = f"%{q}%"
        people = db.get().all("SELECT user_id, full_name, email, phone, college_name, dept_name FROM v_participant_details "
                              "WHERE email LIKE %s OR phone LIKE %s OR full_name LIKE %s ORDER BY full_name LIMIT 20",
                              (like, like, like))
    return render_template("staff/desk.html", q=q, people=people, colleges=users.colleges(),
                           departments=users.departments(), form=request.form)


@bp.route("/desk/new", methods=["POST"])
@roles_required("ADMIN", "CASHIER")
def desk_new():
    f = request.form
    name, email, phone = clean(f.get("full_name"), 100), clean(f.get("email"), 120).lower(), clean(f.get("phone"), 15)
    college, dept, year = clean(f.get("college"), 150), f.get("dept_id", type=int), f.get("year", type=int)
    if len(name) < 3 or not valid_email(email) or not valid_phone(phone) or len(college) < 3 or not dept \
            or year not in range(1, 6):
        flash("Fill in name, a valid e-mail, 10-digit phone, college, department and year.", "error")
        return redirect(url_for("staff.desk"))
    try:
        uid = users.create_participant(name, email, phone, random_password(), college, dept, year, None, verified=True)
    except db.DatabaseError as exc:
        flash(str(exc), "error")
        return redirect(url_for("staff.desk", q=email))
    token = users.issue_token(uid, "RESET")
    from webapp.services import mailer
    mailer.queue(email, f"Your {settings.get('symposium_name')} account", "notice",
                 heading="Your account is ready",
                 lines=[f"Hi {name.split()[0]}, the registration desk created an account for you.",
                        "Set a password to see your tickets and download certificates online."],
                 button="Set my password", url=current_app.config["BASE_URL"] + url_for("auth.reset", token=token))
    audit.log(g.user["user_id"], "DESK_ACCOUNT", email)
    flash(f"Account created for {name}. They will get an e-mail to set a password.", "success")
    return redirect(url_for("staff.desk_person", user_id=uid))


@bp.route("/desk/<int:user_id>", methods=["GET", "POST"])
@roles_required("ADMIN", "CASHIER")
def desk_person(user_id):
    person = db.get().one("SELECT * FROM v_participant_details WHERE user_id = %s", (user_id,))
    if not person:
        abort(404)
    if request.method == "POST":
        event_ids = [int(x) for x in request.form.getlist("event_id") if x.isdigit()]
        method = request.form.get("method")
        utr = clean(request.form.get("utr"), 22).upper()
        if not event_ids:
            flash("Select at least one event.", "error")
        elif method not in ("CASH", "UPI_QR"):
            flash("Choose how the participant paid.", "error")
        else:
            done, failed = [], []
            for eid in event_ids:
                try:
                    team_name = clean(request.form.get(f"team_{eid}"), 60)
                    members = [{"name": clean(n, 100)} for n in request.form.get(f"members_{eid}", "").split(",")
                               if clean(n, 100)]
                    res = registrations.register(user_id, eid, team_name, members, clean(request.form.get("coupon"), 30),
                                                 method, source="DESK",
                                                 cash_collected_by=g.user["user_id"] if method == "CASH" else None,
                                                 actor_id=g.user["user_id"])
                    if method == "UPI_QR" and res["status"] == "PENDING":
                        p = registrations.open_payment(res["reg_id"])
                        cashdesk.verify(p["payment_id"], g.user["user_id"],
                                        f"UPI at desk{(' UTR ' + utr) if utr else ''} - verified by cashier")
                    notify.registration_received(res["reg_id"])
                    done.append(res["reg_id"])
                except (registrations.RegistrationError, db.DatabaseError) as exc:
                    name = next((e["event_name"] for e in events.list_events(False) if e["event_id"] == eid), eid)
                    failed.append(f"{name}: {exc}")
            if done:
                flash(f"Registered for {len(done)} event(s). Print or show the receipt.", "success")
            for msg in failed:
                flash(msg, "error")
            return redirect(url_for("staff.desk_person", user_id=user_id))
    regs = registrations.mine(user_id)
    taken = {r["event_id"] for r in regs if r["status"] != "CANCELLED"}
    open_events = [e for e in events.list_events(public_only=False) if e["status"] == "OPEN" and not e["is_past"]]
    return render_template("staff/desk_person.html", p=person, regs=regs, open_events=open_events, taken=taken)


@bp.route("/desk/receipt/<int:reg_id>.pdf")
@roles_required("ADMIN", "CASHIER")
def desk_receipt(reg_id):
    r = registrations.get(reg_id)
    if not r:
        abort(404)
    return Response(pdf.receipt(r, settings.all_settings(), registrations.team(reg_id)), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=REG{reg_id:05d}.pdf"})


# ------------------------------------------------------------------ payments & reconciliation
@bp.route("/payments", methods=["GET", "POST"])
@roles_required("ADMIN", "CASHIER")
def payments():
    if request.method == "POST":
        pid = request.form.get("payment_id", type=int)
        action = request.form.get("action")
        try:
            if action == "verify":
                cashdesk.verify(pid, g.user["user_id"], "UPI reference verified manually by cashier")
                flash("Payment verified - participant confirmed and e-mailed.", "success")
            elif action == "reject":
                cashdesk.reject(pid, g.user["user_id"], clean(request.form.get("reason"), 150) or "reference not found")
                flash("Reference rejected - the participant was asked to check it.", "info")
            elif action == "cash":
                cashdesk.record_cash(request.form.get("reg_id", type=int), g.user["user_id"])
                flash("Cash recorded - participant confirmed.", "success")
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("staff.payments"))
    return render_template("staff/payments.html", submitted=cashdesk.queue("SUBMITTED"),
                           pending=cashdesk.queue("PENDING"), bank=cashdesk.unmatched_bank_lines())


@bp.route("/payments/reconcile", methods=["POST"])
@roles_required("ADMIN", "CASHIER")
def reconcile():
    f = request.files.get("statement")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Upload the bank statement as a .csv file (export it from net banking).", "error")
        return redirect(url_for("staff.payments"))
    summary = cashdesk.reconcile(f.read(), g.user["user_id"])
    return render_template("staff/reconcile.html", s=summary)


@bp.route("/cash-report")
@roles_required("ADMIN", "CASHIER")
def cashier_report():
    day = request.args.get("day")
    try:
        d = dt.date.fromisoformat(day) if day else today()
    except ValueError:
        d = today()
    rows = cashdesk.cashier_report(None if request.args.get("all") else d)
    return render_template("staff/cash_report.html", rows=rows, day=d, all=bool(request.args.get("all")),
                           total=sum(r["total"] for r in rows))


# ------------------------------------------------------------------ registrations
@bp.route("/registrations", endpoint="registrations")
@roles_required(*STAFF_ROLES)
def registrations_list():
    scope = _event_scope()
    ev = request.args.get("event", type=int)
    st = request.args.get("status") if request.args.get("status") in ("PENDING", "CONFIRMED", "WAITLISTED",
                                                                        "CANCELLED") else None
    q = clean(request.args.get("q"), 80)
    sql, params = "SELECT * FROM v_registration_details WHERE 1=1", []
    if scope is not None:
        sql += " AND event_id IN (" + ",".join(["%s"] * len(scope or [0])) + ")"
        params += scope or [0]
    if ev:
        sql += " AND event_id = %s"
        params.append(ev)
    if st:
        sql += " AND status = %s"
        params.append(st)
    if q:
        sql += (" AND (full_name LIKE %s OR email LIKE %s OR phone LIKE %s OR college_name LIKE %s OR team_name LIKE %s "
                "OR ticket_code = %s OR utr = %s OR reg_id = %s)")
        params += [f"%{q}%"] * 5 + [q.upper(), q.upper(), q if q.isdigit() else -1]
    sql += " ORDER BY event_date, event_name, full_name LIMIT 2000"
    rows = db.get().all(sql, tuple(params))
    fmt = request.args.get("format")
    if fmt == "csv":
        cols = ["reg_id", "event_name", "full_name", "email", "phone", "college_name", "dept_name", "team_name",
                "team_size", "status", "attended", "payment_method", "payment_status", "amount", "utr", "registered_at"]
        data = reports.to_csv(cols, [[r[c] for c in cols] for r in rows])
        return Response(data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=registrations.csv"})
    if fmt == "sheet" and ev:
        e = events.get(ev, public_only=False)
        data = pdf.table(f"Attendance sheet - {e['event_name']}", events.describe_slot(e),
                         ["#", "Reg ID", "Name", "College", "Phone", "Team"],
                         [(i, f"REG-{r['reg_id']:05d}", r["full_name"], r["college_name"] or "", r["phone"] or "",
                           r["team_name"] or "") for i, r in enumerate([x for x in rows if x["status"] == "CONFIRMED"], 1)],
                         widths=[6, 18, 40, 55, 22, 25], signature=True)
        return Response(data, mimetype="application/pdf",
                        headers={"Content-Disposition": f"inline; filename=attendance-{ev}.pdf"})
    evs = events.events_for_staff(g.user) if scope is not None else events.list_events(public_only=False)
    return render_template("staff/registrations.html", rows=rows, events=evs, ev=ev, st=st, q=q)



@bp.route("/registrations/<int:reg_id>", methods=["GET", "POST"])
@roles_required(*STAFF_ROLES)
def registration(reg_id):
    r = registrations.get(reg_id)
    if not r or not _can_see(r["event_id"]):
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "cancel" and g.user["role"] == "ADMIN":
                reason = clean(request.form.get("reason"), 200)
                db.get().call("sp_cancel_registration", (reg_id, g.user["user_id"], reason))
                notify.cancelled(reg_id, reason)
                promoted = registrations.promote_waitlist(r["event_id"])
                flash("Registration cancelled." + (" The next person on the waitlist was offered the seat."
                                                   if promoted else ""), "success")
            elif action == "attend" and r["status"] == "CONFIRMED":
                present = request.form.get("present") == "1"
                db.get().run("UPDATE registration SET attended = %s, checked_in_at = IF(%s, NOW(), NULL), "
                             "checked_in_by = %s WHERE reg_id = %s", (present, present, g.user["user_id"], reg_id))
                flash("Attendance updated.", "success")
            elif action == "cash" and g.user["role"] in ("ADMIN", "CASHIER"):
                cashdesk.record_cash(reg_id, g.user["user_id"])
                flash("Cash recorded - registration confirmed.", "success")
            elif action == "resend":
                notify.registration_received(reg_id)
                flash("Registration e-mail sent again.", "success")
            else:
                abort(403)
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("staff.registration", reg_id=reg_id))
    history = db.get().all("SELECT p.*, u.full_name AS staff FROM payment p LEFT JOIN app_user u "
                           "ON u.user_id = p.collected_by WHERE p.reg_id = %s ORDER BY p.payment_id", (reg_id,))
    return render_template("staff/registration.html", r=r, team=registrations.team(reg_id), history=history)


# ------------------------------------------------------------------ scoring & results
@bp.route("/scoring")
@roles_required("ADMIN", "COORDINATOR")
def scoring_home():
    return render_template("staff/scoring_home.html", events=events.events_for_staff(g.user))


@bp.route("/scoring/<int:event_id>", methods=["GET", "POST"])
@roles_required("ADMIN", "COORDINATOR")
def scoring(event_id):
    if not events.can_manage(g.user, event_id):
        abort(403)
    e = events.get(event_id, public_only=False)
    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "scores":
                scores = {}
                for key, val in request.form.items():
                    if key.startswith("score_"):
                        reg_id = int(key[6:])
                        val = val.strip()
                        score = None
                        if val:
                            score = float(val)
                            if not 0 <= score <= 100:
                                raise ValueError
                        scores[reg_id] = (score, clean(request.form.get(f"remarks_{reg_id}"), 255))
                n = results.save_scores(event_id, g.user["user_id"], scores)
                flash(f"Saved {n} score(s).", "success")
            elif action == "auto":
                results.set_winners(event_id, results.auto_rank(event_id), g.user["user_id"])
                flash("Top three by average score selected. Review and publish when ready.", "success")
            elif action == "winners":
                pos = {p: request.form.get(f"pos{p}", type=int) for p in (1, 2, 3)}
                results.set_winners(event_id, pos, g.user["user_id"])
                flash("Winners saved.", "success")
            elif action in ("publish", "unpublish"):
                results.publish(event_id, action == "publish", g.user["user_id"])
                if action == "publish":
                    for reg in db.get().all("SELECT reg_id FROM registration WHERE event_id = %s AND attended "
                                            "AND status = 'CONFIRMED'", (event_id,)):
                        notify.certificate_ready(reg["reg_id"])
                flash("Results published - certificates are now available." if action == "publish"
                      else "Results hidden from the public site.", "success")
        except ValueError:
            flash("Scores must be numbers between 0 and 100.", "error")
        except db.DatabaseError as exc:
            flash(str(exc), "error")
        return redirect(url_for("staff.scoring", event_id=event_id))
    board = results.score_board(event_id)
    return render_template("staff/scoring.html", e=e, board=board, mine=results.my_scores(event_id, g.user["user_id"]),
                           winners={b["position"]: b["reg_id"] for b in board if b["position"]})
