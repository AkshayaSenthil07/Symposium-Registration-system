"""Public pages: home (with flash news), events, schedule, results, legal pages, certificate check."""
import os

from flask import Blueprint, abort, render_template, request, send_from_directory

from webapp import config, db
from webapp.services import events, results, settings

bp = Blueprint("public", __name__)


@bp.route("/")
def home():
    all_events = events.list_events()
    upcoming = [e for e in all_events if not e["is_past"]]
    stats = db.get().one(
        "SELECT (SELECT COUNT(*) FROM event WHERE is_published AND status <> 'CANCELLED') AS events, "
        "(SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT') AS participants, "
        "(SELECT COUNT(DISTINCT college_id) FROM participant_profile) AS colleges")
    return render_template("public/home.html", featured=upcoming[:6], stats=stats,
                           categories=events.categories(),
                           changed=[e for e in all_events if e["recently_changed"]][:4])


@bp.route("/events")
def event_list():
    cat = request.args.get("category", type=int)
    q = request.args.get("q", "").strip()[:60]
    return render_template("public/events.html", events=events.list_events(category_id=cat, search=q),
                           categories=events.categories(), active_cat=cat, q=q)


@bp.route("/events/<int:event_id>")
def event_detail(event_id):
    e = events.get(event_id)
    if not e:
        abort(404)
    return render_template("public/event_detail.html", e=e)


@bp.route("/schedule")
def schedule():
    return render_template("public/schedule.html", days=events.schedule())


@bp.route("/results")
def results_page():
    return render_template("public/results.html", winners=results.published_winners(),
                           leaderboard=results.college_leaderboard())


@bp.route("/verify/<code>")
def verify_certificate(code):
    cert = results.certificate_lookup(code[:20])
    return render_template("public/verify.html", cert=cert, code=code[:20])


@bp.route("/page/<name>")
def legal(name):
    titles = {"terms": ("Terms & Conditions", "terms_text"), "privacy": ("Privacy Policy", "privacy_note"),
              "refunds": ("Refund & Cancellation Policy", "refund_policy"), "contact": ("Contact Us", None)}
    if name not in titles:
        abort(404)
    title, key = titles[name]
    return render_template("public/legal.html", title=title, body=settings.get(key) if key else None, name=name)


@bp.route("/media/logo")
def logo():
    path = settings.get("logo_path")
    if not path or "/" in path or "\\" in path or not os.path.exists(os.path.join(config.UPLOAD_DIR, path)):
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, path, max_age=300)


@bp.route("/health")
def health():
    ok = db.get().ping()
    return ({"status": "ok" if ok else "db-unavailable"}, 200 if ok else 503)
