"""QR codes as PNG bytes: UPI payment requests and entry tickets."""
import io
import urllib.parse

import qrcode
from flask import current_app, url_for


def png(data: str, box: int = 8) -> bytes:
    img = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box, border=2)
    img.add_data(data)
    img.make(fit=True)
    buf = io.BytesIO()
    img.make_image(fill_color="#14264a", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def upi_uri(upi_id: str, payee: str, amount, note: str) -> str:
    """Standard UPI deep link understood by GPay, PhonePe, Paytm, BHIM and bank apps."""
    params = {"pa": upi_id, "pn": payee[:40], "am": f"{amount:.2f}", "cu": "INR", "tn": note[:50]}
    return "upi://pay?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def ticket_payload(ticket_code: str) -> str:
    """A staff member can scan this with any phone camera; it opens the check-in page."""
    return current_app.config["BASE_URL"] + url_for("staff.checkin", code=ticket_code)
