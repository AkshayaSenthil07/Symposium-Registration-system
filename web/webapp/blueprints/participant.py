"""Participant area: dashboard, registering, tickets, receipts, certificates, feedback, profile.

Participants cannot cancel registrations themselves - only admins can (agreed rule).
"""
from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   url_for)

from webapp import db
from webapp.security import clean, roles_required, valid_email, valid_phone
from webapp.services import events, notify, pdf, qr, registrations, results, settings, users

bp = Blueprint("participant", __name__, url_prefix="/me")


def _mine(reg_id):
    r = registrations.for_user(reg_id, g.user["user_id"])
    if not r:
        abort(404)
    return r


@bp.route("/")
@roles_required("PARTICIPANT")
def dashboard():
    regs = registrations.mine(g.user["user_id"])
    active = [r for r in regs if r["status"] != "CANCELLED"]
    return render_template("participant/dashboard.html", regs=active,
                           pending=[r for r in active if r["status"] == "PENDING"],
                           upcoming=[r for r in active if r["status"] == "CONFIRMED" and not r["attended"]])


@bp.route("/register/<int:event_id>", methods=["GET", "POST"])
@roles_required("PARTICIPANT")
def register(event_id):
    e = events.get(event_id)
    if not e:
        abort(404)
    methods = registrations.enabled_methods()
    form = request.form
    price = None
    if request.method == "POST":
        members, errors = _members_from_form(form, e["team_max"] - 1)
        coupon = clean(form.get("coupon"), 30)
        try:
            price = registrations.quote(event_id, coupon)
        except registrations.RegistrationError as exc:
            errors.append(str(exc))
        if form.get("action") == "register" and not errors:
            method = form.get("method") if price and price["total"] > 0 else "UPI_QR"
            if price and price["total"] > 0 and method not in methods:
                errors.append("Choose a payment method.")
            else:
                try:
                    res = registrations.register(g.user["user_id"], event_id, clean(form.get("team_name"), 60),
                                                 members, coupon, method or "UPI_QR")
                except registrations.RegistrationError as exc:
                    errors.append(str(exc))
                else:
                    notify.registration_received(res["reg_id"])
                    flash({"CONFIRMED": "You're registered! Your QR ticket is ready.",
                           "WAITLISTED": "The event is full - you're on the waitlist. We'll e-mail you if a seat opens.",
                           "PENDING": "Seat reserved. Complete the payment below to confirm it."}[res["status"]],
                          "success")
                    return redirect(url_for("participant.registration", reg_id=res["reg_id"]))
        for msg in errors:
            flash(msg, "error")
    else:
        price = registrations.quote(event_id)
    return render_template("participant/register.html", e=e, form=form, price=price, methods=methods,
                           fee=_gateway_fee())


def _gateway_fee():
    return settings.number("gateway_convenience_fee")


def _members_from_form(form, max_extra):
    members, errors = [], []
    names = form.getlist("member_name")[:max_extra]
    emails = form.getlist("member_email")[:max_extra]
    phones = form.getlist("member_phone")[:max_extra]
    for i, name in enumerate(names):
        name = clean(name, 100)
        email = clean(emails[i] if i < len(emails) else "", 120).lower()
        phone = clean(phones[i] if i < len(phones) else "", 15)
        if not name:
            continue
        if email and not valid_email(email):
            errors.append(f"Team member {name}: invalid e-mail.")
        if phone and not valid_phone(phone):
            errors.append(f"Team member {name}: phone must be 10 digits.")
        members.append({"name": name, "email": email, "phone": phone})
    return members, errors


@bp.route("/registrations", endpoint="registrations")
@roles_required("PARTICIPANT")
def registrations_page():
    return render_template("participant/registrations.html", regs=registrations.mine(g.user["user_id"]))


@bp.route("/registrations/<int:reg_id>")
@roles_required("PARTICIPANT")
def registration(reg_id):
    r = _mine(reg_id)
    payment = registrations.open_payment(reg_id)
    upi = None
    if payment and payment["method"] == "UPI_QR" and payment["status"] == "PENDING":
        upi_id = settings.get("upi_id")
        if upi_id:
            upi = {"uri": qr.upi_uri(upi_id, settings.get("upi_payee_name") or settings.get("symposium_name"),
                                     payment["amount"], f"REG{reg_id:05d} {r['ticket_code'][:6]}"),
                   "upi_id": upi_id}
    feedback = db.get().one("SELECT rating, comments FROM feedback WHERE reg_id = %s", (reg_id,))
    return render_template("participant/registration.html", r=r, payment=payment, upi=upi,
                           team=registrations.team(reg_id), methods=registrations.enabled_methods(),
                           feedback=feedback, fee=_gateway_fee(),
                           cert_available=r["status"] == "CONFIRMED" and r["attended"])


