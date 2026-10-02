"""Reusable UI building blocks."""
import calendar
import datetime as dt
import decimal
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from symposium.ui import theme as T

# ---------------------------------------------------------------- formatting helpers


def fmt(value, key: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, dt.datetime):
        return value.strftime("%d %b %Y, %I:%M %p")
    if isinstance(value, dt.date):
        return value.strftime("%d %b %Y")
    if isinstance(value, dt.timedelta):
        return fmt_time(value)
    if isinstance(value, (decimal.Decimal, float)):
        return f"{value:,.2f}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def fmt_time(value) -> str:
    if isinstance(value, dt.timedelta):
        minutes = int(value.total_seconds()) // 60
        return dt.time(minutes // 60, minutes % 60).strftime("%I:%M %p").lstrip("0")
    return str(value)


def time_str(value) -> str:
    """timedelta -> 'HH:MM' (for form fields)."""
    if isinstance(value, dt.timedelta):
        minutes = int(value.total_seconds()) // 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return str(value or "")


def money(value) -> str:
    return f"₹{value:,.0f}" if value else "Free"


# ---------------------------------------------------------------- simple widgets
def label(master, text, size=13, weight="normal", color=T.TEXT, **kw):
    return ctk.CTkLabel(master, text=text, font=T.f(size, weight), text_color=color, **kw)


def button(master, text, command=None, kind="primary", width=120, **kw):
    styles = {
        "primary": dict(fg_color=T.PRIMARY, hover_color=T.PRIMARY_HOVER, text_color="#FFFFFF"),
        "secondary": dict(fg_color=T.SURFACE_2, hover_color=T.BORDER, text_color=T.TEXT,
                          border_width=1, border_color=T.BORDER),
        "danger": dict(fg_color=T.DANGER, hover_color=T.DANGER_HOVER, text_color="#FFFFFF"),
        "success": dict(fg_color=T.SUCCESS, hover_color="#15803D", text_color="#FFFFFF"),
        "ghost": dict(fg_color="transparent", hover_color=T.SURFACE_2, text_color=T.PRIMARY),
    }
    kw.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, width=width, corner_radius=8,
                         font=T.f(12, "bold"), **{**styles[kind], **kw})


class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", T.SURFACE)
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", T.BORDER)
        super().__init__(master, **kw)


class PageHeader(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = ""):
        super().__init__(master, fg_color="transparent")
        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side="left", anchor="w")
        label(text, title, 24, "bold").pack(anchor="w")
        self.sub = label(text, subtitle, 13, color=T.MUTED)
        self.sub.pack(anchor="w")
        self.actions = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self.actions.pack(side="right", anchor="e")


class StatCard(Card):
    def __init__(self, master, title: str, value: str, note: str = "", color: str = T.PRIMARY[0]):
        super().__init__(master)
        bar = ctk.CTkFrame(self, width=5, height=10, fg_color=color, corner_radius=3)
        bar.pack(side="left", fill="y", padx=(12, 0), pady=16)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=14, pady=14)
        label(body, title.upper(), 10, "bold", T.MUTED).pack(anchor="w")
        self.value = label(body, value, 26, "bold")
        self.value.pack(anchor="w")
        self.note = label(body, note, 11, color=T.MUTED)
        self.note.pack(anchor="w")


class Badge(ctk.CTkLabel):
    COLORS = {
        "OPEN": T.SUCCESS, "CONFIRMED": T.SUCCESS, "SUCCESS": T.SUCCESS,
        "PENDING": T.WARNING, "CLOSED": T.WARNING,
        "CANCELLED": T.DANGER, "FAILED": T.DANGER, "REFUNDED": T.DANGER,
        "COMPLETED": T.INFO,
    }

    def __init__(self, master, text: str, color: str | None = None):
        color = color or self.COLORS.get(text.upper(), T.PRIMARY[0])
        super().__init__(master, text=f"  {text}  ", font=T.f(10, "bold"), fg_color=color,
                         text_color="#FFFFFF", corner_radius=10, height=22)


