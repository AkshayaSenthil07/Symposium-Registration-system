"""Flask application factory: security settings, blueprints, error pages, background jobs."""
import datetime as dt
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, g, render_template, request, session
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from webapp import config, db, util

csrf = CSRFProtect()


def create_app(test_config: dict | None = None) -> Flask:
    config.ensure_dirs()
    cfg = config.load()
    if not os.path.exists(config.CONFIG_PATH) and not test_config:
        config.save(cfg)
    app = Flask(__name__, instance_path=config.INSTANCE_DIR)
    https = cfg["server"].getboolean("https")
    app.config.update(
        SECRET_KEY=cfg["server"]["secret_key"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=https,
        SESSION_COOKIE_NAME="sym_session",
        PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=8),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,           # 5 MB uploads max
        WTF_CSRF_TIME_LIMIT=None,                      # token valid for the whole session
        WTF_CSRF_SSL_STRICT=https,
        MAIL_MODE=cfg["mail"]["mode"],
        GATEWAY_MODE=cfg["payment"]["gateway_mode"],
        BASE_URL=cfg["server"]["base_url"].rstrip("/"),
        CFG=cfg,
        TESTING=False,
        START_JOBS=True,
    )
    if test_config:
        app.config.update(test_config)
    if cfg["server"].getboolean("behind_proxy"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _setup_logging(app)
    csrf.init_app(app)
    if not app.config.get("SKIP_DB"):
        db.init(config.mysql_params(cfg), config.mysql_params(cfg, readonly=True))

    _register_hooks(app, https)                  # must run before blueprint hooks (loads g.user)
    from webapp.blueprints import admin, auth, participant, payments, public, staff
    for bp in (public.bp, auth.bp, participant.bp, payments.bp, staff.bp, admin.bp):
        app.register_blueprint(bp)
    csrf.exempt(payments.razorpay_webhook)       # verified by HMAC signature instead

    _register_template_helpers(app)
    _register_errors(app)

    if app.config["START_JOBS"] and not app.config["TESTING"]:
        from webapp.services import jobs
        jobs.start(app)
    return app


def _setup_logging(app):
    handler = RotatingFileHandler(os.path.join(config.LOG_DIR, "app.log"), maxBytes=2_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def _register_hooks(app, https):
    from webapp.services import users

    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("uid")
        if uid:
            user = users.session_user(uid, session.get("ver"))
            if user is None:
                session.clear()
            else:
                g.user = user

    @app.after_request
    def security_headers(resp):
        style = "'self' 'unsafe-inline'" if g.get("relaxed_csp") else "'self'"
        csp = (f"default-src 'self'; img-src 'self' data: blob: https://*.razorpay.com; style-src {style}; "
               "script-src 'self' https://checkout.razorpay.com; "
               "frame-src https://api.razorpay.com https://checkout.razorpay.com; "
               "connect-src 'self' https://lumberjack.razorpay.com; "
               "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self' "
               "https://api.razorpay.com; frame-ancestors 'none'")
        resp.headers["Content-Security-Policy"] = csp
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        if https:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if g.get("user") is not None:
            resp.headers["Cache-Control"] = "no-store"
        return resp


def _register_template_helpers(app):
    from webapp.services import news, settings

    @app.context_processor
    def inject():
        try:
            site = settings.all_settings()
        except db.DatabaseError:
            site = dict(settings.DEFAULTS)
        return {"site": site, "current_user": g.get("user"), "now": util.now(),
                "ticker": _safe(news.active_ticker) if request.endpoint and
                request.endpoint.startswith("public.") else []}

    for name, fn in (("date", util.fmt_date), ("time", util.fmt_time), ("money", util.money),
                     ("hhmm", util.hhmm), ("dtlocal", util.as_datetime_local)):
        app.add_template_filter(fn, name)


def _safe(fn):
    try:
        return fn()
    except db.DatabaseError:
        return []


def _register_errors(app):
    def page(code, title, message):
        return render_template("errors/error.html", code=code, title=title, message=message), code

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return page(400, "Form expired", "The form expired or was sent from another site. "
                                         "Go back, refresh the page and try again.")

    @app.errorhandler(403)
    def forbidden(_e):
        return page(403, "Not allowed", "You do not have permission to open this page.")

    @app.errorhandler(404)
    def not_found(_e):
        return page(404, "Page not found", "The page you are looking for does not exist.")

    @app.errorhandler(413)
    def too_large(_e):
        return page(413, "File too large", "The file you uploaded is larger than 5 MB.")

    @app.errorhandler(429)
    def too_many(_e):
        return page(429, "Slow down", "Too many attempts from your network. Please wait a few minutes.")

    @app.errorhandler(db.DatabaseError)
    def db_error(e):
        return page(503, "Temporarily unavailable", str(e))

    @app.errorhandler(500)
    def server_error(_e):
        return page(500, "Something went wrong", "An unexpected error occurred. It has been logged; "
                                                 "please try again.")