@bp.route("/registrations/<int:reg_id>/ticket.png")
@roles_required("PARTICIPANT")
def ticket_qr(reg_id):
    r = _mine(reg_id)
    if r["status"] != "CONFIRMED":
        abort(404)
    return Response(qr.png(qr.ticket_payload(r["ticket_code"])), mimetype="image/png",
                    headers={"Cache-Control": "private, no-store"})


@bp.route("/registrations/<int:reg_id>/upi.png")
@roles_required("PARTICIPANT")
def upi_qr(reg_id):
    r = _mine(reg_id)
    p = registrations.open_payment(reg_id)
    upi_id = settings.get("upi_id")
    if not p or p["method"] != "UPI_QR" or not upi_id:
        abort(404)
    uri = qr.upi_uri(upi_id, settings.get("upi_payee_name") or settings.get("symposium_name"), p["amount"],
                     f"REG{reg_id:05d} {r['ticket_code'][:6]}")
    return Response(qr.png(uri), mimetype="image/png", headers={"Cache-Control": "private, no-store"})


@bp.route("/registrations/<int:reg_id>/receipt.pdf")
@roles_required("PARTICIPANT")
def receipt(reg_id):
    r = _mine(reg_id)
    data = pdf.receipt(r, settings.all_settings(), registrations.team(reg_id))
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=REG{reg_id:05d}.pdf"})


@bp.route("/registrations/<int:reg_id>/certificate.pdf")
@roles_required("PARTICIPANT")
def certificate(reg_id):
    r = _mine(reg_id)
    if r["status"] != "CONFIRMED" or not r["attended"]:
        flash("Certificates are available after your attendance is recorded at the event.", "info")
        return redirect(url_for("participant.registration", reg_id=reg_id))
    if not r["results_published"]:
        r = dict(r, result_position=None)
    code = results.certificate_code(reg_id)
    url = current_app.config["BASE_URL"] + url_for("public.verify_certificate", code=code)
    data = pdf.certificate(r, settings.all_settings(), code, url)
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=Certificate-{reg_id}.pdf"})


@bp.route("/registrations/<int:reg_id>/feedback", methods=["POST"])
@roles_required("PARTICIPANT")
def feedback(reg_id):
    r = _mine(reg_id)
    rating = request.form.get("rating", type=int)
    if not r["attended"] or rating not in (1, 2, 3, 4, 5):
        flash("Choose a rating from 1 to 5.", "error")
    else:
        db.get().run("INSERT INTO feedback (reg_id, rating, comments) VALUES (%s, %s, %s) "
                     "ON DUPLICATE KEY UPDATE rating = VALUES(rating), comments = VALUES(comments)",
                     (reg_id, rating, clean(request.form.get("comments"), 500) or None))
        flash("Thanks for your feedback!", "success")
    return redirect(url_for("participant.registration", reg_id=reg_id))


@bp.route("/profile", methods=["GET", "POST"])
@roles_required("PARTICIPANT")
def profile():
    if request.method == "POST":
        f = request.form
        name, phone, college = clean(f.get("full_name"), 100), clean(f.get("phone"), 15), clean(f.get("college"), 150)
        dept, year = f.get("dept_id", type=int), f.get("year", type=int)
        gender = f.get("gender") if f.get("gender") in ("Male", "Female", "Other") else None
        if len(name) < 3 or not valid_phone(phone) or len(college) < 3 or not dept or year not in range(1, 6):
            flash("Please fill every field correctly (phone must be 10 digits).", "error")
        else:
            users.update_profile(g.user["user_id"], name, phone, college, dept, year, gender)
            flash("Profile updated.", "success")
            return redirect(url_for("participant.profile"))
    return render_template("participant/profile.html", p=users.profile(g.user["user_id"]),
                           colleges=users.colleges(), departments=users.departments())
