"""Backups: every table exported to a compressed JSON file in instance/backups.

Works with the limited app user (no mysqldump or root needed). Restore replaces all data in one
transaction with triggers paused (@restoring = 1), so derived rows are not duplicated.
Scheduled backups run from the background job every [backup] interval_minutes (default 30).
"""
import datetime as dt
import decimal
import gzip
import json
import os
import re
import time

from webapp import config, db
from webapp.services import settings

TABLES = ["college", "department", "venue", "event_category", "app_setting", "app_user", "participant_profile",
          "user_token", "event", "event_staff", "coupon", "registration", "team_member", "payment", "bank_txn",
          "judge_score", "event_result", "feedback", "news_item", "email_outbox", "audit_log"]
NAME_RE = re.compile(r"^backup-\d{8}-\d{6}-[a-z]+\.json\.gz$")
FORMAT = 1


def _encode(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, dt.timedelta):
        s = int(v.total_seconds())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


def create(cfg, label: str = "manual") -> str:
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    data = {"format": FORMAT, "created": dt.datetime.now().isoformat(timespec="seconds"), "tables": {}}
    with db.get().transaction(dictionary=False) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    with db.get().transaction(dictionary=False) as cur:
        for t in TABLES:
            cur.execute(f"SELECT * FROM `{t}`")
            cols = [d[0] for d in cur.description]
            data["tables"][t] = {"columns": cols, "rows": [[_encode(v) for v in row] for row in cur.fetchall()]}
    name = f"backup-{dt.datetime.now():%Y%m%d-%H%M%S}-{label}.json.gz"
    path = os.path.join(config.BACKUP_DIR, name)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
    _rotate(cfg)
    return name


def _rotate(cfg):
    keep = cfg["backup"].getint("keep", 48)
    auto = sorted(f for f in os.listdir(config.BACKUP_DIR) if NAME_RE.match(f) and f.endswith("-auto.json.gz"))
    for f in auto[:-keep] if keep > 0 else []:
        os.remove(os.path.join(config.BACKUP_DIR, f))


def listing() -> list[dict]:
    if not os.path.isdir(config.BACKUP_DIR):
        return []
    out = []
    for f in sorted(os.listdir(config.BACKUP_DIR), reverse=True):
        if NAME_RE.match(f):
            p = os.path.join(config.BACKUP_DIR, f)
            out.append({"name": f, "size_kb": round(os.path.getsize(p) / 1024, 1),
                        "created": dt.datetime.fromtimestamp(os.path.getmtime(p))})
    return out


def path_for(name: str) -> str | None:
    if not NAME_RE.match(name or ""):
        return None
    p = os.path.join(config.BACKUP_DIR, name)
    return p if os.path.exists(p) else None


def maybe_scheduled(cfg) -> str | None:
    minutes = cfg["backup"].getint("interval_minutes", 30)
    if minutes <= 0:
        return None
    autos = [b for b in listing() if b["name"].endswith("-auto.json.gz")]
    if autos and (time.time() - autos[0]["created"].timestamp()) < minutes * 60:
        return None
    return create(cfg, label="auto")


def restore(raw: bytes, cfg) -> dict:
    try:
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise db.DatabaseError("This is not a valid backup file.") from exc
    if data.get("format") != FORMAT or set(data.get("tables", {})) - set(TABLES):
        raise db.DatabaseError("This backup was made by a different version and cannot be restored here.")
    safety = create(cfg, label="prerestore")           # always keep a way back
    counts = {}
    with db.get().transaction(dictionary=False) as cur:
        cur.execute("SET @restoring = 1")
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for t in reversed(TABLES):
                cur.execute(f"DELETE FROM `{t}`")
            for t in TABLES:
                block = data["tables"].get(t)
                if not block or not block["rows"]:
                    counts[t] = 0
                    continue
                cols = ", ".join(f"`{c}`" for c in block["columns"])
                marks = ", ".join(["%s"] * len(block["columns"]))
                cur.executemany(f"INSERT INTO `{t}` ({cols}) VALUES ({marks})", block["rows"])
                counts[t] = len(block["rows"])
        finally:
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            cur.execute("SET @restoring = NULL")
    settings.invalidate()
    return {"counts": counts, "safety_backup": safety, "created": data.get("created")}
