"""Payments: UPI reference + bank reconciliation, gateway signature checks, webhook, cash, check-in."""
import hashlib
import hmac
import json

import pytest

from webapp.services import cashdesk, gateway
from webapp.services import registrations as R


def _pending(make_user, make_event, method="UPI_QR", fee=150):
    u, e = make_user(), make_event(fee=fee)
    return u, R.register(u["user_id"], e, method=method)["reg_id"]


def test_utr_submit_then_bank_statement_match(ctx, make_user, make_event, make_user_admin=None, db=None):
    from webapp import db as dbm
    D = dbm.get()
    u, reg = _pending(make_user, make_event)
    with pytest.raises(R.RegistrationError):
        R.submit_utr(reg, u["user_id"], "12")                       # invalid
    R.submit_utr(reg, u["user_id"], "412345678901")
    assert D.value("SELECT status FROM payment WHERE reg_id = %s", (reg,)) == "SUBMITTED"
    staff = make_user("CASHIER")
    csv = ("Statement\n\nTxn Date,Description,Ref No.,Debit,Credit,Balance\n"
           "01/10/2026,UPI/412345678901/ASHA@okicici/fee,412345678901,,150.00,5150\n"
           "01/10/2026,UPI/499999999999/SOMEONE/fee,499999999999,,90.00,5240\n").encode()
    s = cashdesk.reconcile(csv, staff["user_id"])
    assert s["matched"] == [reg] and s["unmatched"] == 1
    assert D.value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "CONFIRMED"
    assert cashdesk.reconcile(csv, staff["user_id"])["new"] == 0      # re-upload is harmless


def test_underpayment_not_confirmed(ctx, make_user, make_event):
    from webapp import db as dbm
    u, reg = _pending(make_user, make_event, fee=200)
    R.submit_utr(reg, u["user_id"], "412345678999")
    csv = b"Date,Narration,Credit\n01/10/2026,UPI/412345678999/X/fee,20.00\n"
    s = cashdesk.reconcile(csv, make_user("CASHIER")["user_id"])
    assert s["amount_mismatch"] and not s["matched"]
    assert dbm.get().value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "PENDING"


def test_utr_cannot_be_reused(ctx, make_user, make_event):
    u1, r1 = _pending(make_user, make_event)
    u2, r2 = _pending(make_user, make_event)
    R.submit_utr(r1, u1["user_id"], "412345670000")
    with pytest.raises(R.RegistrationError, match="already been used"):
        R.submit_utr(r2, u2["user_id"], "412345670000")


def test_mock_gateway_signature(ctx, make_user, make_event):
    from webapp import db as dbm
    u, reg = _pending(make_user, make_event, method="GATEWAY")
    payment = R.open_payment(reg)
    order = gateway.start(payment, R.get(reg))
    with pytest.raises(gateway.GatewayError):
        gateway.verify_and_capture(order["order_id"], "pay_MOCKX", "0" * 64)
    sig = gateway.mock_signature(order["order_id"], "pay_MOCKABC")
    gateway.verify_and_capture(order["order_id"], "pay_MOCKABC", sig)
    assert dbm.get().value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "CONFIRMED"
    gateway.verify_and_capture(order["order_id"], "pay_MOCKABC", sig)        # idempotent


def test_webhook_requires_valid_signature_and_amount(app, ctx, make_user, make_event):
    from webapp import db as dbm
    cfg = app.config["CFG"]["payment"]
    cfg["razorpay_webhook_secret"] = "whsec_test"
    u, reg = _pending(make_user, make_event, method="GATEWAY", fee=100)
    dbm.get().run("UPDATE payment SET gateway_order_id = 'order_T1' WHERE reg_id = %s", (reg,))

    def body(amount):
        return json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_T1", "order_id": "order_T1", "amount": amount}}}}).encode()

    with pytest.raises(gateway.GatewayError):
        gateway.handle_webhook(body(10000), "bad", json.loads(body(10000)))
    wrong = body(100)                                                        # Rs 1 instead of Rs 100
    sig = hmac.new(b"whsec_test", wrong, hashlib.sha256).hexdigest()
    assert gateway.handle_webhook(wrong, sig, json.loads(wrong)) == "ignored"
    good = body(10000)
    sig = hmac.new(b"whsec_test", good, hashlib.sha256).hexdigest()
    assert gateway.handle_webhook(good, sig, json.loads(good)) == "marked"
    assert dbm.get().value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "CONFIRMED"


def test_webhook_endpoint_rejects_forgery(client):
    r = client.c.post("/pay/razorpay/webhook", data=b"{}", headers={"X-Razorpay-Signature": "x"},
                      content_type="application/json")
    assert r.status_code == 400


def test_cash_desk_and_checkin(app, make_user, make_event, db):
    from tests.conftest import Client
    cashier = make_user("CASHIER")
    with app.test_request_context():
        u, reg = _pending(make_user, make_event, method="CASH")
    c = Client(app).login(cashier["email"])
    c.post("/staff/payments", {"action": "cash", "reg_id": reg})
    assert db.value("SELECT status FROM registration WHERE reg_id = %s", (reg,)) == "CONFIRMED"
    code = db.value("SELECT ticket_code FROM registration WHERE reg_id = %s", (reg,))
    c.post("/staff/checkin", {"code": code, "confirm": "1"})
    assert db.value("SELECT attended FROM registration WHERE reg_id = %s", (reg,)) == 1


def test_statement_parser_handles_bank_layouts():
    rows, _ = cashdesk.parse_statement(
        b"Bank of X\nTran Date,Particulars,Chq/Ref Number,Withdrawal Amt,Deposit Amt\n"
        b"01-10-2026,UPI-ASHA-412345678901-fee,,,\"1,200.00\"\n")
    assert rows and rows[0]["utr"] == "412345678901" and rows[0]["amount"] == 1200