class SearchBox(ctk.CTkEntry):
    """Entry that calls `on_change` shortly after the user stops typing."""

    def __init__(self, master, on_change, placeholder="Search…", width=260, delay=300):
        super().__init__(master, placeholder_text=placeholder, width=width, height=36,
                         corner_radius=8, font=T.f(12))
        self._job = None
        self._delay = delay
        self._on_change = on_change
        self.bind("<KeyRelease>", self._schedule)

    def _schedule(self, _event=None):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(self._delay, lambda: self._on_change(self.get().strip()))


class PasswordEntry(ctk.CTkFrame):
    def __init__(self, master, placeholder="Password", width=320, height=42, **kw):
        super().__init__(master, fg_color="transparent")
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder, show="•", width=width - 46,
                                  height=height, corner_radius=8, font=T.f(13), **kw)
        self.entry.pack(side="left", fill="x", expand=True)
        self._shown = False
        self.toggle = ctk.CTkButton(self, text="Show", width=40, height=height, corner_radius=8,
                                    fg_color=T.SURFACE_2, hover_color=T.BORDER, text_color=T.MUTED,
                                    font=T.f(10, "bold"), command=self._toggle)
        self.toggle.pack(side="left", padx=(6, 0))

    def _toggle(self):
        self._shown = not self._shown
        self.entry.configure(show="" if self._shown else "•")
        self.toggle.configure(text="Hide" if self._shown else "Show")

    def get(self):
        return self.entry.get()

    def delete(self, *a):
        self.entry.delete(*a)

    def bind(self, *a, **kw):
        return self.entry.bind(*a, **kw)


# ---------------------------------------------------------------- toast
class Toast:
    @staticmethod
    def show(widget, message: str, kind: str = "success", ms: int = 2800):
        root = widget.winfo_toplevel()
        color = {"success": T.SUCCESS, "error": T.DANGER, "info": T.PRIMARY[1],
                 "warning": T.WARNING}[kind]
        mark = {"success": "✔", "error": "✖", "info": "ℹ", "warning": "!"}[kind]
        frame = ctk.CTkFrame(root, fg_color=color, corner_radius=10)
        ctk.CTkLabel(frame, text=f"{mark}   {message}", text_color="#FFFFFF",
                     font=T.f(13, "bold")).pack(padx=18, pady=10)
        frame.place(relx=0.5, rely=0.97, anchor="s")
        frame.lift()
        root.after(ms, frame.destroy)


def error(widget, message: str, title: str = "Something went wrong"):
    messagebox.showerror(title, message, parent=widget.winfo_toplevel())


def confirm(widget, message: str, title: str = "Please confirm") -> bool:
    return messagebox.askyesno(title, message, parent=widget.winfo_toplevel())


