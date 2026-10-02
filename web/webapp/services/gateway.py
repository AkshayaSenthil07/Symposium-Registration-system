"""Online payment gateway: Razorpay (test / live keys) or a built-in mock for demos.

Security rules followed:
  * the amount is always taken from our database, never from the browser;
  * a payment is marked successful only after the HMAC signature is verified AND (for Razorpay)
    the payment is fetched from Razorpay's API and found captured for the exact amount;
  * the webhook is verified with its own secret, and every update is idempotent.
"""
import logging
import secrets

import requests
from flask import current_app

from webapp import db
from webapp.security import sign, signature_ok
from webapp.services import audit, settings

log = logging.getLogger(__name__)
API = "https://api.razorpay.com/v1"


class GatewayError(Exception):
    pass


def mode() -> str:
    return current_app.config["CFG"]["payment"]["gateway_mode"]


def _keys():
    p = current_app.config["CFG"]["payment"]
    return p["razorpay_key_id"], p["razorpay_key_secret"], p["razorpay_webhook_secret"]


def mock_allowed() -> bool:
    """The simulated gateway must NEVER work on a live site (it would give free seats)."""
    return mode() == "mock" and settings.get("data_mode") == "demo"


def is_ready() -> bool:
    if mode() == "mock":
        return mock_allowed()
    key_id, secret, _ = _keys()
    return bool(key_id and secret)


def convenience_fee() -> int:
    return max(0, settings.number("gateway_convenience_fee"))


def start(payment: dict, reg: dict) -> dict:
    """Creates (or reuses) a gateway order for a pending payment. Returns checkout data."""
    if payment["method"] != "GATEWAY" or payment["status"] != "PENDING":
        raise GatewayError("This payment cannot be paid online.")
    amount_paise = int((payment["amount"] + convenience_fee()) * 100)
    order_id = payment["gateway_order_id"]
    if not order_id:
        receipt = f"REG{reg['reg_id']:06d}"
        if mode() == "mock":
            if not mock_allowed():
                raise GatewayError("Online payment is not configured yet. Please use UPI QR or pay at the desk.")
            order_id = "order_MOCK" + secrets.token_hex(7).upper()
        else:
            key_id, secret, _ = _keys()
            try:
                resp = requests.post(f"{API}/orders", auth=(key_id, secret), timeout=15, json={
                    "amount": amount_paise, "currency": "INR", "receipt": receipt,
                    "notes": {"reg_id": str(reg["reg_id"]), "event": reg["event_name"][:60]}})
            except requests.RequestException as exc:
                log.error("Razorpay order failed: %s", exc)
                raise GatewayError("Could not reach the payment gateway. Please try again or pay by UPI QR.") from exc
            if resp.status_code != 200:
                log.error("Razorpay order error %s: %s", resp.status_code, resp.text[:300])
                raise GatewayError("The payment gateway rejected the request. Please try UPI QR or pay at the desk.")
            order_id = resp.json()["id"]
        db.get().run("UPDATE payment SET gateway_order_id = %s WHERE payment_id = %s AND status = 'PENDING'",
                     (order_id, payment["payment_id"]))
    return {"order_id": order_id, "amount_paise": amount_paise, "key_id": _keys()[0], "mode": mode()}


def mock_signature(order_id: str, payment_id: str) -> str:
    return sign(f"{order_id}|{payment_id}", current_app.config["CFG"]["payment"]["mock_secret"])


def verify_and_capture(order_id: str, payment_id: str, signature: str) -> dict:
    """Called by the checkout callback. Returns the payment row after marking it SUCCESS."""
    row = db.get().one("SELECT * FROM payment WHERE gateway_order_id = %s", (order_id or "",))
    if not row:
        raise GatewayError("Unknown payment order.")
    if row["status"] == "SUCCESS":
        return row                                           # already confirmed (e.g. by the webhook)
    expected = int((row["amount"] + convenience_fee()) * 100)
    if mode() == "mock":
        if not mock_allowed():
            raise GatewayError("Online payment is not configured.")
        if not payment_id.startswith("pay_MOCK") or not signature_ok(f"{order_id}|{payment_id}", signature,
                                                                      current_app.config["CFG"]["payment"]["mock_secret"]):
            raise GatewayError("Payment verification failed.")
    else:
        key_id, secret, _ = _keys()
        if not signature_ok(f"{order_id}|{payment_id}", signature, secret):
            raise GatewayError("Payment verification failed (signature mismatch).")
        try:
            resp = requests.get(f"{API}/payments/{payment_id}", auth=(key_id, secret), timeout=15)
            info = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise GatewayError("Could not confirm the payment with the gateway. If money was debited, "
                               "it will be confirmed automatically within a few minutes.") from exc
        if info.get("order_id") != order_id or int(info.get("amount", -1)) != expected:
            raise GatewayError("Payment amount does not match. Please contact the organisers.")
        if info.get("status") == "authorized":
            requests.post(f"{API}/payments/{payment_id}/capture", auth=(key_id, secret), timeout=15,
                          json={"amount": expected, "currency": "INR"})
        elif info.get("status") != "captured":
            raise GatewayError("The payment was not completed.")
    return mark_paid(order_id, payment_id, source="checkout")


def mark_paid(order_id: str, payment_id: str, source: str) -> dict:
    with db.get().transaction() as cur:
        cur.execute("SELECT * FROM payment WHERE gateway_order_id = %s FOR UPDATE", (order_id,))
        row = cur.fetchone()
        if not row:
            raise GatewayError("Unknown payment order.")
        if row["status"] != "SUCCESS":
            cur.execute("SELECT r.status, r.event_id, fn_seats_left(r.event_id) AS seats FROM registration r "
                        "WHERE r.reg_id = %s FOR UPDATE", (row["reg_id"],))
            reg = cur.fetchone()
            note = f"Paid online ({source})"
            if reg["status"] == "CANCELLED":
                # the seat hold expired while the student was paying - give the seat back if one is free
                if reg["seats"] > 0:
                    cur.execute("UPDATE registration SET status = 'PENDING' WHERE reg_id = %s", (row["reg_id"],))
                else:
                    note = "PAID AFTER SEAT WAS RELEASED - refund or add a seat"
            cur.execute("UPDATE payment SET status = 'SUCCESS', gateway_payment_id = %s, paid_at = NOW(), "
                        "note = %s WHERE payment_id = %s", (payment_id, note, row["payment_id"]))
            audit.log(None, "GATEWAY_PAID", f"Reg #{row['reg_id']} {payment_id} via {source}", cur=cur)
        cur.execute("SELECT * FROM payment WHERE payment_id = %s", (row["payment_id"],))
        return cur.fetchone()


def handle_webhook(raw_body: bytes, signature: str, payload: dict) -> str:
    _, _, webhook_secret = _keys()
    if not signature_ok(raw_body, signature, webhook_secret):
        raise GatewayError("bad signature")
    event = payload.get("event")
    if event in ("payment.captured", "order.paid"):
        ent = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id, pay_id = ent.get("order_id"), ent.get("id")
        row = db.get().one("SELECT amount FROM payment WHERE gateway_order_id = %s", (order_id or "",))
        if row and int(ent.get("amount", -1)) == int((row["amount"] + convenience_fee()) * 100):
            mark_paid(order_id, pay_id, source="webhook")
            return "marked"
    return "ignored"
