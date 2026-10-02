"""Password hashing (PBKDF2-HMAC-SHA256 with per-user salt) and input validation."""
import base64
import hashlib
import hmac
import re
import secrets
import string

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE_RE = re.compile(r"^[0-9]{10}$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join([
        ALGORITHM,
        str(ITERATIONS),
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    ])


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def password_problems(password: str) -> list[str]:
    """Return the unmet password rules (empty list = strong enough)."""
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a digit")
    return problems


def password_strength(password: str) -> tuple[float, str]:
    """0..1 score and a label for the strength meter."""
    score = 0
    score += min(len(password), 12) / 12 * 2
    score += bool(re.search(r"[A-Z]", password))
    score += bool(re.search(r"[a-z]", password))
    score += bool(re.search(r"[0-9]", password))
    score += bool(re.search(r"[^A-Za-z0-9]", password))
    value = score / 6
    if not password:
        return 0.0, ""
    if value < 0.45:
        return value, "Weak"
    if value < 0.75:
        return value, "Medium"
    return value, "Strong"


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone.strip()))


def temporary_password() -> str:
    """Readable random password that satisfies password_problems()."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(10))
        if not password_problems(pwd):
            return pwd
