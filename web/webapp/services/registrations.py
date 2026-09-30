"""Registration rules, pricing (early bird + coupons), waitlist, UPI reference submission.

register() runs as ONE transaction and locks the event row (SELECT ... FOR UPDATE) so two people
can never take the last seat at the same time. The capacity trigger double-checks inside MySQL.
"""
import datetime as dt
import decimal

import mysql.connector

from webapp import db
from webapp.security import ticket_code, valid_utr
from webapp.services import audit, settings
from webapp.util import now

D = decimal.Decimal
ONLINE_METHODS = ("UPI_QR", "GATEWAY", "CASH")


class RegistrationError(Exception):
    pass


# ------------------------------------------------------------------ pricing
def _coupon(cur, code: str, event_id: int, lock=False) -> dict:
    cur.execute("SELECT * FROM coupon WHERE code = %s" + (" FOR UPDATE" if lock else ""),
                (code.strip().upper(),))
    c = cur.fetchone()
    if not c or not c["is_active"]:
        raise RegistrationError("This coupon code is not valid.")
    if c["event_id"] and c["event_id"] != event_id:
        raise RegistrationError("This coupon is not valid for this event.")
    if c["valid_until"] and c["valid_until"] < now():
        raise RegistrationError("This coupon has expired.")
    if c["max_uses"] is not None and c["used_count"] >= c["max_uses"]:
        raise RegistrationError("This coupon has been fully used.")
    return c


def _discount(price: D, coupon: dict | None) -> D:
    if not coupon or price <= 0:
        return D(0)
    if coupon["discount_type"] == "PERCENT":
        off = (price * D(coupon["discount_value"]) / 100).quantize(D("0.01"))
    else:
        off = D(coupon["discount_value"])
    return min(price, off)


def quote(event_id: int, coupon_code: str = "") -> dict:
    """Price breakdown shown before registering (raises RegistrationError for a bad coupon)."""
    with db.get().transaction() as cur:
        cur.execute("SELECT fn_event_price(%s) AS price, registration_fee FROM event WHERE event_id = %s",
                    (event_id, event_id))
        row = cur.fetchone()
        price = D(row["price"])
        coupon = _coupon(cur, coupon_code, event_id) if coupon_code.strip() else None
    off = _discount(price, coupon)
    return {"base": D(row["registration_fee"]), "price": price, "discount": off, "total": price - off,
            "coupon": coupon}


