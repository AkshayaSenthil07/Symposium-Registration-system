"""PDF documents: payment receipt, participation / merit certificate, tabular reports."""
import datetime as dt

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from symposium import config

PRIMARY = (79, 70, 229)
DARK = (30, 41, 59)
MUTED = (100, 116, 139)
GOLD = (180, 140, 40)
NEXT = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


def _t(value) -> str:
    """Core PDF fonts are latin-1 only - replace anything else safely."""
    text = "" if value is None else str(value)
    return text.replace("₹", "Rs.").encode("latin-1", "replace").decode("latin-1")


def _fmt_time(value) -> str:
    if isinstance(value, dt.timedelta):              # MySQL TIME -> timedelta
        minutes = int(value.total_seconds()) // 60
        return dt.time(minutes // 60, minutes % 60).strftime("%I:%M %p")
    return str(value)


def _fmt_date(value) -> str:
    return value.strftime("%d %b %Y") if isinstance(value, (dt.date, dt.datetime)) else str(value)


# ---------------------------------------------------------------- receipt
def receipt(reg: dict, settings: dict) -> str:
    pdf = FPDF(format=(148, 210))                 # A5
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w = pdf.w

    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, w, 34, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 8)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, _t(settings.get("symposium_name")), **NEXT)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _t(settings.get("tagline")), **NEXT)
    pdf.set_x(10)
    pdf.cell(0, 5, _t(settings.get("host_institution")), **NEXT)

    pdf.set_text_color(*DARK)
    pdf.set_xy(10, 42)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "REGISTRATION RECEIPT", **NEXT)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, f"Generated on {dt.datetime.now().strftime('%d %b %Y, %I:%M %p')}", **NEXT)
    pdf.ln(4)

    paid = reg.get("payment_status") == "SUCCESS"
    rows = [
        ("Registration ID", f"REG-{reg['reg_id']:05d}"),
        ("Participant", reg["full_name"]),
        ("E-mail", reg["email"]),
        ("College", reg.get("college_name") or "-"),
        ("Event", reg["event_name"]),
        ("Category", reg.get("category_name")),
        ("Date & Time", f"{_fmt_date(reg['event_date'])}, {_fmt_time(reg['start_time'])} - "
                        f"{_fmt_time(reg['end_time'])}"),
        ("Venue", reg.get("venue_name") or "Online"),
        ("Team", reg.get("team_name") or "-"),
        ("Payment Method", {"CASH": "Cash at registration desk", "NET_BANKING": "Net Banking",
                            "CARD": "Debit / Credit Card"}.get(reg.get("payment_method"),
                                                               reg.get("payment_method") or "-")),
        ("Transaction Ref", reg.get("transaction_ref") or "-"),
        ("Amount", f"Rs. {reg.get('amount') or 0:.2f}"),
        ("Registration Status", reg["status"]),
    ]
    for i, (label, value) in enumerate(rows):
        pdf.set_fill_color(*((241, 245, 249) if i % 2 == 0 else (255, 255, 255)))
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(42, 7.5, _t(label), fill=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*DARK)
        pdf.cell(w - 62, 7.5, _t(value), fill=True, **NEXT)

    # status stamp
    stamp_color = (22, 163, 74) if paid else (217, 119, 6)
    stamp = "PAID" if paid else ("REFUNDED" if reg.get("payment_status") == "REFUNDED"
                                 else "PAYMENT PENDING")
    pdf.set_draw_color(*stamp_color)
    pdf.set_text_color(*stamp_color)
    pdf.set_line_width(0.8)
    pdf.set_font("Helvetica", "B", 13)
    sw = pdf.get_string_width(stamp) + 10
    pdf.set_xy(w - sw - 10, pdf.get_y() + 6)
    pdf.cell(sw, 10, stamp, border=1, align="C")

    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_xy(10, pdf.h - 22)
    note = ("Please show this receipt (printed or on your phone) at the registration desk."
            if paid else "Pay the fee at the registration desk to confirm your seat.")
    pdf.multi_cell(w - 20, 4, _t(f"{note}\nFor queries: {settings.get('contact_email', '')}  "
                                 f"{settings.get('contact_phone', '')}\n"
                                 "This is a computer generated receipt and needs no signature."),
                   align="C")
    path = config.export_path(f"Receipt_REG{reg['reg_id']:05d}.pdf")
    pdf.output(path)
    return path


