"""Payments (filled in Stage B)."""
from flask import Blueprint

bp = Blueprint("payments", __name__, url_prefix="/pay")


@bp.route("/razorpay/webhook", methods=["POST"])
def razorpay_webhook():
    return {"status": "ignored"}, 200
