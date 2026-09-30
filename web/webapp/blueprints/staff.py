"""Staff area (filled in Stage C)."""
from flask import Blueprint, render_template

from webapp.security import STAFF_ROLES, roles_required

bp = Blueprint("staff", __name__, url_prefix="/staff")


@bp.route("/")
@roles_required(*STAFF_ROLES)
def dashboard():
    return render_template("participant/placeholder.html")
