"""Authentication, account creation and password management."""
from dataclasses import dataclass

from symposium import db
from symposium.security import hash_password, temporary_password, verify_password

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 5


class AuthError(Exception):
    pass


@dataclass
class User:
    user_id: int
    full_name: str
    email: str
    role: str
    phone: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0]


def audit(user_id: int | None, action: str, details: str = "") -> None:
    db.get().execute("INSERT INTO audit_log (user_id, action, details) VALUES (%s, %s, %s)",
                     (user_id, action, details[:255]))


def login(email: str, password: str) -> User:
    email = email.strip().lower()
    if not email or not password:
        raise AuthError("Please enter both e-mail and password.")
    database = db.get()
    row = database.fetch_one(
        "SELECT user_id, full_name, email, phone, role, password_hash, is_active, failed_attempts, "
        "locked_until, TIMESTAMPDIFF(SECOND, NOW(), locked_until) AS lock_seconds "
        "FROM app_user WHERE email = %s", (email,))
    if row is None:
        raise AuthError("Invalid e-mail or password.")
    if row["lock_seconds"] is not None and row["lock_seconds"] > 0:
        minutes = row["lock_seconds"] // 60 + 1
        raise AuthError(f"Too many failed attempts. Account locked - try again in {minutes} min.")
    if not row["is_active"]:
        raise AuthError("This account has been deactivated. Please contact the organisers.")

    if not verify_password(password, row["password_hash"]):
        attempts = row["failed_attempts"] + 1
        if attempts >= MAX_FAILED_ATTEMPTS:
            database.execute("UPDATE app_user SET failed_attempts = 0, "
                             "locked_until = NOW() + INTERVAL %s MINUTE WHERE user_id = %s",
                             (LOCK_MINUTES, row["user_id"]))
            audit(row["user_id"], "ACCOUNT_LOCKED", "Locked after repeated failed logins")
            raise AuthError(f"Too many failed attempts. Account locked for {LOCK_MINUTES} minutes.")
        database.execute("UPDATE app_user SET failed_attempts = %s WHERE user_id = %s",
                         (attempts, row["user_id"]))
        audit(row["user_id"], "LOGIN_FAILED", "Wrong password")
        left = MAX_FAILED_ATTEMPTS - attempts
        raise AuthError(f"Invalid e-mail or password. {left} attempt(s) left before lock-out.")

    database.execute("UPDATE app_user SET failed_attempts = 0, locked_until = NULL, "
                     "last_login = NOW() WHERE user_id = %s", (row["user_id"],))
    audit(row["user_id"], "LOGIN", f"{row['role'].title()} logged in")
    return User(row["user_id"], row["full_name"], row["email"], row["role"], row["phone"])


def register_participant(full_name: str, email: str, phone: str, password: str,
                         college_name: str, dept_id: int, year: int, gender: str | None) -> int:
    """Creates app_user + participant_profile in ONE transaction."""
    with db.get().cursor() as cur:
        cur.execute("SELECT college_id FROM college WHERE college_name = %s", (college_name.strip(),))
        row = cur.fetchone()
        if row:
            college_id = row["college_id"]
        else:                                   # new college typed by the participant
            cur.execute("INSERT INTO college (college_name) VALUES (%s)", (college_name.strip(),))
            college_id = cur.lastrowid
        cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, role) "
                    "VALUES (%s, %s, %s, %s, 'PARTICIPANT')",
                    (full_name.strip(), email.strip().lower(), phone.strip() or None,
                     hash_password(password)))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO participant_profile (user_id, college_id, dept_id, year_of_study, gender) "
                    "VALUES (%s, %s, %s, %s, %s)", (user_id, college_id, dept_id, year, gender))
        cur.execute("INSERT INTO audit_log (user_id, action, details) VALUES (%s, 'SIGNUP', %s)",
                    (user_id, f"New participant {email.strip().lower()}"))
    return user_id


def get_profile(user_id: int) -> dict | None:
    return db.get().fetch_one(
        "SELECT u.full_name, u.email, u.phone, pp.college_id, c.college_name, pp.dept_id, "
        "d.dept_name, pp.year_of_study, pp.gender FROM app_user u "
        "LEFT JOIN participant_profile pp ON pp.user_id = u.user_id "
        "LEFT JOIN college c ON c.college_id = pp.college_id "
        "LEFT JOIN department d ON d.dept_id = pp.dept_id WHERE u.user_id = %s", (user_id,))


def update_profile(user_id: int, full_name: str, phone: str, college_name: str, dept_id: int,
                   year: int, gender: str | None) -> None:
    with db.get().cursor() as cur:
        cur.execute("SELECT college_id FROM college WHERE college_name = %s", (college_name.strip(),))
        row = cur.fetchone()
        if row:
            college_id = row["college_id"]
        else:
            cur.execute("INSERT INTO college (college_name) VALUES (%s)", (college_name.strip(),))
            college_id = cur.lastrowid
        cur.execute("UPDATE app_user SET full_name = %s, phone = %s WHERE user_id = %s",
                    (full_name.strip(), phone.strip() or None, user_id))
        cur.execute("UPDATE participant_profile SET college_id = %s, dept_id = %s, year_of_study = %s, "
                    "gender = %s WHERE user_id = %s", (college_id, dept_id, year, gender, user_id))
        cur.execute("INSERT INTO audit_log (user_id, action, details) VALUES (%s, 'PROFILE_UPDATED', %s)",
                    (user_id, "Participant updated profile"))


def create_admin(full_name: str, email: str, phone: str, password: str, actor_id: int) -> int:
    uid = db.get().execute(
        "INSERT INTO app_user (full_name, email, phone, password_hash, role) VALUES (%s,%s,%s,%s,'ADMIN')",
        (full_name.strip(), email.strip().lower(), phone.strip() or None, hash_password(password)))
    audit(actor_id, "ADMIN_CREATED", f"Created admin {email.strip().lower()}")
    return uid


def change_password(user_id: int, old_password: str, new_password: str) -> None:
    stored = db.get().scalar("SELECT password_hash FROM app_user WHERE user_id = %s", (user_id,))
    if not stored or not verify_password(old_password, stored):
        raise AuthError("Current password is incorrect.")
    db.get().execute("UPDATE app_user SET password_hash = %s WHERE user_id = %s",
                     (hash_password(new_password), user_id))
    audit(user_id, "PASSWORD_CHANGED", "User changed own password")


def reset_password(user_id: int, actor_id: int) -> str:
    temp = temporary_password()
    db.get().execute("UPDATE app_user SET password_hash = %s, failed_attempts = 0, locked_until = NULL "
                     "WHERE user_id = %s", (hash_password(temp), user_id))
    audit(actor_id, "PASSWORD_RESET", f"Reset password of user #{user_id}")
    return temp


def set_active(user_id: int, active: bool, actor_id: int) -> None:
    db.get().execute("UPDATE app_user SET is_active = %s WHERE user_id = %s", (active, user_id))
    audit(actor_id, "USER_ACTIVATED" if active else "USER_DEACTIVATED", f"User #{user_id}")
