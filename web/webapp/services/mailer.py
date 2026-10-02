"""E-mail: every message goes to the email_outbox table first.

mail.mode = demo  -> messages stay in the outbox (Admin > Outbox shows them); nothing is sent.
mail.mode = smtp  -> a background worker sends queued mail through the configured SMTP server
                     and retries failures up to 5 times.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from flask import current_app, render_template

from webapp import db
from webapp.util import now

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def queue(to_email: str, subject: str, template: str, cur=None, **context) -> None:
    """Render templates/email/<template>.txt and .html and store the message."""
    text = render_template(f"email/{template}.txt", **context)
    html = render_template(f"email/{template}.html", **context)
    status = "QUEUED" if current_app.config["MAIL_MODE"] == "smtp" else "DEMO"
    sql = ("INSERT INTO email_outbox (to_email, subject, body_text, body_html, status) "
           "VALUES (%s, %s, %s, %s, %s)")
    params = (to_email, subject[:200], text, html, status)
    if cur is not None:
        cur.execute(sql, params)
    else:
        db.get().run(sql, params)
    if status == "QUEUED":
        wake()


_event = threading.Event()


def wake():
    _event.set()


def send_pending(cfg) -> int:
    """Sends queued mail. Returns how many were sent."""
    m = cfg["mail"]
    if m["mode"] != "smtp" or not m["smtp_host"]:
        return 0
    rows = db.get().all("SELECT * FROM email_outbox WHERE status = 'QUEUED' AND attempts < %s "
                        "ORDER BY mail_id LIMIT 20", (MAX_ATTEMPTS,))
    if not rows:
        return 0
    sent = 0
    try:
        server = smtplib.SMTP(m["smtp_host"], int(m["smtp_port"]), timeout=20)
        server.starttls(context=ssl.create_default_context())
        if m["smtp_user"]:
            server.login(m["smtp_user"], m["smtp_password"])
    except (OSError, smtplib.SMTPException) as exc:
        log.error("SMTP connection failed: %s", exc)
        for r in rows:
            db.get().run("UPDATE email_outbox SET attempts = attempts + 1, last_error = %s WHERE mail_id = %s",
                         (str(exc)[:255], r["mail_id"]))
        return 0
    try:
        for r in rows:
            msg = EmailMessage()
            msg["From"] = m["from_address"] or m["smtp_user"]
            msg["To"] = r["to_email"]
            msg["Subject"] = r["subject"]
            msg.set_content(r["body_text"])
            if r["body_html"]:
                msg.add_alternative(r["body_html"], subtype="html")
            try:
                server.send_message(msg)
                db.get().run("UPDATE email_outbox SET status = 'SENT', sent_at = %s, attempts = attempts + 1 "
                             "WHERE mail_id = %s", (now(), r["mail_id"]))
                sent += 1
            except smtplib.SMTPException as exc:
                db.get().run("UPDATE email_outbox SET attempts = attempts + 1, last_error = %s, "
                             "status = IF(attempts + 1 >= %s, 'FAILED', 'QUEUED') WHERE mail_id = %s",
                             (str(exc)[:255], MAX_ATTEMPTS, r["mail_id"]))
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass
    return sent


def test_connection(cfg) -> tuple[bool, str]:
    m = cfg["mail"]
    try:
        server = smtplib.SMTP(m["smtp_host"], int(m["smtp_port"]), timeout=15)
        server.starttls(context=ssl.create_default_context())
        if m["smtp_user"]:
            server.login(m["smtp_user"], m["smtp_password"])
        server.quit()
        return True, "Connected and logged in to the SMTP server."
    except (OSError, smtplib.SMTPException) as exc:
        return False, f"SMTP error: {exc}"
