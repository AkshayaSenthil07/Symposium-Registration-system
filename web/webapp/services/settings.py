"""Organiser-editable settings stored in the app_setting table (cached briefly)."""
import threading
import time

from webapp import db

DEFAULTS = {
    # branding / contact
    "symposium_name": "TECHNOVA 2026",
    "tagline": "National Level Technical Symposium",
    "host_institution": "Department of Computer Science and Engineering",
    "college_name": "Coimbatore Institute of Technology",
    "symposium_dates": "",
    "venue_address": "",
    "contact_email": "technova@example.edu",
    "contact_phone": "",
    "about_text": "A national level technical symposium with technical and non-technical events, "
                  "workshops and prizes. Register online, pay by UPI and get your QR ticket instantly.",
    "logo_path": "",
    # registration rules
    "registrations_open": "1",
    "signups_open": "1",
    "max_events_per_participant": "0",       # 0 = no limit
    "online_hold_minutes": "60",             # unpaid online registrations are released after this
    "desk_hold_minutes": "1440",             # 'pay at desk' holds
    # payments
    "pay_upi_qr": "1",
    "pay_gateway": "1",
    "pay_cash": "1",
    "upi_id": "",                            # e.g. collegename@okaxis - money goes here directly
    "upi_payee_name": "",
    "gateway_convenience_fee": "0",          # extra charged on gateway payments (0 = organisers absorb)
    # legal pages (shown in the footer; required by payment gateways)
    "refund_policy": "Registration fees are non-refundable, except when an event is cancelled by the "
                     "organisers. In that case the full fee is refunded to the original payment method "
                     "within 7 working days.",
    "privacy_note": "We collect only your name, e-mail, phone number, college, department and year of "
                    "study to manage your registration, send tickets and certificates. We never sell or "
                    "share your data. You can ask the organisers to delete your data after the event.",
    "terms_text": "By registering you agree to follow the rules of each event and the code of conduct of "
                  "the host institution. The organisers may change schedules; changes are announced on "
                  "this website and by e-mail.",
    # site state
    "data_mode": "live",                     # demo | live
    "sql_console_enabled": "1",
}

_cache: dict = {}
_cache_at = 0.0
_lock = threading.Lock()
TTL = 10


def all_settings() -> dict:
    global _cache, _cache_at
    with _lock:
        if time.monotonic() - _cache_at > TTL or not _cache:
            data = dict(DEFAULTS)
            for row in db.get().all("SELECT setting_key, setting_value FROM app_setting"):
                data[row["setting_key"]] = row["setting_value"]
            _cache, _cache_at = data, time.monotonic()
        return dict(_cache)


def get(key: str) -> str:
    return all_settings().get(key, DEFAULTS.get(key, ""))


def flag(key: str) -> bool:
    return get(key) in ("1", "true", "yes", "on")


def number(key: str, default: int = 0) -> int:
    try:
        return int(float(get(key)))
    except (TypeError, ValueError):
        return default


def save(values: dict) -> None:
    global _cache_at
    with db.get().transaction() as cur:
        for key, value in values.items():
            cur.execute("INSERT INTO app_setting (setting_key, setting_value) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)", (key, str(value)))
    with _lock:
        _cache_at = 0.0


def invalidate():
    global _cache_at
    with _lock:
        _cache_at = 0.0