# ---------------------------------------------------------------- certificate
def certificate(reg: dict, settings: dict, position: int | None = None) -> str:
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w, h = pdf.w, pdf.h
    accent = GOLD if position else PRIMARY

    pdf.set_draw_color(*accent)
    pdf.set_line_width(2.5)
    pdf.rect(8, 8, w - 16, h - 16)
    pdf.set_line_width(0.6)
    pdf.rect(13, 13, w - 26, h - 26)
    pdf.set_fill_color(*accent)
    for x, y in ((13, 13), (w - 33, 13), (13, h - 33), (w - 33, h - 33)):
        pdf.rect(x, y, 20, 20, "F")

    pdf.set_text_color(*DARK)
    pdf.set_y(30)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _t(settings.get("host_institution")), align="C", **NEXT)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*accent)
    pdf.cell(0, 16, _t(settings.get("symposium_name")), align="C", **NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, _t(settings.get("tagline")), align="C", **NEXT)
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*DARK)
    title = "CERTIFICATE OF MERIT" if position else "CERTIFICATE OF PARTICIPATION"
    pdf.cell(0, 12, title, align="C", **NEXT)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 13)
    pdf.cell(0, 8, "This is to certify that", align="C", **NEXT)
    pdf.set_font("Times", "BI", 28)
    pdf.set_text_color(*accent)
    pdf.cell(0, 16, _t(reg["full_name"]), align="C", **NEXT)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*DARK)
    college = reg.get("college_name") or ""
    pdf.cell(0, 8, _t(f"of {college}") if college else "", align="C", **NEXT)

    ordinal = {1: "FIRST", 2: "SECOND", 3: "THIRD"}
    if position:
        line = (f"has secured the {ordinal[position]} PRIZE in \"{reg['event_name']}\" "
                f"held on {_fmt_date(reg['event_date'])}.")
    else:
        line = f"has successfully participated in \"{reg['event_name']}\" held on {_fmt_date(reg['event_date'])}."
    pdf.set_x(30)
    pdf.multi_cell(w - 60, 8, _t(line), align="C")

    y = h - 45
    pdf.set_draw_color(*DARK)
    pdf.set_line_width(0.3)
    for x, label in ((45, "Event Coordinator"), (w / 2 - 30, "Symposium Convenor"), (w - 105, "Head of Department")):
        pdf.line(x, y, x + 60, y)
        pdf.set_xy(x, y + 2)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(60, 6, label, align="C")
    pdf.set_xy(0, h - 26)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(w, 5, f"Certificate ID: CERT-{reg['event_id']:03d}-{reg['reg_id']:05d}", align="C")

    kind = "Merit" if position else "Participation"
    path = config.export_path(f"Certificate_{kind}_REG{reg['reg_id']:05d}.pdf")
    pdf.output(path)
    return path


# ---------------------------------------------------------------- tables
def table_report(title: str, subtitle: str, columns: list[str], rows: list,
                 filename: str, widths: list[float] | None = None, landscape: bool = False,
                 signature_column: bool = False) -> str:
    pdf = FPDF(orientation="L" if landscape else "P", format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(10, 12, 10)
    cols = list(columns) + (["Signature"] if signature_column else [])
    usable = pdf.w - 20
    if widths is None:
        widths = [usable / len(cols)] * len(cols)
    else:
        widths = list(widths) + ([28] if signature_column else [])
        scale = usable / sum(widths)
        widths = [x * scale for x in widths]

    def header():
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(*PRIMARY)
        pdf.set_text_color(255, 255, 255)
        for c, cw in zip(cols, widths):
            pdf.cell(cw, 8, _t(c), border=0, fill=True)
        pdf.ln()

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 8, _t(title), **NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, _t(f"{subtitle}   |   Generated {dt.datetime.now().strftime('%d %b %Y %I:%M %p')}"
                      f"   |   {len(rows)} record(s)"), **NEXT)
    pdf.ln(3)
    header()
    row_h = 9 if signature_column else 7
    pdf.set_font("Helvetica", "", 8.5)
    for i, row in enumerate(rows):
        if pdf.get_y() + row_h > pdf.h - 15:
            pdf.add_page()
            header()
            pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*DARK)
        pdf.set_fill_color(*((248, 250, 252) if i % 2 == 0 else (255, 255, 255)))
        values = list(row) + ([""] if signature_column else [])
        for v, cw in zip(values, widths):
            text = _t(v)
            while text and pdf.get_string_width(text) > cw - 2:
                text = text[:-1]
            pdf.cell(cw, row_h, text, border="B", fill=True)
        pdf.ln()
    path = config.export_path(filename)
    pdf.output(path)
    return path
