"""PDF documents generated on demand (never stored): receipt/ticket, certificate, table reports."""
import datetime as dt
import io

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from webapp.services import qr
from webapp.util import fmt_time, now

NAVY = (20, 38, 74)
BLUE = (47, 85, 151)
GOLD = (190, 140, 0)
MUTED = (94, 107, 133)
NEXT = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
METHOD = {"UPI_QR": "UPI (direct)", "GATEWAY": "Online (UPI / Net banking)", "CASH": "Cash at desk", "FREE": "Free"}


def _t(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("₹", "Rs.").replace("–", "-").replace("—", "-").encode(
        "latin-1", "replace").decode("latin-1")


def _date(v):
    return v.strftime("%d %b %Y") if isinstance(v, (dt.date, dt.datetime)) else _t(v)


def _bytes(pdf) -> bytes:
    return bytes(pdf.output())


def receipt(r: dict, site: dict, team: list[dict]) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    w = pdf.w
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, w, 34, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(15, 9)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 9, _t(site["symposium_name"]), **NEXT)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _t(f"{site['host_institution']}, {site['college_name']}"), **NEXT)

    paid = r["payment_status"] == "SUCCESS"
    pdf.set_text_color(*NAVY)
    pdf.set_xy(15, 44)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "REGISTRATION RECEIPT & ENTRY TICKET" if paid else "REGISTRATION SLIP", **NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f"Generated {now().strftime('%d %b %Y, %I:%M %p')}", **NEXT)

    if r["status"] == "CONFIRMED":
        pdf.image(io.BytesIO(qr.png(qr.ticket_payload(r["ticket_code"]), box=6)), x=w - 60, y=42, w=45)
        pdf.set_xy(w - 60, 88)
        pdf.set_font("Courier", "B", 10)
        pdf.set_text_color(*NAVY)
        pdf.cell(45, 5, _t(r["ticket_code"]), align="C")

    rows = [("Registration ID", f"REG-{r['reg_id']:05d}"), ("Participant", r["full_name"]), ("E-mail", r["email"]),
            ("Phone", r["phone"] or "-"), ("College", r["college_name"] or "-"), ("Event", r["event_name"]),
            ("Date & time", f"{_date(r['event_date'])}, {fmt_time(r['start_time'])} - {fmt_time(r['end_time'])}"),
            ("Venue", r["venue_name"] or "Online")]
    if r["team_name"]:
        rows.append(("Team", f"{r['team_name']} ({r['team_size']} members)"))
    rows += [("Amount", f"Rs. {r['amount'] or 0:.2f}"), ("Payment method", METHOD.get(r["payment_method"], "-")),
             ("Payment reference", r["utr"] or r["gateway_payment_id"] or "-"),
             ("Status", r["status"])]
    pdf.set_y(62)
    for i, (k, v) in enumerate(rows):
        pdf.set_fill_color(*((241, 244, 250) if i % 2 == 0 else (255, 255, 255)))
        pdf.set_x(15)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(42, 8, _t(k), fill=True)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*NAVY)
        pdf.cell(w - 125 if r["status"] == "CONFIRMED" and pdf.get_y() < 100 else w - 72, 8, _t(v)[:70], fill=True, **NEXT)
    if team:
        pdf.ln(3)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Team members", **NEXT)
        pdf.set_font("Helvetica", "", 9.5)
        for m in [{"member_name": r["full_name"] + " (leader)"}] + team:
            pdf.set_x(18)
            pdf.cell(0, 6, _t(f"- {m['member_name']}"), **NEXT)

    color = (21, 128, 61) if paid else (180, 83, 9)
    stamp = "PAID" if paid else ("REFUNDED" if r["payment_status"] == "REFUNDED" else "PAYMENT PENDING")
    pdf.ln(6)
    pdf.set_draw_color(*color)
    pdf.set_text_color(*color)
    pdf.set_line_width(0.8)
    pdf.set_font("Helvetica", "B", 14)
    sw = pdf.get_string_width(stamp) + 12
    pdf.set_x(w - sw - 15)
    pdf.cell(sw, 11, stamp, border=1, align="C", **NEXT)

    pdf.ln(8)
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_x(15)
    msg = ("Show the QR code at the venue entrance for check-in. The QR code is unique to you - do not share it."
           if r["status"] == "CONFIRMED" else "This is not an entry ticket yet. Complete the payment to get your QR ticket.")
    pdf.multi_cell(w - 30, 4.5, _t(msg + f"\nQueries: {site.get('contact_email', '')} {site.get('contact_phone', '')}\n"
                                        "This is a computer-generated document."))
    return _bytes(pdf)


