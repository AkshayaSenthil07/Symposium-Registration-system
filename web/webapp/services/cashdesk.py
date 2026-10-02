"""Cashier tools: verify UPI references, record cash, bank-statement reconciliation, cashier report."""
import csv
import datetime as dt
import decimal
import io
import re

from webapp import db
from webapp.services import audit, notify

D = decimal.Decimal
UTR_IN_TEXT = re.compile(r"(?<![0-9])([0-9]{12})(?![0-9])")


def queue(status: str = "SUBMITTED") -> list[dict]:
    return db.get().all(
        "SELECT p.payment_id, p.reg_id, p.amount, p.method, p.status, p.utr, p.created_at, p.note, r.hold_expires_at, "
        "u.full_name, u.phone, u.email, e.event_name, r.ticket_code FROM payment p "
        "JOIN registration r ON r.reg_id = p.reg_id JOIN app_user u ON u.user_id = r.user_id "
        "JOIN event e ON e.event_id = r.event_id WHERE p.status = %s AND r.status = 'PENDING' "
        "ORDER BY p.created_at", (status,))


def verify(payment_id: int, actor_id: int, note: str = "Verified by cashier") -> int:
    with db.get().transaction() as cur:
        cur.execute("SELECT p.*, r.status AS reg_status FROM payment p JOIN registration r ON r.reg_id = p.reg_id "
                    "WHERE p.payment_id = %s FOR UPDATE", (payment_id,))
        p = cur.fetchone()
        if not p or p["status"] not in ("PENDING", "SUBMITTED"):
            raise db.DatabaseError("This payment is not waiting for verification.")
        if p["reg_status"] != "PENDING":
            raise db.DatabaseError("The registration is no longer pending (it may have expired or been cancelled).")
        cur.execute("UPDATE payment SET status = 'SUCCESS', paid_at = NOW(), collected_by = %s, note = %s "
                    "WHERE payment_id = %s", (actor_id, note, payment_id))
        audit.log(actor_id, "PAYMENT_VERIFIED", f"Payment #{payment_id} reg #{p['reg_id']} Rs.{p['amount']}", cur=cur)
    notify.payment_confirmed(p["reg_id"])
    return p["reg_id"]


def reject(payment_id: int, actor_id: int, reason: str) -> None:
    with db.get().transaction() as cur:
        cur.execute("SELECT reg_id, status, utr FROM payment WHERE payment_id = %s FOR UPDATE", (payment_id,))
        p = cur.fetchone()
        if not p or p["status"] != "SUBMITTED":
            raise db.DatabaseError("Only submitted UPI references can be rejected.")
        cur.execute("UPDATE payment SET status = 'PENDING', utr = NULL, note = %s WHERE payment_id = %s",
                    (f"Rejected: {reason}"[:255], payment_id))
        cur.execute("UPDATE registration SET hold_expires_at = NOW() + INTERVAL 1 DAY WHERE reg_id = %s", (p["reg_id"],))
        audit.log(actor_id, "PAYMENT_REJECTED", f"Payment #{payment_id} UTR {p['utr']}: {reason}", cur=cur)
    notify.payment_rejected(p["reg_id"], reason)


def record_cash(reg_id: int, actor_id: int) -> None:
    """Cash handed over at the desk for an existing pending registration."""
    with db.get().transaction() as cur:
        cur.execute("SELECT p.payment_id FROM payment p JOIN registration r ON r.reg_id = p.reg_id "
                    "WHERE p.reg_id = %s AND r.status = 'PENDING' AND p.status IN ('PENDING','SUBMITTED') "
                    "ORDER BY p.payment_id DESC LIMIT 1 FOR UPDATE", (reg_id,))
        p = cur.fetchone()
        if not p:
            raise db.DatabaseError("No pending payment for this registration.")
        cur.execute("UPDATE payment SET method = 'CASH', status = 'SUCCESS', utr = NULL, paid_at = NOW(), "
                    "collected_by = %s, note = 'Cash collected at desk' WHERE payment_id = %s", (actor_id, p["payment_id"]))
        audit.log(actor_id, "CASH_COLLECTED", f"Reg #{reg_id}", cur=cur)
    notify.payment_confirmed(reg_id)


# ------------------------------------------------------------------ bank statement
def _find(header: list[str], *words) -> int | None:
    for i, h in enumerate(header):
        name = h.strip().lower()
        if any(w in name for w in words):
            return i
    return None


def _amount(text: str) -> D | None:
    t = (text or "").replace(",", "").replace("₹", "").replace("INR", "").strip()
    if not t or t in ("-", "0", "0.00"):
        return None
    try:
        v = D(t)
    except decimal.InvalidOperation:
        return None
    return v if v > 0 else None


def _date(text: str):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%d-%m-%y"):
        try:
            return dt.datetime.strptime(text.strip()[:11], fmt).date()
        except ValueError:
            continue
    return None


