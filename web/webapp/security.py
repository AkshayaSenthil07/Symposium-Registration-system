"""Password hashing, input validation, tokens, rate limiting and role guards."""
import base64
import hashlib
import hmac
import re
import secrets
import string
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 260_000
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
PHONE_RE = re.compile(r"^[0-9]{10}$")
UTR_RE = re.compile(r"^[A-Za-z0-9]{8,22}$")
TICKET_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # no 0/O/1/I - easy to read aloud


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join([ALGORITHM, str(ITERATIONS), base64.b64encode(salt).decode(),
                     base64.b64encode(digest).decode()])


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(actual, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password(secrets.token_hex(8))   # equalises timing for unknown e-mails


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if len(password) > 128:
        problems.append("at most 128 characters")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[0-9]", password):
        problems.append("a digit")
    return problems


def random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if not password_problems(pwd):
            return pwd


# ---------------------------------------------------------------- validation
def clean(value, max_len: int = 255) -> str:
    return (value or "").strip()[:max_len]


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or "")) and len(email) <= 120


def valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone or ""))


def valid_utr(utr: str) -> bool:
    return bool(UTR_RE.match(utr or ""))


def safe_next(url: str | None) -> str | None:
    """Only allow redirects to local paths (prevents open-redirect attacks)."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None


# ---------------------------------------------------------------- tokens
def new_token() -> tuple[str, str]:
    """Returns (token for the link, SHA-256 hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ticket_code() -> str:
    return "".join(secrets.choice(TICKET_ALPHABET) for _ in range(12))


def sign(message: str, secret: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def signature_ok(message: str | bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    data = message if isinstance(message, bytes) else message.encode()
    expected = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """In-memory sliding window per (bucket, client). Fine for one server process."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str, limit: int, window: int) -> bool:
        """Records a hit; returns False when the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 50_000:            # memory guard
                self._hits.clear()
            return True


limiter = RateLimiter()


def client_ip() -> str:
    return request.remote_addr or "unknown"


def rate_limit(bucket: str, limit: int, window: int):
    """Decorator for POST handlers."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if request.method == "POST" and not limiter.hit(bucket, client_ip(), limit, window):
                abort(429)
            return fn(*args, **kwargs)
        return wrapper
    return deco


# ---------------------------------------------------------------- access control
STAFF_ROLES = ("ADMIN", "CASHIER", "COORDINATOR")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def fresh_session_id():
    """Rotate the session on login (prevents session fixation)."""
    keep = {k: session[k] for k in ("csrf_token",) if k in session}
    session.clear()
    session.update(keep)
    session.permanent = True
