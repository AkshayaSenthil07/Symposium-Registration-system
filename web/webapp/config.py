"""Server configuration from instance/config.ini (git-ignored; holds every secret).

Non-secret, organiser-editable settings (symposium name, UPI ID, feature
switches ...) live in the app_setting table instead - see services/settings.py.
"""
import configparser
import os
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
CONFIG_PATH = os.path.join(INSTANCE_DIR, "config.ini")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")
BACKUP_DIR = os.path.join(INSTANCE_DIR, "backups")
UPLOAD_DIR = os.path.join(INSTANCE_DIR, "uploads")
LOG_DIR = os.path.join(INSTANCE_DIR, "logs")

DEFAULTS = {
    "server": {
        "secret_key": "",                 # generated on first run
        "base_url": "http://127.0.0.1:5000",
        "https": "false",                 # true once served over HTTPS (secure cookies, HSTS)
        "behind_proxy": "false",          # true when Caddy / nginx sits in front
    },
    "mysql": {
        "host": "localhost",
        "port": "3306",
        "database": "symposium_live",
        "user": "symposium_app",
        "password": "",
        "readonly_user": "symposium_ro",
        "readonly_password": "",
    },
    "mail": {
        "mode": "demo",                   # demo = keep in outbox only; smtp = really send
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "from_address": "",
    },
    "payment": {
        "gateway_mode": "mock",           # mock | test | live
        "razorpay_key_id": "",
        "razorpay_key_secret": "",
        "razorpay_webhook_secret": "",
        "mock_secret": "",                # generated; signs mock-gateway callbacks
    },
    "backup": {
        "interval_minutes": "30",         # 0 = off
        "keep": "48",
    },
}

SECRET_FIELDS = {("server", "secret_key"), ("mysql", "password"), ("mysql", "readonly_password"),
                 ("mail", "smtp_password"), ("payment", "razorpay_key_secret"),
                 ("payment", "razorpay_webhook_secret"), ("payment", "mock_secret")}


def load() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding="utf-8")
    changed = False
    if not cfg["server"]["secret_key"]:
        cfg["server"]["secret_key"] = secrets.token_hex(32)
        changed = True
    if not cfg["payment"]["mock_secret"]:
        cfg["payment"]["mock_secret"] = secrets.token_hex(16)
        changed = True
    if changed and os.path.exists(CONFIG_PATH):
        save(cfg)
    return cfg


def save(cfg: configparser.ConfigParser) -> None:
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("; Server secrets for the symposium website. NEVER commit or share this file.\n")
        cfg.write(fh)
    os.replace(tmp, CONFIG_PATH)


def mysql_params(cfg, readonly: bool = False) -> dict:
    s = cfg["mysql"]
    return {
        "host": s["host"],
        "port": s.getint("port"),
        "database": s["database"],
        "user": s["readonly_user"] if readonly else s["user"],
        "password": s["readonly_password"] if readonly else s["password"],
    }


def ensure_dirs():
    for d in (INSTANCE_DIR, BACKUP_DIR, UPLOAD_DIR, LOG_DIR):
        os.makedirs(d, exist_ok=True)