# ------------------------------------------------------------------ registering
def register(user_id: int, event_id: int, team_name: str = "", members: list[dict] | None = None,
             coupon_code: str = "", method: str = "UPI_QR", source: str = "ONLINE",
             cash_collected_by: int | None = None, actor_id: int | None = None) -> dict:
    """Returns {"reg_id", "status", "total"}. Raises RegistrationError with a friendly message."""
    members = members or []
    t = now()
    try:
        with db.get().transaction() as cur:
            cur.execute("SELECT * FROM event WHERE event_id = %s FOR UPDATE", (event_id,))
            e = cur.fetchone()
            if not e or (not e["is_published"] and source == "ONLINE"):
                raise RegistrationError("Event not found.")
            if e["status"] != "OPEN":
                raise RegistrationError("Registrations are closed for this event.")
            start = dt.datetime.combine(e["event_date"], dt.time()) + e["start_time"]
            if start < t:
                raise RegistrationError("This event has already started.")
            if source == "ONLINE":
                if not settings.flag("registrations_open"):
                    raise RegistrationError("Online registrations are closed. Please visit the registration desk.")
                if e["registration_deadline"] and e["registration_deadline"] < t:
                    raise RegistrationError("The registration deadline for this event has passed.")

            cur.execute("SELECT u.role, u.is_active, u.email_verified, pp.user_id AS has_profile FROM app_user u "
                        "LEFT JOIN participant_profile pp ON pp.user_id = u.user_id WHERE u.user_id = %s", (user_id,))
            u = cur.fetchone()
            if not u or u["role"] != "PARTICIPANT" or not u["has_profile"] or not u["is_active"]:
                raise RegistrationError("Only active participant accounts can register.")
            if source == "ONLINE" and not u["email_verified"]:
                raise RegistrationError("Please verify your e-mail address before registering.")

            # team size: the participant + additional members
            size = 1 + len(members)
            if size < e["team_min"] or size > e["team_max"]:
                if e["team_max"] == 1:
                    raise RegistrationError("This is an individual event.")
                raise RegistrationError(f"Team size must be between {e['team_min']} and {e['team_max']} "
                                        f"(including you). You entered {size}.")
            if e["team_max"] > 1 and not (team_name or "").strip():
                raise RegistrationError("Please enter a team name.")

            cur.execute("SELECT reg_id, status FROM registration WHERE user_id = %s AND event_id = %s FOR UPDATE",
                        (user_id, event_id))
            existing = cur.fetchone()
            if existing and existing["status"] != "CANCELLED":
                raise RegistrationError("You are already registered for this event.")

            limit = settings.number("max_events_per_participant")
            if limit:
                cur.execute("SELECT COUNT(*) AS n FROM registration WHERE user_id = %s "
                            "AND status IN ('PENDING','CONFIRMED','WAITLISTED')", (user_id,))
                if cur.fetchone()["n"] >= limit:
                    raise RegistrationError(f"You can register for at most {limit} events.")

            cur.execute("SELECT e2.event_name FROM registration r JOIN event e2 ON e2.event_id = r.event_id "
                        "WHERE r.user_id = %s AND r.status IN ('PENDING','CONFIRMED','WAITLISTED') "
                        "AND e2.event_id <> %s AND e2.event_date = %s AND e2.start_time < %s AND e2.end_time > %s "
                        "LIMIT 1", (user_id, event_id, e["event_date"], e["end_time"], e["start_time"]))
            clash = cur.fetchone()
            if clash:
                raise RegistrationError(f"Time clash: you are already registered for \"{clash['event_name']}\" "
                                        "at the same time.")

            cur.execute("SELECT fn_event_price(%s) AS price, fn_seats_left(%s) AS seats", (event_id, event_id))
            p = cur.fetchone()
            price = D(p["price"])
            coupon = _coupon(cur, coupon_code, event_id, lock=True) if coupon_code.strip() else None
            total = price - _discount(price, coupon)
            waitlisted = p["seats"] <= 0
            if total == 0:
                status = "WAITLISTED" if waitlisted else "PENDING"
            else:
                status = "WAITLISTED" if waitlisted else "PENDING"
            if method not in ONLINE_METHODS or not _method_enabled(method, source):
                raise RegistrationError("Please choose an available payment method.")
            hold_minutes = settings.number("desk_hold_minutes" if method == "CASH" else "online_hold_minutes", 60)
            hold = None if (waitlisted or total == 0 or cash_collected_by) else t + dt.timedelta(minutes=hold_minutes)

            code = ticket_code()
            if existing:                                  # re-registering after an admin cancellation
                reg_id = existing["reg_id"]
                cur.execute("UPDATE registration SET status = %s, team_name = %s, fee_amount = %s, coupon_id = %s, "
                            "ticket_code = %s, hold_expires_at = %s, attended = FALSE, checked_in_at = NULL, "
                            "registered_at = NOW(), source = %s WHERE reg_id = %s",
                            (status, (team_name or "").strip() or None, total, coupon and coupon["coupon_id"],
                             code, hold, source, reg_id))
                cur.execute("DELETE FROM team_member WHERE reg_id = %s", (reg_id,))
                if coupon:
                    cur.execute("UPDATE coupon SET used_count = used_count + 1 WHERE coupon_id = %s",
                                (coupon["coupon_id"],))
            else:
                cur.execute("INSERT INTO registration (user_id, event_id, team_name, status, fee_amount, coupon_id, "
                            "ticket_code, hold_expires_at, source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (user_id, event_id, (team_name or "").strip() or None, status, total,
                             coupon and coupon["coupon_id"], code, hold, source))
                reg_id = cur.lastrowid
            for m in members:
                cur.execute("INSERT INTO team_member (reg_id, member_name, member_email, member_phone) "
                            "VALUES (%s, %s, %s, %s)", (reg_id, m["name"], m.get("email") or None,
                                                        m.get("phone") or None))
            if not waitlisted:
                _create_payment(cur, reg_id, total, method, cash_collected_by)
            audit.log(actor_id or user_id, "REGISTER",
                      f"Reg #{reg_id} event #{event_id} {status} {method} Rs.{total} ({source})", cur=cur)
            cur.execute("SELECT status FROM registration WHERE reg_id = %s", (reg_id,))
            final = cur.fetchone()["status"]
    except db.DatabaseError as exc:
        raise RegistrationError(str(exc)) from exc
    return {"reg_id": reg_id, "status": final, "total": total}


