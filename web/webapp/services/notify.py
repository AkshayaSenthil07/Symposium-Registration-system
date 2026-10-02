"""All participant e-mails in one place (rendered with templates/email/notice.*)."""
import logging

from flask import current_app, url_for

from webapp import db
from webapp.services import mailer, settings
from webapp.util import fmt_date, fmt_time, money

log = logging.getLogger(__name__)


def _send(to, subject, heading, lines, button=None, url=None):
    try:
        mailer.queue(to, f"{subject} - {settings.get('symposium_name')}", "notice",
                     heading=heading, lines=lines, button=button, url=url)
    except db.DatabaseError as exc:          # never block the main action because of e-mail
        log.error("Could not queue e-mail to %s: %s", to, exc)


def _abs(endpoint, **kw):
    return current_app.config["BASE_URL"] + url_for(endpoint, **kw)


def _reg(reg_id):
    return db.get().one("SELECT * FROM v_registration_details WHERE reg_id = %s", (reg_id,))


def _slot(r):
    return f"{fmt_date(r['event_date'])}, {fmt_time(r['start_time'])} - {fmt_time(r['end_time'])} · {r['venue_name'] or 'Online'}"


def registration_received(reg_id):
    r = _reg(reg_id)
    if not r:
        return
    link = _abs("participant.registration", reg_id=reg_id)
    if r["status"] == "CONFIRMED":
        _send(r["email"], f"You're registered: {r['event_name']}", f"See you at {r['event_name']}!",
              [f"Hi {r['full_name'].split()[0]}, your registration is confirmed.", _slot(r),
               f"Ticket code: {r['ticket_code']}. Show the QR code on your ticket at the venue."],
              "View my ticket", link)
    elif r["status"] == "WAITLISTED":
        _send(r["email"], f"On the waitlist: {r['event_name']}", "You're on the waitlist",
              [f"Hi {r['full_name'].split()[0]}, {r['event_name']} is full right now.",
               "We will e-mail you as soon as a seat opens up. You will then have a limited time to pay."],
              "View registration", link)
    else:
        _send(r["email"], f"Complete your payment: {r['event_name']}", "Your seat is on hold",
              [f"Hi {r['full_name'].split()[0]}, we are holding a seat for you in {r['event_name']}.",
               f"Amount due: {money(r['amount'])}. Please complete the payment before the hold expires, "
               "otherwise the seat is released to others."], "Pay now", link)


def payment_confirmed(reg_id):
    r = _reg(reg_id)
    if r and r["status"] == "CONFIRMED":
        _send(r["email"], f"Payment received: {r['event_name']}", "Payment received - you're in!",
              [f"Hi {r['full_name'].split()[0]}, we received {money(r['amount'])} for {r['event_name']}.",
               _slot(r), f"Ticket code: {r['ticket_code']}. Your receipt can be downloaded from your dashboard."],
              "View my ticket", _abs("participant.registration", reg_id=reg_id))


def payment_rejected(reg_id, reason):
    r = _reg(reg_id)
    if r:
        _send(r["email"], f"Payment not verified: {r['event_name']}", "We could not verify your payment",
              [f"Hi {r['full_name'].split()[0]}, the UPI reference you submitted for {r['event_name']} "
               f"could not be verified: {reason}.",
               "Please check the reference number in your UPI app and submit it again, or contact the organisers."],
              "Open registration", _abs("participant.registration", reg_id=reg_id))


def waitlist_promoted(reg_id):
    r = _reg(reg_id)
    if not r:
        return
    lines = [f"Good news {r['full_name'].split()[0]} - a seat opened up in {r['event_name']}.", _slot(r)]
    if r["status"] == "PENDING":
        lines.append(f"Please pay {money(r['fee_amount'])} soon - the seat is held for a limited time.")
    _send(r["email"], f"A seat is available: {r['event_name']}", "You're off the waitlist!", lines,
          "Open registration", _abs("participant.registration", reg_id=reg_id))


def cancelled(reg_id, reason):
    r = _reg(reg_id)
    if r:
        lines = [f"Hi {r['full_name'].split()[0]}, your registration for {r['event_name']} was cancelled "
                 f"by the organisers." + (f" Reason: {reason}." if reason else "")]
        if r["payment_status"] == "REFUNDED":
            lines.append(f"Your payment of {money(r['amount'])} will be refunded as per the refund policy.")
        _send(r["email"], f"Registration cancelled: {r['event_name']}", "Registration cancelled", lines)


def event_changed(event_id, change):
    e = db.get().one("SELECT event_name FROM event WHERE event_id = %s", (event_id,))
    rows = db.get().all("SELECT u.email, u.full_name FROM registration r JOIN app_user u ON u.user_id = r.user_id "
                        "WHERE r.event_id = %s AND r.status IN ('PENDING','CONFIRMED','WAITLISTED')", (event_id,))
    for row in rows:
        _send(row["email"], f"Update: {e['event_name']}", f"{e['event_name']} has been updated",
              [f"Hi {row['full_name'].split()[0]}, there is an important update for an event you registered for:",
               change], "View event", _abs("public.event_detail", event_id=event_id))
    return len(rows)


def certificate_ready(reg_id):
    r = _reg(reg_id)
    if r:
        _send(r["email"], f"Your certificate: {r['event_name']}", "Your certificate is ready",
              [f"Hi {r['full_name'].split()[0]}, thank you for taking part in {r['event_name']}.",
               "You can download your certificate from your dashboard."],
              "Download certificate", _abs("participant.registration", reg_id=reg_id))