def parse_statement(raw: bytes) -> tuple[list[dict], list[str]]:
    """Reads a bank statement CSV. Finds the header row automatically (banks put a few lines above it)."""
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    notes = []
    header_i = None
    for i, row in enumerate(rows[:40]):
        joined = " ".join(c.lower() for c in row)
        if ("credit" in joined or "deposit" in joined or "amount" in joined) and \
           ("narration" in joined or "description" in joined or "particular" in joined or "remark" in joined
                or "ref" in joined or "utr" in joined):
            header_i = i
            break
    if header_i is None:
        return [], ["Could not find the header row. The CSV needs columns like Date, Narration/Description, "
                    "Reference/UTR and Credit/Deposit amount."]
    header = rows[header_i]
    c_date = _find(header, "date")
    c_text = _find(header, "narration", "description", "particular", "remark", "details")
    c_ref = _find(header, "utr", "ref", "chq", "cheque")
    c_credit = _find(header, "credit", "deposit", "cr amount")
    if c_credit is None:
        c_credit = _find(header, "amount")
    out = []
    for row in rows[header_i + 1:]:
        if not row or c_credit is None or c_credit >= len(row):
            continue
        amt = _amount(row[c_credit])
        if amt is None:
            continue
        narration = row[c_text] if c_text is not None and c_text < len(row) else ""
        ref = row[c_ref].strip() if c_ref is not None and c_ref < len(row) else ""
        utr = ref if re.fullmatch(r"[0-9]{12}", ref) else None
        if not utr:
            m = UTR_IN_TEXT.search(narration + " " + ref)
            utr = m.group(1) if m else None
        if not utr:
            continue
        out.append({"utr": utr, "amount": amt, "date": _date(row[c_date]) if c_date is not None and c_date < len(row) else None,
                    "narration": narration[:255]})
    if not out:
        notes.append("No UPI credits with a 12-digit reference were found in the file.")
    return out, notes


def reconcile(raw: bytes, actor_id: int) -> dict:
    lines, notes = parse_statement(raw)
    summary = {"lines": len(lines), "new": 0, "matched": [], "amount_mismatch": [], "unmatched": 0, "notes": notes}
    with db.get().transaction() as cur:
        for ln in lines:
            cur.execute("INSERT IGNORE INTO bank_txn (utr, amount, txn_date, narration, imported_by) "
                        "VALUES (%s, %s, %s, %s, %s)", (ln["utr"], ln["amount"], ln["date"], ln["narration"], actor_id))
            summary["new"] += cur.rowcount
        cur.execute("SELECT b.txn_id, b.utr, b.amount, p.payment_id, p.amount AS due, p.reg_id FROM bank_txn b "
                    "JOIN payment p ON p.utr = b.utr JOIN registration r ON r.reg_id = p.reg_id "
                    "WHERE b.matched_payment_id IS NULL AND p.status = 'SUBMITTED' AND r.status = 'PENDING' "
                    "FOR UPDATE")
        for m in cur.fetchall():
            if D(m["amount"]) >= D(m["due"]):
                cur.execute("UPDATE bank_txn SET matched_payment_id = %s WHERE txn_id = %s", (m["payment_id"], m["txn_id"]))
                cur.execute("UPDATE payment SET status = 'SUCCESS', paid_at = NOW(), collected_by = %s, "
                            "note = 'Matched with bank statement' WHERE payment_id = %s", (actor_id, m["payment_id"]))
                summary["matched"].append(m["reg_id"])
            else:
                summary["amount_mismatch"].append({"reg_id": m["reg_id"], "utr": m["utr"], "paid": m["amount"],
                                                   "due": m["due"]})
        cur.execute("SELECT COUNT(*) AS n FROM bank_txn WHERE matched_payment_id IS NULL")
        summary["unmatched"] = cur.fetchone()["n"]
        audit.log(actor_id, "BANK_RECONCILED", f"{len(lines)} lines, {len(summary['matched'])} matched", cur=cur)
    for reg_id in summary["matched"]:
        notify.payment_confirmed(reg_id)
    return summary


def unmatched_bank_lines() -> list[dict]:
    return db.get().all("SELECT * FROM bank_txn WHERE matched_payment_id IS NULL ORDER BY txn_date DESC, txn_id DESC "
                        "LIMIT 200")


def cashier_report(day: dt.date | None) -> list[dict]:
    sql = ("SELECT IFNULL(u.full_name, 'Online / automatic') AS cashier, p.method, COUNT(*) AS n, SUM(p.amount) AS total "
           "FROM payment p LEFT JOIN app_user u ON u.user_id = p.collected_by "
           "WHERE p.status = 'SUCCESS' AND p.amount > 0")
    params: tuple = ()
    if day:
        sql += " AND DATE(p.paid_at) = %s"
        params = (day,)
    sql += " GROUP BY cashier, p.method ORDER BY cashier, p.method"
    return db.get().all(sql, params)
