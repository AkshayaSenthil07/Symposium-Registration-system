"""Sign in / sign up / e-mail verification / password reset / sign out."""
from flask import (Blueprint, current_app, flash, g, redirect, render_template, request, session,
                   url_for)

from webapp import db
from webapp.security import (clean, fresh_session_id, login_required, password_problems, rate_limit,
                             safe_next, valid_email, valid_phone)
from webapp.services import audit, mailer, settings, users

bp = Blueprint("auth", __name__)


def _home_for(role: str) -> str:
    return url_for("staff.dashboard") if role != "PARTICIPANT" else url_for("participant.dashboard")


def send_verification(user_id: int, email: str, name: str) -> None:
    token = users.issue_token(user_id, "VERIFY")
    link = current_app.config["BASE_URL"] + url_for("auth.verify", token=token)
    mailer.queue(email, f"Verify your e-mail - {settings.get('symposium_name')}", "verify", name=name, link=link)


@bp.route("/login", methods=["GET", "POST"])
@rate_limit("login", limit=20, window=300)
def login():
    if g.user:
        return redirect(_home_for(g.user["role"]))
    email = ""
    if request.method == "POST":
        email = clean(request.form.get("email"), 120).lower()
        try:
            result = users.login(email, request.form.get("password", ""))
        except users.AuthError as exc:
            flash(str(exc), "error")
            return render_template("auth/login.html", email=email), 401
        fresh_session_id()
        session["uid"], session["ver"] = result["user_id"], result["ver"]
        nxt = safe_next(request.args.get("next"))
        return redirect(nxt or _home_for(result["role"]))
    return render_template("auth/login.html", email=email)


@bp.route("/signup", methods=["GET", "POST"])
@rate_limit("signup", limit=10, window=3600)
def signup():
    if g.user:
        return redirect(_home_for(g.user["role"]))
    if not settings.flag("signups_open"):
        flash("Online sign-ups are closed. Please register at the registration desk.", "info")
        return redirect(url_for("public.home"))
    form = request.form
    if request.method == "POST":
        name = clean(form.get("full_name"), 100)
        email = clean(form.get("email"), 120).lower()
        phone = clean(form.get("phone"), 15)
        college = clean(form.get("college"), 150)
        dept = form.get("dept_id", type=int)
        year = form.get("year", type=int)
        gender = form.get("gender") if form.get("gender") in ("Male", "Female", "Other") else None
        pwd = form.get("password", "")
        errors = []
        if len(name) < 3:
            errors.append("Enter your full name.")
        if not valid_email(email):
            errors.append("Enter a valid e-mail address.")
        if not valid_phone(phone):
            errors.append("Mobile number must be exactly 10 digits.")
        if len(college) < 3:
            errors.append("Enter your college name.")
        if not dept:
            errors.append("Select your department.")
        if year not in (1, 2, 3, 4, 5):
            errors.append("Select your year of study.")
        weak = password_problems(pwd)
        if weak:
            errors.append("Password needs " + ", ".join(weak) + ".")
        elif pwd != form.get("confirm", ""):
            errors.append("Passwords do not match.")
        if not form.get("consent"):
            errors.append("Please accept the terms and privacy policy.")
        if not errors:
            try:
                uid = users.create_participant(name, email, phone, pwd, college, dept, year, gender)
            except db.DatabaseError as exc:
                errors.append(str(exc))
            else:
                send_verification(uid, email, name.split()[0])
                flash("Account created! We sent a verification link to your e-mail. "
                      "Open it to activate registrations.", "success")
                return redirect(url_for("auth.login"))
        for e in errors:
            flash(e, "error")
    return render_template("auth/signup.html", form=form, colleges=users.colleges(),
                           departments=users.departments())


@bp.route("/verify-email/<token>")
def verify(token):
    uid = users.consume_token(token, "VERIFY")
    if uid is None:
        flash("This verification link is invalid or has expired. Sign in to get a new one.", "error")
    else:
        users.mark_verified(uid)
        flash("E-mail verified. You can now register for events.", "success")
    return redirect(url_for("participant.dashboard") if g.user else url_for("auth.login"))


@bp.route("/verify-email/resend", methods=["POST"])
@login_required
@rate_limit("resend", limit=3, window=900)
def resend_verification():
    if not g.user["email_verified"]:
        send_verification(g.user["user_id"], g.user["email"], g.user["first_name"])
        flash("A new verification link has been sent to your e-mail.", "success")
    return redirect(url_for("participant.dashboard"))


@bp.route("/forgot", methods=["GET", "POST"])
@rate_limit("forgot", limit=5, window=900)
def forgot():
    if request.method == "POST":
        email = clean(request.form.get("email"), 120).lower()
        user = users.by_email(email) if valid_email(email) else None
        if user and user["is_active"]:
            token = users.issue_token(user["user_id"], "RESET")
            link = current_app.config["BASE_URL"] + url_for("auth.reset", token=token)
            mailer.queue(user["email"], f"Reset your password - {settings.get('symposium_name')}", "reset",
                         name=user["full_name"].split()[0], link=link)
            audit.log(user["user_id"], "RESET_REQUESTED", "")
        # same message either way, so nobody can find out which e-mails are registered
        flash("If an account exists for that e-mail, a reset link has been sent. It is valid for 1 hour.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
@rate_limit("reset", limit=10, window=900)
def reset(token):
    if users.peek_token(token, "RESET") is None:
        flash("This reset link is invalid or has expired. Request a new one.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        weak = password_problems(pwd)
        if weak:
            flash("Password needs " + ", ".join(weak) + ".", "error")
        elif pwd != request.form.get("confirm", ""):
            flash("Passwords do not match.", "error")
        else:
            uid = users.consume_token(token, "RESET")
            if uid:
                users.set_password(uid, pwd, reason="PASSWORD_RESET")
                users.mark_verified(uid)            # they proved they own the mailbox
                session.clear()
                flash("Password changed. Please sign in with your new password.", "success")
                return redirect(url_for("auth.login"))
    return render_template("auth/reset.html")


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
@rate_limit("chpwd", limit=10, window=900)
def change_password():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        weak = password_problems(pwd)
        if not users.check_password(g.user["user_id"], request.form.get("current", "")):
            flash("Your current password is incorrect.", "error")
        elif weak:
            flash("New password needs " + ", ".join(weak) + ".", "error")
        elif pwd != request.form.get("confirm", ""):
            flash("New passwords do not match.", "error")
        elif pwd == request.form.get("current"):
            flash("Choose a password different from the current one.", "error")
        else:
            session["ver"] = users.set_password(g.user["user_id"], pwd)
            flash("Password updated.", "success")
            return redirect(_home_for(g.user["role"]))
    return render_template("auth/change_password.html", forced=g.user["must_change_password"])


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        audit.log(g.user["user_id"], "LOGOUT", "")
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("public.home"))


@bp.before_app_request
def force_password_change():
    """Staff created with a temporary password (and the first admin) must change it first."""
    if (g.get("user") and g.user["must_change_password"] and request.endpoint
            and request.endpoint not in ("auth.change_password", "auth.logout", "static")):
        if request.endpoint.startswith(("staff.", "admin.", "participant.", "payments.")):
            flash("Please set a new password before continuing.", "info")
            return redirect(url_for("auth.change_password"))
    return None
