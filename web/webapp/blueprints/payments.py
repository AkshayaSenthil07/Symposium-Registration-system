"""Payment actions: UPI reference submission, method change, gateway checkout + callbacks."""
import json
import logging
import secrets

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from webapp.security import rate_limit, roles_required
from webapp.services import gateway, notify, registrations

log = logging.getLogger(__name__)
bp = Blueprint("payments", __name__, url_prefix="/pay")


def _own(reg_id):
    r = registrations.for_user(reg_id, g.user["user_id"])
    if not r:
        abort(404)
    return r


@bp.route("/<int:reg_id>/utr", methods=["POST"])
@roles_required("PARTICIPANT")
@rate_limit("utr", limit=10, window=900)
def submit_utr(reg_id):
    _own(reg_id)
    try:
        registrations.submit_utr(reg_id, g.user["user_id"], request.form.get("utr", ""))
    except registrations.RegistrationError as exc:
        flash(str(exc), "error")
    else:
        r = registrations.get(reg_id)
        if r["status"] == "CONFIRMED":
            notify.payment_confirmed(reg_id)
            flash("Payment matched with the bank statement - you're confirmed!", "success")
        else:
            flash("Thanks! Your payment reference was submitted. Your seat is held while the organisers verify "
                  "it with the bank statement (usually within a few hours). You'll get an e-mail once confirmed.",
                  "success")
    return redirect(url_for("participant.registration", reg_id=reg_id))


@bp.route("/<int:reg_id>/method", methods=["POST"])
@roles_required("PARTICIPANT")
def change_method(reg_id):
    _own(reg_id)
    try:
        registrations.change_method(reg_id, g.user["user_id"], request.form.get("method", ""))
        flash("Payment method changed.", "success")
    except registrations.RegistrationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("participant.registration", reg_id=reg_id))


@bp.route("/<int:reg_id>/online", methods=["POST"])
@roles_required("PARTICIPANT")
@rate_limit("gateway", limit=20, window=900)
def start_online(reg_id):
    r = _own(reg_id)
    payment = registrations.open_payment(reg_id)
    if not payment or payment["method"] != "GATEWAY" or r["status"] != "PENDING":
        flash("This registration is not waiting for an online payment.", "error")
        return redirect(url_for("participant.registration", reg_id=reg_id))
    if not gateway.is_ready():
        flash("Online payment is not configured yet. Please use UPI QR or pay at the desk.", "error")
        return redirect(url_for("participant.registration", reg_id=reg_id))
    try:
        order = gateway.start(payment, r)
    except gateway.GatewayError as exc:
        flash(str(exc), "error")
        return redirect(url_for("participant.registration", reg_id=reg_id))
    if order["mode"] == "mock":
        return redirect(url_for("payments.mock_checkout", order_id=order["order_id"]))
    g.relaxed_csp = True                        # Razorpay's checkout injects its own styles
    return render_template("participant/checkout.html", r=r, order=order)


@bp.route("/callback", methods=["POST"])
@roles_required("PARTICIPANT")
def callback():
    order_id = request.form.get("razorpay_order_id", "")
    payment_id = request.form.get("razorpay_payment_id", "")
    signature = request.form.get("razorpay_signature", "")
    try:
        row = gateway.verify_and_capture(order_id, payment_id, signature)
    except gateway.GatewayError as exc:
        log.warning("Gateway callback failed for %s: %s", order_id, exc)
        flash(str(exc), "error")
        return redirect(url_for("participant.registrations"))
    if not registrations.for_user(row["reg_id"], g.user["user_id"]):
        abort(404)
    notify.payment_confirmed(row["reg_id"])
    flash("Payment successful - you're confirmed! Your QR ticket is ready.", "success")
    return redirect(url_for("participant.registration", reg_id=row["reg_id"]))


# ------------------------------------------------------------------ built-in mock gateway (demo mode only)
@bp.route("/mock/<order_id>", methods=["GET", "POST"])
@roles_required("PARTICIPANT")
def mock_checkout(order_id):
    if not gateway.mock_allowed():
        abort(404)
    from webapp import db
    row = db.get().one("SELECT p.*, r.user_id FROM payment p JOIN registration r ON r.reg_id = p.reg_id "
                       "WHERE p.gateway_order_id = %s", (order_id,))
    if not row or row["user_id"] != g.user["user_id"]:
        abort(404)
    r = registrations.get(row["reg_id"])
    if request.method == "POST":
        if request.form.get("outcome") != "success":
            flash("Payment was cancelled. You can try again or choose another method.", "error")
            return redirect(url_for("participant.registration", reg_id=row["reg_id"]))
        pay_id = "pay_MOCK" + secrets.token_hex(7).upper()
        sig = gateway.mock_signature(order_id, pay_id)
        return render_template("participant/mock_return.html", order_id=order_id, pay_id=pay_id, sig=sig)
    total = row["amount"] + gateway.convenience_fee()
    return render_template("participant/mock_gateway.html", r=r, row=row, total=total, order_id=order_id)


# ------------------------------------------------------------------ Razorpay webhook (server to server)
@bp.route("/razorpay/webhook", methods=["POST"])
def razorpay_webhook():
    raw = request.get_data(cache=False)
    try:
        payload = json.loads(raw or b"{}")
        result = gateway.handle_webhook(raw, request.headers.get("X-Razorpay-Signature", ""), payload)
    except (gateway.GatewayError, ValueError) as exc:
        log.warning("Rejected webhook: %s", exc)
        return {"status": "rejected"}, 400
    return {"status": result}, 200