def certificate(r: dict, site: dict, code: str, verify_url: str) -> bytes:
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w, h = pdf.w, pdf.h
    pos = r.get("result_position")
    accent = GOLD if pos else BLUE
    pdf.set_draw_color(*accent)
    pdf.set_line_width(2.5)
    pdf.rect(8, 8, w - 16, h - 16)
    pdf.set_line_width(0.6)
    pdf.rect(13, 13, w - 26, h - 26)
    pdf.set_text_color(*NAVY)
    pdf.set_y(26)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 7, _t(site["college_name"]), align="C", **NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _t(site["host_institution"]), align="C", **NEXT)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*accent)
    pdf.cell(0, 16, _t(site["symposium_name"]), align="C", **NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, _t(site["tagline"]), align="C", **NEXT)
    pdf.ln(7)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 12, "CERTIFICATE OF MERIT" if pos else "CERTIFICATE OF PARTICIPATION", align="C", **NEXT)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 13)
    pdf.cell(0, 8, "This is to certify that", align="C", **NEXT)
    pdf.set_font("Times", "BI", 28)
    pdf.set_text_color(*accent)
    pdf.cell(0, 15, _t(r["full_name"]), align="C", **NEXT)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*NAVY)
    if r.get("college_name"):
        pdf.cell(0, 8, _t(f"of {r['college_name']}"), align="C", **NEXT)
    place = {1: "FIRST", 2: "SECOND", 3: "THIRD"}.get(pos)
    line = (f"has secured the {place} PRIZE in \"{r['event_name']}\"" if place
            else f"has successfully participated in \"{r['event_name']}\"")
    line += f" held on {_date(r['event_date'])}."
    pdf.set_x(30)
    pdf.multi_cell(w - 60, 8, _t(line), align="C")
    y = h - 46
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.3)
    for x, label in ((40, "Event Coordinator"), (w / 2 - 30, "Symposium Convenor"), (w - 100, "Head of Department")):
        pdf.line(x, y, x + 60, y)
        pdf.set_xy(x, y + 2)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(60, 6, label, align="C")
    pdf.image(io.BytesIO(qr.png(verify_url, box=4)), x=w - 44, y=h - 44, w=24)
    pdf.set_xy(20, h - 25)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(w - 70, 5, _t(f"Certificate ID: {code}   |   Verify at {verify_url}"))
    return _bytes(pdf)


def table(title: str, subtitle: str, columns: list[str], rows: list, widths=None, landscape=False,
          signature=False) -> bytes:
    pdf = FPDF(orientation="L" if landscape else "P", format="A4")
    pdf.set_auto_page_break(True, 15)
    pdf.set_margins(10, 12, 10)
    cols = list(columns) + (["Signature"] if signature else [])
    usable = pdf.w - 20
    widths = list(widths or [1] * len(columns)) + ([28] if signature else [])
    scale = usable / sum(widths)
    widths = [x * scale for x in widths]

    def header():
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(*BLUE)
        pdf.set_text_color(255, 255, 255)
        for c, cw in zip(cols, widths):
            pdf.cell(cw, 8, _t(c), fill=True)
        pdf.ln()

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _t(title), **NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, _t(f"{subtitle}  |  {len(rows)} record(s)  |  generated {now().strftime('%d %b %Y %I:%M %p')}"), **NEXT)
    pdf.ln(2)
    header()
    rh = 9 if signature else 7
    for i, row in enumerate(rows):
        if pdf.get_y() + rh > pdf.h - 15:
            pdf.add_page()
            header()
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*NAVY)
        pdf.set_fill_color(*((246, 247, 251) if i % 2 == 0 else (255, 255, 255)))
        for v, cw in zip(list(row) + ([""] if signature else []), widths):
            text = _t(v)
            while text and pdf.get_string_width(text) > cw - 2:
                text = text[:-1]
            pdf.cell(cw, rh, text, border="B", fill=True)
        pdf.ln()
    return _bytes(pdf)