# ---------------------------------------------------------------- data table
class DataTable(ctk.CTkFrame):
    """Treeview wrapper: sortable columns, zebra rows, status colouring, empty state.

    columns: list of (key, heading, width, anchor)
    """

    TAGS = {"ok": T.SUCCESS, "warn": T.WARNING, "bad": T.DANGER, "info": T.INFO}

    def __init__(self, master, columns, on_double_click=None, selectmode="browse",
                 tag_fn=None, formatters=None, empty_text="No records found", hscroll=False):
        super().__init__(master, fg_color=T.SURFACE, corner_radius=12, border_width=1,
                         border_color=T.BORDER)
        self.columns = columns
        self.tag_fn = tag_fn
        self.formatters = formatters or {}
        self._rows: dict[str, dict] = {}
        self._sort_state: dict[str, bool] = {}

        keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=keys, show="headings", style="Sym.Treeview",
                                 selectmode=selectmode)
        for key, heading, width, anchor in columns:
            self.tree.heading(key, text=heading, anchor=anchor,
                              command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=40, anchor=anchor, stretch=not hscroll)
        self.hscroll = hscroll
        sb = ctk.CTkScrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)
        if hscroll:
            hsb = ctk.CTkScrollbar(self, orientation="horizontal", command=self.tree.xview)
            self.tree.configure(xscrollcommand=hsb.set)
            hsb.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))
        self.empty = ctk.CTkLabel(self, text=empty_text, font=T.f(13), text_color=T.MUTED)
        if on_double_click:
            self.tree.bind("<Double-1>", lambda e: self.selected() and on_double_click(self.selected()))
        self.restyle()

    def restyle(self):
        self.tree.tag_configure("odd", background=T.pick(T.SURFACE_2))
        self.tree.tag_configure("even", background=T.pick(T.SURFACE))
        for tag, color in self.TAGS.items():
            self.tree.tag_configure(tag, foreground=color)

    def set_rows(self, rows: list[dict]):
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for i, row in enumerate(rows):
            values = []
            for key, *_ in self.columns:
                fn = self.formatters.get(key)
                values.append(fn(row) if fn else fmt(row.get(key), key))
            tags = ["odd" if i % 2 else "even"]
            if self.tag_fn:
                t = self.tag_fn(row)
                if t:
                    tags.append(t)
            iid = self.tree.insert("", "end", values=values, tags=tags)
            self._rows[iid] = row
        if self.hscroll:
            self._autosize(rows)
        if rows:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _autosize(self, rows):
        """Fit column widths to their content (used by dynamic result tables)."""
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        sample = rows[:200]
        for key, heading, *_ in self.columns:
            longest = max([len(heading)] + [len(fmt(r.get(key))) for r in sample])
            self.tree.column(key, width=int(min(max(longest * 8 + 24, 70), 360) * scale))

    def selected(self) -> dict | None:
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def selected_all(self) -> list[dict]:
        return [self._rows[i] for i in self.tree.selection() if i in self._rows]

    def rows(self) -> list[dict]:
        return [self._rows[i] for i in self.tree.get_children()]

    def sort_by(self, key):
        reverse = self._sort_state.get(key, False)
        items = list(self._rows.items())

        def sort_key(item):
            v = item[1].get(key)
            if v is None:
                return (1, "")
            if isinstance(v, (int, float, decimal.Decimal)):
                return (0, float(v))
            if isinstance(v, (dt.date, dt.datetime, dt.timedelta)):
                return (0, str(v))
            return (0, str(v).lower())

        items.sort(key=sort_key, reverse=reverse)
        for index, (iid, _) in enumerate(items):
            self.tree.move(iid, "", index)
            tags = [t for t in self.tree.item(iid, "tags") if t not in ("odd", "even")]
            self.tree.item(iid, tags=["odd" if index % 2 else "even", *tags])
        self._sort_state[key] = not reverse
        for k, heading, *_ in self.columns:
            arrow = (" ▼" if reverse else " ▲") if k == key else ""
            self.tree.heading(k, text=heading + arrow)