def _method_enabled(method: str, source: str) -> bool:
    if source == "DESK":
        return method in ("CASH", "UPI_QR")
    return settings.flag({"UPI_QR": "pay_upi_qr", "GATEWAY": "pay_gateway", "CASH": "pay_cash"}[method])


def enabled_methods() -> list[str]:
    return [m for m in ONLINE_METHODS if _method_enabled(m, "ONLINE")]


def _create_payment(cur, reg_id, total, method, cash_collected_by=None):
    if total == 0:
        cur.execute("INSERT INTO payment (reg_id, amount, method, status, paid_at) "
                    "VALUES (%s, 0, 'FREE', 'SUCCESS', NOW())", (reg_id,))
    elif cash_collected_by:
        cur.execute("INSERT INTO payment (reg_id, amount, method, status, collected_by, paid_at, note) "
                    "VALUES (%s, %s, 'CASH', 'SUCCESS', %s, NOW(), 'Collected at the registration desk')",
                    (reg_id, total, cash_collected_by))
    else:
        cur.execute("INSERT INTO payment (reg_id, amount, method, status) VALUES (%s, %s, %s, 'PENDING')",
                    (reg_id, total, method))


# ------------------------------------------------------------------ participant actions
def get(reg_id: int) -> dict | None:
    return db.get().one("SELECT * FROM v_registration_details WHERE reg_id = %s", (reg_id,))


def for_user(reg_id: int, user_id: int) -> dict | None:
    r = get(reg_id)
    return r if r and r["user_id"] == user_id else None


def team(reg_id: int) -> list[dict]:
    return db.get().all("SELECT member_name, member_email, member_phone FROM team_member WHERE reg_id = %s "
                        "ORDER BY member_id", (reg_id,))


def mine(user_id: int) -> list[dict]:
    return db.get().all("SELECT * FROM v_registration_details WHERE user_id = %s "
                        "ORDER BY status = 'CANCELLED', event_date, start_time", (user_id,))


def open_payment(reg_id: int) -> dict | None:
    return db.get().one("SELECT * FROM payment WHERE reg_id = %s AND status IN ('PENDING','SUBMITTED') "
                        "ORDER BY payment_id DESC LIMIT 1", (reg_id,))


def change_method(reg_id: int, user_id: int, method: str) -> None:
    if method not in enabled_methods():
        raise RegistrationError("That payment method is not available.")
    hold = settings.number("desk_hold_minutes" if method == "CASH" else "online_hold_minutes", 60)
    with db.get().transaction() as cur:
        cur.execute("SELECT r.status, p.payment_id, p.status AS pstatus FROM registration r "
                    "JOIN payment p ON p.reg_id = r.reg_id WHERE r.reg_id = %s AND r.user_id = %s "
                    "AND p.status IN ('PENDING','SUBMITTED') ORDER BY p.payment_id DESC LIMIT 1 FOR UPDATE",
                    (reg_id, user_id))
        row = cur.fetchone()
        if not row or row["status"] != "PENDING":
            raise RegistrationError("This registration has no pending payment.")
        if row["pstatus"] == "SUBMITTED":
            raise RegistrationError("Your UPI reference is already being verified.")
        cur.execute("UPDATE payment SET method = %s, gateway_order_id = NULL WHERE payment_id = %s",
                    (method, row["payment_id"]))
        cur.execute("UPDATE registration SET hold_expires_at = GREATEST(IFNULL(hold_expires_at, NOW()), "
                    "NOW() + INTERVAL %s MINUTE) WHERE reg_id = %s", (hold, reg_id))


