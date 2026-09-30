"""Participant area (filled in Stage B)."""
from flask import Blueprint, render_template

from webapp.security import roles_required

bp = Blueprint("participant", __name__, url_prefix="/me")


@bp.route("/")
@roles_required("PARTICIPANT")
def dashboard():
    return render_template("participant/placeholder.html")


@bp.route("/register/<int:event_id>")
@roles_required("PARTICIPANT")
def register(event_id):
    return render_template("participant/placeholder.html")
