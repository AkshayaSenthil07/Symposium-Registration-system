"""Accounts: login with lock-out, sign-up, e-mail verification, password reset, staff, profile."""
import datetime as dt
import hashlib

from webapp import db
from webapp.security import (DUMMY_HASH, hash_password, new_token, token_hash, verify_password)
from webapp.services import audit
from webapp.util import now

MAX_FAILED = 5
LOCK_MINUTES = 15
TOKEN_HOURS = {"VERIFY": 48, "RESET": 1}


class AuthError(Exception):
    pass


def session_version(password_hash: str) -> str:
    """Changes whenever the password changes -> old sessions are invalidated."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def session_user(uid: int, ver: str | None) -> dict | None:
    row = db.get().one("SELECT user_id, full_name, email, phone, role, is_active, email_verified, "
                       "must_change_password, password_hash, is_demo FROM app_user WHERE user_id = %s", (uid,))
    if not row or not row["is_active"] or session_version(row.pop("password_hash")) != ver:
        return None
    row["first_name"] = row["full_name"].split()[0]
    row["is_staff"] = row["role"] != "PARTICIPANT"
    return row


def login(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    row = db.get().one("SELECT user_id, full_name, role, password_hash, is_active, email_verified, "
                       "failed_attempts, TIMESTAMPDIFF(SECOND, NOW(), locked_until) AS lock_seconds "
                       "FROM app_user WHERE email = %s", (email,))
    if row is None:
        verify_password(password, DUMMY_HASH)          # same timing as a real check
        raise AuthError("Invalid e-mail or password.")
    if row["lock_seconds"] and row["lock_seconds"] > 0:
        raise AuthError(f"Too many failed attempts. Try again in {row['lock_seconds'] // 60 + 1} minute(s).")
    if not verify_password(password, row["password_hash"]):
        attempts = row["failed_attempts"] + 1
        if attempts >= MAX_FAILED:
            db.get().run("UPDATE app_user SET failed_attempts = 0, locked_until = NOW() + INTERVAL %s MINUTE "
                         "WHERE user_id = %s", (LOCK_MINUTES, row["user_id"]))
            audit.log(row["user_id"], "ACCOUNT_LOCKED", "Too many failed logins")
            raise AuthError(f"Too many failed attempts. Account locked for {LOCK_MINUTES} minutes.")
        db.get().run("UPDATE app_user SET failed_attempts = %s WHERE user_id = %s", (attempts, row["user_id"]))
        audit.log(row["user_id"], "LOGIN_FAILED", "Wrong password")
        raise AuthError("Invalid e-mail or password.")
    if not row["is_active"]:
        raise AuthError("This account is disabled. Please contact the organisers.")
    db.get().run("UPDATE app_user SET failed_attempts = 0, locked_until = NULL, last_login = NOW() "
                 "WHERE user_id = %s", (row["user_id"],))
    audit.log(row["user_id"], "LOGIN", f"{row['role'].title()} signed in")
    return {"user_id": row["user_id"], "ver": session_version(row["password_hash"]),
            "email_verified": row["email_verified"], "role": row["role"]}


def get_or_create_college(cur, name: str) -> int:
    cur.execute("SELECT college_id FROM college WHERE college_name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row["college_id"]
    cur.execute("INSERT INTO college (college_name) VALUES (%s)", (name,))
    return cur.lastrowid


def create_participant(full_name, email, phone, password, college_name, dept_id, year, gender,
                       verified=False, cur=None, is_demo=False) -> int:
    def work(c):
        college_id = get_or_create_college(c, college_name.strip())
        c.execute("INSERT INTO app_user (full_name, email, phone, password_hash, role, email_verified, is_demo) "
                  "VALUES (%s, %s, %s, %s, 'PARTICIPANT', %s, %s)",
                  (full_name.strip(), email.strip().lower(), phone or None, hash_password(password),
                   verified, is_demo))
        uid = c.lastrowid
        c.execute("INSERT INTO participant_profile (user_id, college_id, dept_id, year_of_study, gender) "
                  "VALUES (%s, %s, %s, %s, %s)", (uid, college_id, dept_id, year, gender or None))
        return uid
    if cur is not None:
        return work(cur)
    with db.get().transaction() as c:
        uid = work(c)
        audit.log(uid, "SIGNUP", f"New participant {email.strip().lower()}", cur=c)
        return uid


def issue_token(user_id: int, purpose: str, cur=None) -> str:
    token, digest = new_token()
    expires = now() + dt.timedelta(hours=TOKEN_HOURS[purpose])
    sql_del = "DELETE FROM user_token WHERE user_id = %s AND purpose = %s AND used_at IS NULL"
    sql_ins = "INSERT INTO user_token (user_id, purpose, token_hash, expires_at) VALUES (%s, %s, %s, %s)"
    if cur is not None:
        cur.execute(sql_del, (user_id, purpose))
        cur.execute(sql_ins, (user_id, purpose, digest, expires))
    else:
        with db.get().transaction() as c:
            c.execute(sql_del, (user_id, purpose))
            c.execute(sql_ins, (user_id, purpose, digest, expires))
    return token


def consume_token(token: str, purpose: str) -> int | None:
    """Marks the token used and returns its user_id, or None if invalid/expired."""
    with db.get().transaction() as cur:
        cur.execute("SELECT token_id, user_id FROM user_token WHERE token_hash = %s AND purpose = %s "
                    "AND used_at IS NULL AND expires_at > NOW() FOR UPDATE", (token_hash(token or ""), purpose))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("UPDATE user_token SET used_at = NOW() WHERE token_id = %s", (row["token_id"],))
        return row["user_id"]


def peek_token(token: str, purpose: str) -> int | None:
    return db.get().value("SELECT user_id FROM user_token WHERE token_hash = %s AND purpose = %s "
                          "AND used_at IS NULL AND expires_at > NOW()", (token_hash(token or ""), purpose))


def mark_verified(user_id: int) -> None:
    db.get().run("UPDATE app_user SET email_verified = TRUE WHERE user_id = %s", (user_id,))
    audit.log(user_id, "EMAIL_VERIFIED", "")


def set_password(user_id: int, password: str, actor_id=None, reason="PASSWORD_CHANGED") -> str:
    new_hash = hash_password(password)
    db.get().run("UPDATE app_user SET password_hash = %s, must_change_password = FALSE, failed_attempts = 0, "
                 "locked_until = NULL WHERE user_id = %s", (new_hash, user_id))
    audit.log(actor_id or user_id, reason, f"User #{user_id}")
    return session_version(new_hash)


def check_password(user_id: int, password: str) -> bool:
    stored = db.get().value("SELECT password_hash FROM app_user WHERE user_id = %s", (user_id,))
    return bool(stored) and verify_password(password, stored)


def by_email(email: str) -> dict | None:
    return db.get().one("SELECT user_id, full_name, email, is_active, email_verified FROM app_user "
                        "WHERE email = %s", ((email or "").strip().lower(),))


def create_staff(full_name, email, phone, role, password, actor_id, is_demo=False) -> int:
    uid = db.get().run("INSERT INTO app_user (full_name, email, phone, password_hash, role, email_verified, "
                       "must_change_password, is_demo) VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, %s)",
                       (full_name.strip(), email.strip().lower(), phone or None, hash_password(password),
                        role, is_demo))
    audit.log(actor_id, "STAFF_CREATED", f"{role} {email}")
    return uid


def profile(user_id: int) -> dict | None:
    return db.get().one(
        "SELECT u.user_id, u.full_name, u.email, u.phone, u.role, pp.college_id, c.college_name, pp.dept_id, "
        "d.dept_name, pp.year_of_study, pp.gender FROM app_user u "
        "LEFT JOIN participant_profile pp ON pp.user_id = u.user_id "
        "LEFT JOIN college c ON c.college_id = pp.college_id "
        "LEFT JOIN department d ON d.dept_id = pp.dept_id WHERE u.user_id = %s", (user_id,))


def update_profile(user_id, full_name, phone, college_name, dept_id, year, gender) -> None:
    with db.get().transaction() as cur:
        college_id = get_or_create_college(cur, college_name.strip())
        cur.execute("UPDATE app_user SET full_name = %s, phone = %s WHERE user_id = %s",
                    (full_name.strip(), phone or None, user_id))
        cur.execute("UPDATE participant_profile SET college_id = %s, dept_id = %s, year_of_study = %s, "
                    "gender = %s WHERE user_id = %s", (college_id, dept_id, year, gender or None, user_id))
        audit.log(user_id, "PROFILE_UPDATED", "", cur=cur)


def colleges() -> list[dict]:
    return db.get().all("SELECT college_id, college_name FROM college ORDER BY college_name")


def departments() -> list[dict]:
    return db.get().all("SELECT dept_id, dept_name FROM department ORDER BY dept_name")