# ---------------------------------------------------------------- date picker
class DatePicker(ctk.CTkToplevel):
    def __init__(self, anchor_widget, initial: dt.date | None, on_pick):
        super().__init__(anchor_widget)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(fg_color=T.SURFACE)
        self.on_pick = on_pick
        self.current = (initial or dt.date.today()).replace(day=1)
        self.selected = initial
        frame = ctk.CTkFrame(self, fg_color=T.SURFACE, border_width=1, border_color=T.BORDER,
                             corner_radius=10)
        frame.pack(fill="both", expand=True)
        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkButton(nav, text="‹", width=30, command=lambda: self._move(-1), fg_color=T.SURFACE_2,
                      text_color=T.TEXT, hover_color=T.BORDER).pack(side="left")
        self.title_lbl = label(nav, "", 13, "bold")
        self.title_lbl.pack(side="left", expand=True)
        ctk.CTkButton(nav, text="›", width=30, command=lambda: self._move(1), fg_color=T.SURFACE_2,
                      text_color=T.TEXT, hover_color=T.BORDER).pack(side="right")
        self.grid_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.grid_frame.pack(padx=8, pady=(0, 8))
        self._render()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 4
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.after(50, self._grab)
        self.bind("<Escape>", lambda e: self.destroy())

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass
        self.bind("<Button-1>", self._click_outside)

    def _click_outside(self, event):
        x, y = event.x_root, event.y_root
        if not (self.winfo_rootx() <= x <= self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y <= self.winfo_rooty() + self.winfo_height()):
            self.destroy()

    def _move(self, delta):
        month = self.current.month - 1 + delta
        self.current = self.current.replace(year=self.current.year + month // 12, month=month % 12 + 1)
        self._render()

    def _render(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.title_lbl.configure(text=self.current.strftime("%B %Y"))
        for c, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            label(self.grid_frame, name, 10, "bold", T.MUTED).grid(row=0, column=c, padx=1, pady=2)
        today = dt.date.today()
        for r, week in enumerate(calendar.Calendar().monthdatescalendar(self.current.year,
                                                                         self.current.month), start=1):
            for c, day in enumerate(week):
                in_month = day.month == self.current.month
                is_sel = day == self.selected
                ctk.CTkButton(
                    self.grid_frame, text=str(day.day), width=34, height=30, corner_radius=6,
                    font=T.f(11, "bold" if day == today else "normal"),
                    fg_color=T.PRIMARY if is_sel else "transparent",
                    hover_color=T.PRIMARY_SOFT,
                    text_color="#FFFFFF" if is_sel else (T.TEXT if in_month else T.MUTED),
                    border_width=1 if day == today and not is_sel else 0, border_color=T.PRIMARY,
                    command=lambda d=day: self._pick(d)).grid(row=r, column=c, padx=1, pady=1)

    def _pick(self, day):
        self.on_pick(day)
        self.destroy()


class DateEntry(ctk.CTkFrame):
    def __init__(self, master, width=200):
        super().__init__(master, fg_color="transparent")
        self.entry = ctk.CTkEntry(self, placeholder_text="YYYY-MM-DD", width=width - 44, height=36,
                                  corner_radius=8, font=T.f(12))
        self.entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(self, text=T.ICONS["calendar"] if T.icon_available(self) else "📅", width=38,
                      height=36, corner_radius=8, font=(T.ICON_FONT, 13), fg_color=T.SURFACE_2,
                      hover_color=T.BORDER, text_color=T.TEXT, command=self._open).pack(side="left", padx=(6, 0))

    def _open(self):
        DatePicker(self.entry, self.get_date(), self.set)

    def get(self) -> str:
        return self.entry.get().strip()

    def get_date(self) -> dt.date | None:
        try:
            return dt.date.fromisoformat(self.get())
        except ValueError:
            return None

    def set(self, value):
        self.entry.delete(0, "end")
        if value:
            self.entry.insert(0, value.isoformat() if isinstance(value, dt.date) else str(value))


# ---------------------------------------------------------------- generic form dialog
TIME_CHOICES = [f"{h:02d}:{m:02d}" for h in range(6, 23) for m in (0, 15, 30, 45)]


class FormDialog(ctk.CTkToplevel):
    """Modal form built from a field spec.

    field: dict(key, label, type=entry|number|decimal|combo|text|date|time|password,
                options=list|dict(label->value), required=True, default=None, width=1|2)
    validate: optional fn(values) -> error message | None
    on_submit: fn(values) -> None  (raise to keep the dialog open and show the error)
    """

    def __init__(self, master, title: str, fields: list[dict], on_submit, validate=None,
                 submit_text="Save", columns: int = 2):
        super().__init__(master)
        self.withdraw()
        self.title(title)
        self.configure(fg_color=T.BG)
        self.resizable(False, False)
        self.fields = fields
        self.on_submit = on_submit
        self.validate = validate
        self.widgets = {}

        card = Card(self)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        label(card, title, 18, "bold").pack(anchor="w", padx=20, pady=(18, 2))
        label(card, "Fields marked * are required", 11, color=T.MUTED).pack(anchor="w", padx=20)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        for c in range(columns):
            body.grid_columnconfigure(c, weight=1, uniform="col")

        r = c = 0
        for fd in fields:
            span = min(fd.get("width", 1), columns)
            if c + span > columns:
                r, c = r + 1, 0
            cell = ctk.CTkFrame(body, fg_color="transparent")
            cell.grid(row=r, column=c, columnspan=span, sticky="ew", padx=6, pady=6)
            star = " *" if fd.get("required", True) else ""
            label(cell, fd["label"] + star, 12, "bold", T.MUTED).pack(anchor="w")
            w = self._make(cell, fd, 260 * span)
            w.pack(fill="x", pady=(3, 0))
            self.widgets[fd["key"]] = w
            c += span
            if c >= columns:
                r, c = r + 1, 0

        self.err = label(card, "", 12, color=T.DANGER, wraplength=520, justify="left")
        self.err.pack(anchor="w", padx=26)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(6, 18))
        button(btns, submit_text, self._submit, width=130).pack(side="right")
        button(btns, "Cancel", self.destroy, kind="secondary", width=100).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self._submit() if not isinstance(e.widget, tk.Text) else None)
        self.bind("<Escape>", lambda e: self.destroy())

        self.transient(master.winfo_toplevel())
        self.update_idletasks()
        top = master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + max(20, (top.winfo_height() - self.winfo_reqheight()) // 2)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        self.after(80, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _make(self, parent, fd, width):
        kind = fd.get("type", "entry")
        default = fd.get("default")
        if kind == "combo":
            opts = fd["options"]
            labels = list(opts.keys()) if isinstance(opts, dict) else list(opts)
            w = ctk.CTkComboBox(parent, values=labels, width=width, height=36, corner_radius=8,
                                font=T.f(12), state="normal" if fd.get("editable") else "readonly")
            if default is not None:
                if isinstance(opts, dict):
                    default = next((k for k, v in opts.items() if v == default), default)
                w.set(str(default))
            else:
                w.set("")
            return w
        if kind == "time":
            w = ctk.CTkComboBox(parent, values=TIME_CHOICES, width=width, height=36, corner_radius=8,
                                font=T.f(12))
            w.set(default or "")
            return w
        if kind == "date":
            w = DateEntry(parent, width=width)
            w.set(default)
            return w
        if kind == "text":
            w = ctk.CTkTextbox(parent, width=width, height=80, corner_radius=8, font=T.f(12),
                               border_width=2, border_color=T.BORDER)
            if default:
                w.insert("1.0", default)
            return w
        if kind == "password":
            w = PasswordEntry(parent, width=width, height=36)
            return w
        w = ctk.CTkEntry(parent, width=width, height=36, corner_radius=8, font=T.f(12),
                         placeholder_text=fd.get("placeholder", ""))
        if default not in (None, ""):
            w.insert(0, str(default))
        return w

    def values(self) -> dict:
        out = {}
        for fd in self.fields:
            w = self.widgets[fd["key"]]
            kind = fd.get("type", "entry")
            raw = w.get("1.0", "end").strip() if kind == "text" else w.get().strip()
            if kind == "combo" and isinstance(fd["options"], dict):
                raw = fd["options"].get(raw, None if not raw else raw)
            out[fd["key"]] = raw
        return out

    def _clean(self, values: dict) -> dict:
        clean = {}
        for fd in self.fields:
            key, kind, v = fd["key"], fd.get("type", "entry"), values[fd["key"]]
            if v in ("", None):
                if fd.get("required", True):
                    raise ValueError(f"{fd['label']} is required.")
                clean[key] = None
                continue
            if kind == "number":
                try:
                    v = int(v)
                except ValueError:
                    raise ValueError(f"{fd['label']} must be a whole number.") from None
                if v < fd.get("min", 0):
                    raise ValueError(f"{fd['label']} must be at least {fd.get('min', 0)}.")
            elif kind == "decimal":
                try:
                    v = decimal.Decimal(v)
                except decimal.InvalidOperation:
                    raise ValueError(f"{fd['label']} must be a number.") from None
                if v < 0:
                    raise ValueError(f"{fd['label']} cannot be negative.")
            elif kind == "date":
                try:
                    v = dt.date.fromisoformat(v)
                except ValueError:
                    raise ValueError(f"{fd['label']} must be a date like 2026-10-15.") from None
            elif kind == "time":
                try:
                    v = dt.datetime.strptime(v, "%H:%M").strftime("%H:%M:00")
                except ValueError:
                    raise ValueError(f"{fd['label']} must be a time like 09:30.") from None
            clean[key] = v
        return clean

    def _submit(self):
        try:
            values = self._clean(self.values())
            if self.validate:
                problem = self.validate(values)
                if problem:
                    raise ValueError(problem)
            self.on_submit(values)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.err.configure(text=f"⚠  {exc}")
            return
        self.destroy()