def submit_utr(reg_id: int, user_id: int | None, utr: str) -> None:
    utr = (utr or "").strip().upper()
    if not valid_utr(utr):
        raise RegistrationError("Enter the 12-digit UPI reference number (UTR) shown in your UPI app.")
    try:
        with db.get().transaction() as cur:
            cur.execute("SELECT p.payment_id FROM payment p JOIN registration r ON r.reg_id = p.reg_id "
                        "WHERE p.reg_id = %s AND (r.user_id = %s OR %s IS NULL) AND p.method = 'UPI_QR' "
                        "AND p.status = 'PENDING' AND r.status = 'PENDING' FOR UPDATE", (reg_id, user_id, user_id))
            row = cur.fetchone()
            if not row:
                raise RegistrationError("This registration is not waiting for a UPI payment.")
            cur.execute("UPDATE payment SET utr = %s, status = 'SUBMITTED' WHERE payment_id = %s",
                        (utr, row["payment_id"]))
            audit.log(user_id, "UTR_SUBMITTED", f"Reg #{reg_id} UTR {utr}", cur=cur)
            _auto_match(cur, row["payment_id"], utr)
    except db.DatabaseError as exc:
        raise RegistrationError(str(exc)) from exc


def _auto_match(cur, payment_id: int, utr: str) -> bool:
    """If the bank statement line is already imported, confirm immediately."""
    cur.execute("SELECT b.txn_id, b.amount, p.amount AS due FROM bank_txn b JOIN payment p ON p.payment_id = %s "
                "WHERE b.utr = %s AND b.matched_payment_id IS NULL", (payment_id, utr))
    b = cur.fetchone()
    if b and D(b["amount"]) >= D(b["due"]):
        cur.execute("UPDATE bank_txn SET matched_payment_id = %s WHERE txn_id = %s", (payment_id, b["txn_id"]))
        cur.execute("UPDATE payment SET status = 'SUCCESS', paid_at = NOW(), note = 'Matched with bank statement' "
                    "WHERE payment_id = %s", (payment_id,))
        return True
    return False


def promote_waitlist(event_id: int) -> int | None:
    hold = settings.number("online_hold_minutes", 60)
    try:
        res = db.get().call("sp_promote_waitlist", (event_id, hold, 0))
    except db.DatabaseError:
        return None
    reg_id = res[2]
    if reg_id:
        r = get(reg_id)
        if r and r["status"] == "CONFIRMED" and not r["payment_id"]:
            db.get().run("INSERT INTO payment (reg_id, amount, method, status, paid_at) "
                         "VALUES (%s, 0, 'FREE', 'SUCCESS', NOW())", (reg_id,))
        elif r and r["status"] == "PENDING" and not open_payment(reg_id):
            method = "UPI_QR" if "UPI_QR" in enabled_methods() else (enabled_methods() or ["CASH"])[0]
            db.get().run("INSERT INTO payment (reg_id, amount, method, status) VALUES (%s, %s, %s, 'PENDING')",
                         (reg_id, r["fee_amount"], method))
        from webapp.services import notify
        notify.waitlist_promoted(reg_id)
    return reg_id


def is_duplicate_error(exc: Exception) -> bool:
    return isinstance(exc.__cause__, mysql.connector.Error) and exc.__cause__.errno == 1062
