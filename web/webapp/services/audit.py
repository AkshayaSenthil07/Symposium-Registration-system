"""Audit trail helper."""
from flask import has_request_context, request

from webapp import db


def log(user_id, action: str, details: str = "", cur=None) -> None:
    ip = request.remote_addr if has_request_context() else None
    sql = "INSERT INTO audit_log (user_id, action, details, ip_address) VALUES (%s, %s, %s, %s)"
    params = (user_id, action[:50], (details or "")[:255], ip)
    if cur is not None:
        cur.execute(sql, params)
    else:
        db.get().run(sql, params)
