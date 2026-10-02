"""Background jobs: release expired seat holds, send queued e-mail, scheduled backups."""
import logging
import threading
import time

from webapp import db

log = logging.getLogger(__name__)
_started = False


def run_once(app) -> dict:
    """One pass of every periodic task (also used by tests)."""
    from webapp.services import backups, mailer
    out = {}
    with app.app_context():
        try:
            res = db.get().call("sp_expire_holds", (0,))
            out["expired"] = res[0]
        except db.DatabaseError as exc:
            log.warning("expire holds failed: %s", exc)
        try:
            out["mailed"] = mailer.send_pending(app.config["CFG"])
        except Exception as exc:          # noqa: BLE001 - never kill the worker
            log.exception("mail worker failed: %s", exc)
        try:
            out["backup"] = backups.maybe_scheduled(app.config["CFG"])
        except Exception as exc:          # noqa: BLE001
            log.exception("scheduled backup failed: %s", exc)
    return out


def start(app) -> None:
    global _started
    if _started:
        return
    _started = True
    from webapp.services import mailer

    def loop():
        while True:
            run_once(app)
            mailer._event.wait(60)        # wake early when new mail is queued
            mailer._event.clear()
            time.sleep(1)

    threading.Thread(target=loop, name="symposium-jobs", daemon=True).start()
    log.info("Background jobs started")
