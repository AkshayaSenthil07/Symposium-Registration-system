"""Small shared helpers: Indian time, formatting."""
import datetime as dt
import decimal

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now() -> dt.datetime:
    """Naive IST datetime - matches the MySQL session time zone (+05:30)."""
    return dt.datetime.now(IST).replace(tzinfo=None)


def today() -> dt.date:
    return now().date()


def fmt_date(value) -> str:
    if isinstance(value, dt.datetime):
        return value.strftime("%d %b %Y, %I:%M %p")
    if isinstance(value, dt.date):
        return value.strftime("%a, %d %b %Y")
    return value or ""


def fmt_time(value) -> str:
    if isinstance(value, dt.timedelta):
        minutes = int(value.total_seconds()) // 60
        return dt.time(minutes // 60, minutes % 60).strftime("%I:%M %p").lstrip("0")
    if isinstance(value, dt.time):
        return value.strftime("%I:%M %p").lstrip("0")
    return value or ""


def hhmm(value) -> str:
    if isinstance(value, dt.timedelta):
        minutes = int(value.total_seconds()) // 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return str(value or "")[:5]


def money(value) -> str:
    if value is None:
        return "₹0"
    value = decimal.Decimal(value)
    return f"₹{value:,.0f}" if value == value.to_integral() else f"₹{value:,.2f}"


def as_datetime_local(value) -> str:
    """For <input type="datetime-local">."""
    return value.strftime("%Y-%m-%dT%H:%M") if isinstance(value, dt.datetime) else ""


def parse_datetime_local(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M") if value else None
    except ValueError:
        return None
