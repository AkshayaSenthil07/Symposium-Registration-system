"""Admin console pages."""
import datetime as dt
import time
from tkinter import messagebox

import customtkinter as ctk

from symposium import config, db
from symposium.security import password_problems, valid_email, valid_phone
from symposium.services import auth, catalog, pdf, registrations, reports
from symposium.ui import charts
from symposium.ui import theme as T
from symposium.ui.shell import Page
from symposium.ui.widgets import (Card, DataTable, FormDialog, PageHeader, PasswordEntry, SearchBox,
                                  StatCard, Toast, button, confirm, error, fmt, fmt_time, label,
                                  time_str)

STATUS_TAG = {"OPEN": "ok", "CONFIRMED": "ok", "SUCCESS": "ok", "PENDING": "warn", "CLOSED": "warn",
              "CANCELLED": "bad", "FAILED": "bad", "REFUNDED": "bad", "COMPLETED": "info"}
ALL = "All"
METHOD_LABEL = {"UPI": "UPI", "CARD": "Card", "NET_BANKING": "Net Banking", "CASH": "Cash", "FREE": "Free"}


def toolbar(parent):
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    bar.pack(fill="x", pady=(14, 10))
    return bar


def combo(parent, values, command=None, width=200, state="readonly"):
    c = ctk.CTkComboBox(parent, values=values, width=width, height=36, corner_radius=8, font=T.f(12),
                        state=state, command=command)
    if values:
        c.set(values[0])
    return c


def export_table(page, title, table: DataTable, filename):
    cols = [heading for _, heading, *_ in table.columns]
    rows = [[fmt(r.get(k)) for k, *_ in table.columns] for r in table.rows()]
    if not rows:
        Toast.show(page, "Nothing to export", "warning")
        return
    path = reports.export_csv(filename, cols, rows)
    Toast.show(page, f"Exported {len(rows)} rows → exports/{filename}")
    config.open_file(path)


# =====================================================================================
class DashboardPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll
        self.header = PageHeader(body, "Dashboard", "")
        self.header.pack(fill="x", padx=(0, 8))
        button(self.header.actions, "Refresh", self.refresh, kind="secondary").pack()

        self.cards = ctk.CTkFrame(body, fg_color="transparent")
        self.cards.pack(fill="x", pady=16, padx=(0, 8))
        self.cards.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="c")
        self.stat = {}
        for i, (key, title, color) in enumerate([
                ("participants", "Participants", T.CHART_COLORS[0]),
                ("confirmed", "Confirmed Registrations", T.SUCCESS),
                ("revenue", "Revenue Collected", T.CHART_COLORS[1]),
                ("pending", "Pending Payments", T.WARNING)]):
            card = StatCard(self.cards, title, "–", "", color)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.stat[key] = card

        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", padx=(0, 8))
        row1.grid_columnconfigure(0, weight=3, uniform="r")
        row1.grid_columnconfigure(1, weight=2, uniform="r")
        c1 = self._chart_card(row1, "Registrations by event", "Filled vs. capacity (red = almost full)")
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.bar = charts.ChartCard(c1, 300)
        c2 = self._chart_card(row1, "Revenue by category", "Successful payments only")
        c2.grid(row=0, column=1, sticky="nsew")
        self.donut = charts.ChartCard(c2, 300)

        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=16, padx=(0, 8))
        row2.grid_columnconfigure(0, weight=3, uniform="r")
        row2.grid_columnconfigure(1, weight=2, uniform="r")
        c3 = self._chart_card(row2, "Registration trend", "New registrations per day, last 14 days")
        c3.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.line = charts.ChartCard(c3, 240)
        c4 = self._chart_card(row2, "Upcoming events", "Next on the schedule")
        c4.grid(row=0, column=1, sticky="nsew")
        self.upcoming = ctk.CTkFrame(c4, fg_color="transparent")
        self.upcoming.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _chart_card(self, parent, title, subtitle):
        card = Card(parent)
        label(card, title, 15, "bold").pack(anchor="w", padx=18, pady=(14, 0))
        label(card, subtitle, 11, color=T.MUTED).pack(anchor="w", padx=18, pady=(0, 6))
        return card

    def refresh(self):
        s = reports.dashboard_stats()
        self.header.sub.configure(text=f"{self.app.settings['symposium_name']} at a glance · "
                                       f"{dt.date.today().strftime('%A, %d %B %Y')}")
        self.stat["participants"].value.configure(text=f"{s['participants']:,}")
        self.stat["participants"].note.configure(text=f"from {s['colleges']} colleges")
        self.stat["confirmed"].value.configure(text=f"{s['confirmed']:,}")
        self.stat["confirmed"].note.configure(text=f"+{s['today']} today · {s['events']} events")
        self.stat["revenue"].value.configure(text=f"₹{s['revenue']:,.0f}")
        self.stat["revenue"].note.configure(text=f"₹{s['pending_amount']:,.0f} awaiting cash")
        self.stat["pending"].value.configure(text=str(s["pending"]))
        self.stat["pending"].note.configure(text="registrations to verify")
        self._draw_charts()
        for w in self.upcoming.winfo_children():
            w.destroy()
        events = catalog.list_events(upcoming_only=True)[:6]
        if not events:
            label(self.upcoming, "No upcoming events", 12, color=T.MUTED).pack(pady=20)
        for e in events:
            row = ctk.CTkFrame(self.upcoming, fg_color=T.SURFACE_2, corner_radius=10)
            row.pack(fill="x", pady=3)
            date = ctk.CTkFrame(row, fg_color=T.PRIMARY_SOFT, corner_radius=8, width=48, height=44)
            date.pack(side="left", padx=8, pady=6)
            date.pack_propagate(False)
            label(date, e["event_date"].strftime("%d"), 14, "bold", T.PRIMARY).pack(pady=(3, 0))
            label(date, e["event_date"].strftime("%b").upper(), 9, "bold", T.PRIMARY).pack()
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)
            label(info, e["event_name"], 12, "bold").pack(anchor="w")
            label(info, f"{fmt_time(e['start_time'])} · {e['venue_name'] or 'Online'}", 10,
                  color=T.MUTED).pack(anchor="w")
            label(row, f"{e['registered']}/{e['max_participants']}", 12, "bold", T.MUTED).pack(side="right", padx=12)

    def _draw_charts(self):
        self.bar.draw(charts.registrations_bar(reports.registrations_per_event()))
        self.donut.draw(charts.revenue_donut(reports.revenue_by_category()))
        self.line.draw(charts.daily_line(reports.daily_registrations(14)))

    def on_theme_change(self):
        try:
            self._draw_charts()
        except db.DatabaseError:
            pass


# =====================================================================================
class EventsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Events", "Create, edit and manage symposium events")
        header.pack(fill="x")
        button(header.actions, "+  New Event", self.add, width=140).pack()

        bar = toolbar(self)
        self.search = SearchBox(bar, lambda _: self.refresh(), "Search events or coordinators…")
        self.search.pack(side="left")
        self.cat = combo(bar, [ALL], lambda _: self.refresh(), 170)
        self.cat.pack(side="left", padx=8)
        self.status = ctk.CTkSegmentedButton(bar, values=[ALL, "OPEN", "CLOSED", "COMPLETED", "CANCELLED"],
                                             command=lambda _: self.refresh(), height=36, font=T.f(11))
        self.status.set(ALL)
        self.status.pack(side="left", padx=8)

        self.table = DataTable(self, [
            ("event_id", "ID", 45, "center"), ("event_name", "Event", 200, "w"),
            ("category_name", "Category", 105, "w"), ("event_date", "Date", 100, "w"),
            ("start_time", "Time", 130, "w"), ("venue_name", "Venue", 140, "w"),
            ("registration_fee", "Fee (₹)", 70, "e"), ("registered", "Filled", 70, "center"),
            ("seats_left", "Seats left", 75, "center"), ("revenue", "Revenue (₹)", 95, "e"),
            ("status", "Status", 95, "center")],
            on_double_click=self.edit, tag_fn=lambda r: STATUS_TAG.get(r["status"]),
            formatters={
                "start_time": lambda r: f"{fmt_time(r['start_time'])} – {fmt_time(r['end_time'])}",
                "registered": lambda r: f"{r['registered']}/{r['max_participants']}",
                "venue_name": lambda r: r["venue_name"] or "Online",
                "registration_fee": lambda r: f"{r['registration_fee']:,.0f}" if r["registration_fee"] else "Free",
                "revenue": lambda r: f"{r['revenue']:,.0f}"})
        self.table.pack(fill="both", expand=True)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        button(actions, "Edit", self.edit_selected, kind="secondary", width=90).pack(side="left")
        button(actions, "Open / Close registrations", self.toggle_open, kind="secondary", width=200).pack(side="left", padx=8)
        button(actions, "Mark Completed", lambda: self.set_status("COMPLETED"), kind="secondary", width=140).pack(side="left")
        button(actions, "Cancel Event", lambda: self.set_status("CANCELLED"), kind="secondary", width=120).pack(side="left", padx=8)
        button(actions, "Delete", self.delete, kind="danger", width=90).pack(side="left")
        button(actions, "Export CSV", lambda: export_table(self, "Events", self.table, "events.csv"),
               kind="ghost", width=110).pack(side="right")
        self.count = label(actions, "", 12, color=T.MUTED)
        self.count.pack(side="right", padx=10)

    def refresh(self):
        cats = [ALL] + [c["category_name"] for c in catalog.categories()]
        self.cat.configure(values=cats)
        cat = self.cat.get() if self.cat.get() in cats else ALL
        status = self.status.get()
        rows = catalog.list_events(self.search.get().strip(), None if cat == ALL else cat,
                                   None if status == ALL else status)
        self.table.set_rows(rows)
        self.count.configure(text=f"{len(rows)} event(s)")

    def _fields(self, e: dict | None):
        cats = {c["category_name"]: c["category_id"] for c in catalog.categories()}
        venues = {"— Online / no venue —": None}
        venues.update({f"{v['venue_name']} (cap {v['capacity']})": v["venue_id"] for v in catalog.venues()})
        e = e or {}
        return [
            dict(key="event_name", label="Event name", default=e.get("event_name"), width=2),
            dict(key="category_id", label="Category", type="combo", options=cats, default=e.get("category_id")),
            dict(key="venue_id", label="Venue", type="combo", options=venues, default=e.get("venue_id"),
                 required=False),
            dict(key="event_date", label="Date", type="date", default=e.get("event_date")),
            dict(key="status", label="Status", type="combo",
                 options=["OPEN", "CLOSED", "COMPLETED", "CANCELLED"], default=e.get("status", "OPEN")),
            dict(key="start_time", label="Start time", type="time", default=time_str(e.get("start_time")) or "09:30"),
            dict(key="end_time", label="End time", type="time", default=time_str(e.get("end_time")) or "12:30"),
            dict(key="registration_fee", label="Registration fee (₹)", type="decimal",
                 default=e.get("registration_fee", 0)),
            dict(key="max_participants", label="Maximum participants", type="number", min=1,
                 default=e.get("max_participants", 50)),
            dict(key="coordinator_name", label="Coordinator name", default=e.get("coordinator_name"),
                 required=False),
            dict(key="coordinator_phone", label="Coordinator phone", default=e.get("coordinator_phone"),
                 required=False),
            dict(key="description", label="Description", type="text", default=e.get("description"),
                 required=False, width=3),
        ]

    def _validate(self, is_new):
        venue_caps = {v["venue_id"]: v["capacity"] for v in catalog.venues()}

        def check(v):
            if v["end_time"] <= v["start_time"]:
                return "End time must be after the start time."
            if is_new and v["event_date"] < dt.date.today():
                return "Event date cannot be in the past."
            if v["coordinator_phone"] and not valid_phone(v["coordinator_phone"]):
                return "Coordinator phone must be 10 digits."
            cap = venue_caps.get(v["venue_id"])
            if cap and v["max_participants"] > cap:
                return f"Maximum participants exceeds the venue capacity ({cap})."
            return None
        return check

    def add(self):
        def submit(v):
            catalog.save_event(v, self.user.user_id)
            Toast.show(self, f"Event '{v['event_name']}' created")
            self.refresh()
        FormDialog(self, "New Event", self._fields(None), submit, self._validate(True), "Create event",
                   columns=3)

    def edit(self, row):
        e = catalog.get_event(row["event_id"])

        def submit(v):
            catalog.save_event(v, self.user.user_id, row["event_id"])
            Toast.show(self, "Event updated")
            self.refresh()
        FormDialog(self, f"Edit · {e['event_name']}", self._fields(e), submit, self._validate(False),
                   columns=3)

    def _selected(self):
        row = self.table.selected()
        if not row:
            Toast.show(self, "Select an event first", "warning")
        return row

    def edit_selected(self):
        row = self._selected()
        if row:
            self.edit(row)

    def toggle_open(self):
        row = self._selected()
        if not row:
            return
        new = "CLOSED" if row["status"] == "OPEN" else "OPEN"
        ok, _ = self.safe(catalog.set_event_status, row["event_id"], new, self.user.user_id,
                          success=f"Registrations {'closed' if new == 'CLOSED' else 'opened'}")
        if ok:
            self.refresh()

    def set_status(self, status):
        row = self._selected()
        if row and confirm(self, f"Mark '{row['event_name']}' as {status}?"):
            if self.safe(catalog.set_event_status, row["event_id"], status, self.user.user_id,
                         success=f"Event marked {status.lower()}")[0]:
                self.refresh()

    def delete(self):
        row = self._selected()
        if not row:
            return
        msg = f"Delete '{row['event_name']}'?"
        if row["registered"]:
            msg += f"\n\n⚠ {row['registered']} registration(s) and their payments will also be deleted (CASCADE)."
        if confirm(self, msg, "Delete event"):
            if self.safe(catalog.delete_event, row["event_id"], success="Event deleted")[0]:
                self.refresh()


# =====================================================================================
class RegistrationsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Registrations", "Attendance, payment verification and cancellations")
        header.pack(fill="x")
        button(header.actions, "Attendance Sheet (PDF)", self.attendance_sheet, kind="secondary",
               width=190).pack(side="right")
        button(header.actions, "Export CSV", lambda: export_table(self, "Registrations", self.table,
                                                                  "registrations.csv"),
               kind="secondary", width=110).pack(side="right", padx=8)

        bar = toolbar(self)
        self.search = SearchBox(bar, lambda _: self.refresh(), "Name, e-mail, college, team, reg id…", 270)
        self.search.pack(side="left")
        self.events: dict[str, int] = {}
        self.event = combo(bar, ["All events"], lambda _: self.refresh(), 230)
        self.event.pack(side="left", padx=8)
        self.status = ctk.CTkSegmentedButton(bar, values=[ALL, "CONFIRMED", "PENDING", "CANCELLED"],
                                             command=lambda _: self.refresh(), height=36, font=T.f(11))
        self.status.set(ALL)
        self.status.pack(side="left")

        self.table = DataTable(self, [
            ("reg_id", "Reg ID", 60, "center"), ("full_name", "Participant", 150, "w"),
            ("college_name", "College", 170, "w"), ("event_name", "Event", 160, "w"),
            ("team_name", "Team", 90, "w"), ("payment_method", "Paid via", 85, "w"),
            ("amount", "Amount", 70, "e"), ("payment_status", "Payment", 85, "center"),
            ("status", "Status", 90, "center"), ("attended", "Present", 60, "center"),
            ("registered_at", "Registered", 140, "w")],
            selectmode="extended", tag_fn=lambda r: STATUS_TAG.get(r["status"]),
            formatters={"attended": lambda r: "✔" if r["attended"] else "",
                        "payment_method": lambda r: METHOD_LABEL.get(r["payment_method"], "—"),
                        "amount": lambda r: f"{r['amount']:,.0f}" if r["amount"] else "0"})
        self.table.pack(fill="both", expand=True)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        button(actions, "✔  Mark Present", lambda: self.attendance(True), kind="success", width=140).pack(side="left")
        button(actions, "Mark Absent", lambda: self.attendance(False), kind="secondary", width=110).pack(side="left", padx=8)
        button(actions, "Verify Cash Payment", self.verify, kind="secondary", width=160).pack(side="left")
        button(actions, "Receipt", self.receipt, kind="secondary", width=90).pack(side="left", padx=8)
        button(actions, "Cancel & Refund", self.cancel, kind="danger", width=140).pack(side="left")
        self.count = label(actions, "", 12, color=T.MUTED)
        self.count.pack(side="right")
        label(self, "Tip: hold Ctrl or Shift to select several rows (e.g. to mark attendance in bulk).",
              11, color=T.MUTED).pack(anchor="w", pady=(6, 0))

    def refresh(self):
        self.events = {e["event_name"]: e["event_id"] for e in catalog.list_events()}
        self.event.configure(values=["All events"] + list(self.events))
        if self.event.get() not in self.events:
            self.event.set("All events")
        status = self.status.get()
        rows = registrations.search(self.events.get(self.event.get()),
                                    None if status == ALL else status, self.search.get().strip())
        self.table.set_rows(rows)
        confirmed = sum(r["status"] == "CONFIRMED" for r in rows)
        present = sum(bool(r["attended"]) and r["status"] != "CANCELLED" for r in rows)
        self.count.configure(text=f"{len(rows)} shown · {confirmed} confirmed · {present} present")

    def _selection(self):
        rows = self.table.selected_all()
        if not rows:
            Toast.show(self, "Select one or more registrations", "warning")
        return rows

    def attendance(self, present):
        rows = self._selection()
        if not rows:
            return
        eligible = [r["reg_id"] for r in rows if r["status"] == "CONFIRMED"]
        if not eligible:
            error(self, "Attendance can be recorded only for CONFIRMED registrations "
                        "(verify pending payments first).")
            return
        ok, n = self.safe(registrations.set_attendance, eligible, present, self.user.user_id)
        if ok:
            Toast.show(self, f"{n} marked {'present' if present else 'absent'}")
            self.refresh()

    def verify(self):
        rows = self._selection()
        if not rows:
            return
        pending = [r for r in rows if r["payment_status"] == "PENDING"]
        if not pending:
            error(self, "The selected registration(s) have no pending payment.")
            return
        total = sum(r["amount"] for r in pending)
        if confirm(self, f"Confirm cash received for {len(pending)} registration(s), total ₹{total:,.0f}?"):
            for r in pending:
                if not self.safe(registrations.verify_cash_payment, r["reg_id"], self.user.user_id)[0]:
                    break
            Toast.show(self, "Payment verified - registrations confirmed")
            self.refresh()

    def cancel(self):
        rows = self._selection()
        if len(rows) != 1:
            if rows:
                Toast.show(self, "Select a single registration to cancel", "warning")
            return
        r = rows[0]
        if confirm(self, f"Cancel registration #{r['reg_id']} of {r['full_name']} for {r['event_name']}?\n\n"
                         "Successful payments will be marked REFUNDED.", "Cancel registration"):
            if self.safe(registrations.cancel, r["reg_id"], self.user.user_id,
                         success="Registration cancelled")[0]:
                self.refresh()

    def receipt(self):
        rows = self._selection()
        if rows:
            path = pdf.receipt(registrations.get(rows[0]["reg_id"]), self.app.settings)
            config.open_file(path)

    def attendance_sheet(self):
        event_id = self.events.get(self.event.get())
        if not event_id:
            error(self, "Choose an event in the filter first - the sheet is generated per event.",
                  "Select an event")
            return
        rows = [r for r in registrations.search(event_id) if r["status"] != "CANCELLED"]
        e = catalog.get_event(event_id)
        data = [(i, f"REG-{r['reg_id']:05d}", r["full_name"], r["college_name"] or "", r["phone"] or "",
                 r["team_name"] or "", r["payment_status"]) for i, r in enumerate(rows, 1)]
        path = pdf.table_report(
            f"Attendance Sheet - {e['event_name']}",
            f"{fmt(e['event_date'])}, {fmt_time(e['start_time'])} · {e['venue_name'] or 'Online'}",
            ["#", "Reg ID", "Name", "College", "Phone", "Team", "Payment"], data,
            f"Attendance_{e['event_id']:03d}.pdf", widths=[8, 22, 40, 55, 25, 25, 20], signature_column=True)
        config.open_file(path)


# =====================================================================================
class ParticipantsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Participants", "Everyone who has signed up for the symposium")
        header.pack(fill="x")
        button(header.actions, "Export CSV", lambda: export_table(self, "Participants", self.table,
                                                                  "participants.csv"),
               kind="secondary", width=110).pack()
        bar = toolbar(self)
        self.search = SearchBox(bar, lambda _: self.refresh(), "Search name, e-mail, college, phone…", 320)
        self.search.pack(side="left")
        self.count = label(bar, "", 12, color=T.MUTED)
        self.count.pack(side="right")

        self.table = DataTable(self, [
            ("user_id", "ID", 45, "center"), ("full_name", "Name", 150, "w"), ("email", "E-mail", 200, "w"),
            ("phone", "Phone", 95, "w"), ("college_name", "College", 190, "w"),
            ("dept_name", "Department", 170, "w"), ("year_of_study", "Year", 45, "center"),
            ("active_registrations", "Events", 55, "center"), ("is_active", "Account", 75, "center"),
            ("last_login", "Last login", 140, "w")],
            on_double_click=self.view_regs,
            tag_fn=lambda r: None if r["is_active"] else "bad",
            formatters={"is_active": lambda r: "Active" if r["is_active"] else "Disabled"})
        self.table.pack(fill="both", expand=True)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        button(actions, "View Registrations", lambda: self._with(self.view_regs), kind="secondary",
               width=160).pack(side="left")
        button(actions, "Reset Password", lambda: self._with(self.reset), kind="secondary",
               width=140).pack(side="left", padx=8)
        button(actions, "Enable / Disable Account", lambda: self._with(self.toggle), kind="secondary",
               width=190).pack(side="left")

    def refresh(self):
        rows = reports.participants(self.search.get().strip())
        self.table.set_rows(rows)
        self.count.configure(text=f"{len(rows)} participant(s)")

    def _with(self, fn):
        row = self.table.selected()
        if not row:
            Toast.show(self, "Select a participant first", "warning")
            return
        fn(row)

    def view_regs(self, row):
        win = ctk.CTkToplevel(self)
        win.title(f"Registrations · {row['full_name']}")
        win.geometry("900x420")
        win.configure(fg_color=T.BG)
        win.transient(self.winfo_toplevel())
        label(win, row["full_name"], 18, "bold").pack(anchor="w", padx=20, pady=(16, 0))
        label(win, f"{row['email']} · {row['phone'] or '—'} · {row['college_name']}", 12,
              color=T.MUTED).pack(anchor="w", padx=20)
        table = DataTable(win, [
            ("reg_id", "Reg", 50, "center"), ("event_name", "Event", 200, "w"),
            ("event_date", "Date", 100, "w"), ("payment_method", "Paid via", 90, "w"),
            ("amount", "Amount", 70, "e"), ("payment_status", "Payment", 90, "center"),
            ("status", "Status", 90, "center"), ("attended", "Present", 60, "center")],
            tag_fn=lambda r: STATUS_TAG.get(r["status"]),
            formatters={"attended": lambda r: "✔" if r["attended"] else ""})
        table.pack(fill="both", expand=True, padx=20, pady=16)
        table.set_rows(registrations.my_registrations(row["user_id"]))
        win.after(100, win.lift)

    def reset(self, row):
        if confirm(self, f"Generate a new temporary password for {row['full_name']}?"):
            ok, temp = self.safe(auth.reset_password, row["user_id"], self.user.user_id)
            if ok:
                self.clipboard_clear()
                self.clipboard_append(temp)
                messagebox.showinfo("Password reset",
                                    f"Temporary password for {row['email']}:\n\n{temp}\n\n"
                                    "(copied to clipboard - share it with the participant securely)",
                                    parent=self.winfo_toplevel())

    def toggle(self, row):
        active = not row["is_active"]
        verb = "enable" if active else "disable"
        if confirm(self, f"Do you want to {verb} the account of {row['full_name']}?"):
            if self.safe(auth.set_active, row["user_id"], active, self.user.user_id,
                         success=f"Account {verb}d")[0]:
                self.refresh()


# =====================================================================================
class ResultsPage(Page):
    MEDALS = {1: ("★  First", "#D4A017"), 2: ("★  Second", "#9CA3AF"), 3: ("★  Third", "#B87333")}

    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Results & Prizes", "Announce winners and generate certificates")
        header.pack(fill="x")
        bar = toolbar(self)
        label(bar, "Event", 12, "bold", T.MUTED).pack(side="left", padx=(0, 8))
        self.events: dict[str, dict] = {}
        self.event = combo(bar, [], lambda _: self.load_event(), 300)
        self.event.pack(side="left")
        button(bar, "Generate all certificates", self.certificates, kind="secondary",
               width=200).pack(side="right")
        button(bar, "Mark event completed", self.complete, kind="secondary", width=180).pack(side="right", padx=8)

        self.podium = ctk.CTkFrame(self, fg_color="transparent")
        self.podium.pack(fill="x")
        self.podium.grid_columnconfigure((0, 1, 2), weight=1, uniform="p")
        self.slots = {}
        for i, pos in enumerate((1, 2, 3)):
            title, color = self.MEDALS[pos]
            card = Card(self.podium, border_color=color, border_width=2)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            label(card, title + " place", 13, "bold", color).pack(anchor="w", padx=16, pady=(12, 0))
            name = label(card, "—", 17, "bold")
            name.pack(anchor="w", padx=16)
            college = label(card, "Not awarded yet", 11, color=T.MUTED)
            college.pack(anchor="w", padx=16)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(6, 12))
            button(row, f"Award to selected", lambda p=pos: self.award(p), width=140, height=30).pack(side="left")
            button(row, "Clear", lambda p=pos: self.clear(p), kind="ghost", width=60, height=30).pack(side="left")
            self.slots[pos] = (name, college)

        label(self, "Participants who attended (select one, then click 'Award to selected')", 12, "bold",
              T.MUTED).pack(anchor="w", pady=(16, 6))
        self.table = DataTable(self, [
            ("reg_id", "Reg ID", 60, "center"), ("full_name", "Participant", 190, "w"),
            ("team_name", "Team", 120, "w"), ("college_name", "College", 240, "w"),
            ("dept_name", "Department", 200, "w"), ("result_position", "Position", 80, "center")],
            tag_fn=lambda r: "ok" if r["result_position"] else None,
            empty_text="No attendance recorded for this event yet",
            formatters={"result_position": lambda r: {1: "1st ★", 2: "2nd", 3: "3rd"}.get(
                r["result_position"], "")})
        self.table.pack(fill="both", expand=True)

    def refresh(self):
        events = catalog.list_events()
        events.sort(key=lambda e: (e["status"] != "COMPLETED", e["event_date"]))
        self.events = {f"{e['event_name']}  ({e['status'].title()})": e for e in events}
        names = list(self.events)
        self.event.configure(values=names)
        if self.event.get() not in self.events and names:
            self.event.set(names[0])
        self.load_event()

    def current(self):
        return self.events.get(self.event.get())

    def load_event(self):
        e = self.current()
        if not e:
            return
        rows = [r for r in registrations.search(e["event_id"], "CONFIRMED") if r["attended"]]
        self.table.set_rows(rows)
        winners = {r["position"]: r for r in registrations.results(e["event_id"])}
        for pos, (name, college) in self.slots.items():
            w = winners.get(pos)
            name.configure(text=(w["team_name"] or w["full_name"]) if w else "—")
            college.configure(text=(f"{w['full_name']} · {w['college_name']}" if w["team_name"]
                                    else w["college_name"]) if w else "Not awarded yet")

    def award(self, pos):
        e, row = self.current(), self.table.selected()
        if not row:
            Toast.show(self, "Select a participant from the list first", "warning")
            return
        if self.safe(registrations.set_result, e["event_id"], pos, row["reg_id"], self.user.user_id,
                     success=f"{row['full_name']} awarded position {pos}")[0]:
            self.load_event()

    def clear(self, pos):
        e = self.current()
        if e and self.safe(registrations.clear_result, e["event_id"], pos, self.user.user_id)[0]:
            self.load_event()

    def complete(self):
        e = self.current()
        if e and confirm(self, f"Mark '{e['event_name']}' as COMPLETED?\nRegistrations will be closed."):
            if self.safe(catalog.set_event_status, e["event_id"], "COMPLETED", self.user.user_id,
                         success="Event completed")[0]:
                self.refresh()

    def certificates(self):
        e = self.current()
        rows = self.table.rows()
        if not rows:
            error(self, "No attendees for this event - mark attendance first.", "Nothing to generate")
            return
        for r in rows:
            reg = registrations.get(r["reg_id"])
            pdf.certificate(reg, self.app.settings, reg["result_position"])
        Toast.show(self, f"{len(rows)} certificates saved to the exports folder")
        config.open_file(config.EXPORT_DIR)


# =====================================================================================
class ReportsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Reports", "Pre-built analytical queries - export to CSV or PDF")
        header.pack(fill="x")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(14, 0))
        menu = Card(body, width=260)
        menu.pack(side="left", fill="y")
        menu.pack_propagate(False)
        label(menu, "AVAILABLE REPORTS", 10, "bold", T.MUTED).pack(anchor="w", padx=16, pady=(14, 6))
        self.buttons = {}
        for title in reports.REPORTS:
            b = ctk.CTkButton(menu, text=title, anchor="w", height=36, corner_radius=8, font=T.f(12),
                              fg_color="transparent", text_color=T.TEXT, hover_color=T.SURFACE_2,
                              command=lambda t=title: self.show(t))
            b.pack(fill="x", padx=8, pady=1)
            self.buttons[title] = b
        self.right = ctk.CTkFrame(body, fg_color="transparent")
        self.right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        top = ctk.CTkFrame(self.right, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))
        self.title = label(top, "", 17, "bold")
        self.title.pack(side="left")
        button(top, "Export PDF", self.export_pdf, kind="secondary", width=110).pack(side="right")
        button(top, "Export CSV", self.export_csv, kind="secondary", width=110).pack(side="right", padx=8)
        self.sql = label(self.right, "", 10, color=T.MUTED, wraplength=820, justify="left")
        self.sql.pack(anchor="w", pady=(0, 8))
        self.table = None
        self.current = next(iter(reports.REPORTS))
        self.cols, self.rows = [], []

    def refresh(self):
        self.show(self.current)

    def show(self, title):
        self.current = title
        for t, b in self.buttons.items():
            b.configure(fg_color=T.PRIMARY_SOFT if t == title else "transparent",
                        text_color=T.PRIMARY if t == title else T.TEXT)
        ok, result = self.safe(reports.run_report, title)
        if not ok:
            return
        self.cols, self.rows = result
        self.title.configure(text=f"{title}  ·  {len(self.rows)} rows")
        self.sql.configure(text="SQL: " + " ".join(reports.REPORTS[title].split()))
        if self.table:
            self.table.destroy()
        self.table = DataTable(self.right, [(f"c{i}", c, 120, "w") for i, c in enumerate(self.cols)],
                               hscroll=True)
        self.table.pack(fill="both", expand=True)
        self.table.set_rows([{f"c{i}": v for i, v in enumerate(row)} for row in self.rows])

    def _file(self, ext):
        return self.current.split(" (")[0].replace(" ", "_").replace("-", "") + ext

    def export_csv(self):
        path = reports.export_csv(self._file(".csv"), self.cols, [[fmt(v) for v in r] for r in self.rows])
        config.open_file(path)

    def export_pdf(self):
        path = pdf.table_report(self.current, self.app.settings["symposium_name"], self.cols,
                                [[fmt(v) for v in r] for r in self.rows], self._file(".pdf"),
                                landscape=len(self.cols) > 5)
        config.open_file(path)


# =====================================================================================
class SqlConsolePage(Page):
    SAMPLES = {
        "Show all tables": "SHOW FULL TABLES;",
        "Describe registration table": "DESCRIBE registration;",
        "Event summary view": "SELECT * FROM v_event_summary;",
        "Seats left (stored function)": "SELECT event_name, fn_seats_left(event_id) AS seats_left FROM event;",
        "List triggers": "SELECT TRIGGER_NAME, EVENT_MANIPULATION AS on_event, ACTION_TIMING AS timing, "
                         "EVENT_OBJECT_TABLE AS on_table FROM information_schema.TRIGGERS "
                         "WHERE TRIGGER_SCHEMA = DATABASE();",
        "List procedures & functions": "SELECT ROUTINE_NAME, ROUTINE_TYPE FROM information_schema.ROUTINES "
                                       "WHERE ROUTINE_SCHEMA = DATABASE();",
        "Foreign keys": "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                        "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = DATABASE() "
                        "AND REFERENCED_TABLE_NAME IS NOT NULL;",
        "Indexes on registration": "SHOW INDEX FROM registration;",
        "EXPLAIN (index usage)": "EXPLAIN SELECT * FROM event WHERE event_date >= CURDATE();",
        "Top colleges (GROUP BY)": "SELECT college_name, registrations, points FROM v_college_leaderboard "
                                   "ORDER BY points DESC, registrations DESC LIMIT 5;",
    }
    ALLOWED = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH")

    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "SQL Console",
                            "Run read-only queries against the live database (great for demos & viva)")
        header.pack(fill="x")
        bar = toolbar(self)
        label(bar, "Examples", 12, "bold", T.MUTED).pack(side="left", padx=(0, 8))
        self.sample = combo(bar, list(self.SAMPLES), self.load_sample, 300)
        self.sample.set("Event summary view")
        self.sample.pack(side="left")
        button(bar, "▶  Run  (Ctrl+Enter)", self.run, width=170).pack(side="right")

        self.editor = ctk.CTkTextbox(self, height=130, font=("Consolas", 13), corner_radius=10,
                                     border_width=1, border_color=T.BORDER, fg_color=T.SURFACE)
        self.editor.pack(fill="x")
        self.editor.insert("1.0", self.SAMPLES["Event summary view"])
        self.editor.bind("<Control-Return>", lambda e: (self.run(), "break")[1])
        self.status = label(self, "Only SELECT / SHOW / DESCRIBE / EXPLAIN are allowed - "
                                  "queries run inside a READ ONLY transaction.", 11, color=T.MUTED)
        self.status.pack(anchor="w", pady=8)
        self.holder = ctk.CTkFrame(self, fg_color="transparent")
        self.holder.pack(fill="both", expand=True)
        self.table = None

    def load_sample(self, key):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self.SAMPLES[key])
        self.run()

    def refresh(self):
        if self.table is None:
            self.run()

    def run(self):
        sql = self.editor.get("1.0", "end").strip().rstrip(";").strip()
        if not sql:
            return
        if ";" in sql or sql.split(None, 1)[0].upper() not in self.ALLOWED:
            self.status.configure(text="✖ Only a single SELECT / SHOW / DESCRIBE / EXPLAIN statement is allowed.",
                                  text_color=T.DANGER)
            return
        start = time.perf_counter()
        try:
            cols, rows = db.get().read_only_query(sql)
        except db.DatabaseError as exc:
            self.status.configure(text=f"✖ {exc}", text_color=T.DANGER)
            return
        ms = (time.perf_counter() - start) * 1000
        self.status.configure(text=f"✔ {len(rows)} row(s) in {ms:.1f} ms"
                                   + ("  (showing first 1000)" if len(rows) >= 1000 else ""),
                              text_color=T.SUCCESS)
        if self.table:
            self.table.destroy()
        self.table = DataTable(self.holder, [(f"c{i}", c, 130, "w") for i, c in enumerate(cols)],
                               hscroll=True)
        self.table.pack(fill="both", expand=True)
        self.table.set_rows([{f"c{i}": v for i, v in enumerate(r)} for r in rows])


# =====================================================================================
class MasterDataPage(Page):
    SPECS = {
        "Venues": ("venue", [dict(key="venue_name", label="Venue name"),
                             dict(key="location", label="Location", required=False),
                             dict(key="capacity", label="Capacity", type="number", min=1)]),
        "Categories": ("category", [dict(key="category_name", label="Category name")]),
        "Colleges": ("college", [dict(key="college_name", label="College name", width=2),
                                 dict(key="city", label="City", required=False)]),
        "Departments": ("department", [dict(key="dept_name", label="Department name", width=2)]),
    }

    def __init__(self, shell):
        super().__init__(shell)
        PageHeader(self, "Master Data", "Lookup tables used across the system").pack(fill="x")
        self.tabs = ctk.CTkTabview(self, fg_color="transparent", segmented_button_selected_color=T.PRIMARY,
                                   command=self.refresh)
        self.tabs.pack(fill="both", expand=True, pady=(6, 0))
        self.tables = {}
        for name, (kind, fields) in self.SPECS.items():
            tab = self.tabs.add(name)
            pk = catalog.MASTER_TABLES[kind][1]
            cols = [(pk, "ID", 60, "center")] + [(c, lbl, 250, "w") for c, lbl in catalog.MASTER_TABLES[kind][2]]
            bar = ctk.CTkFrame(tab, fg_color="transparent")
            bar.pack(fill="x", pady=(0, 10))
            button(bar, f"+  Add", lambda n=name: self.edit(n, None), width=100).pack(side="left")
            button(bar, "Edit", lambda n=name: self.edit(n, self.tables[n].selected() or False),
                   kind="secondary", width=90).pack(side="left", padx=8)
            button(bar, "Delete", lambda n=name: self.delete(n), kind="danger", width=90).pack(side="left")
            table = DataTable(tab, cols, on_double_click=lambda r, n=name: self.edit(n, r))
            table.pack(fill="both", expand=True)
            self.tables[name] = table

    def refresh(self):
        name = self.tabs.get()
        self.tables[name].set_rows(catalog.master_rows(self.SPECS[name][0]))

    def edit(self, name, row):
        if row is False:
            Toast.show(self, "Select a row first", "warning")
            return
        kind, fields = self.SPECS[name]
        pk = catalog.MASTER_TABLES[kind][1]
        fields = [dict(fd, default=row.get(fd["key"]) if row else None) for fd in fields]

        def submit(values):
            catalog.master_save(kind, values, row[pk] if row else None)
            Toast.show(self, "Saved")
            self.refresh()
        FormDialog(self, f"{'Edit' if row else 'Add'} {name[:-1] if name != 'Categories' else 'Category'}",
                   fields, submit, columns=2 if len(fields) > 1 else 1)

    def delete(self, name):
        row = self.tables[name].selected()
        if not row:
            Toast.show(self, "Select a row first", "warning")
            return
        kind = self.SPECS[name][0]
        pk = catalog.MASTER_TABLES[kind][1]
        if confirm(self, "Delete the selected record?"):
            if self.safe(catalog.master_delete, kind, row[pk], success="Deleted")[0]:
                self.refresh()


# =====================================================================================
class AuditPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        header = PageHeader(self, "Audit Log", "Every sign-in, registration, payment and change - "
                                               "much of it written by database triggers")
        header.pack(fill="x")
        button(header.actions, "Export CSV", lambda: export_table(self, "Audit", self.table, "audit_log.csv"),
               kind="secondary", width=110).pack()
        bar = toolbar(self)
        self.search = SearchBox(bar, lambda _: self.refresh(), "Filter by action, user or details…", 320)
        self.search.pack(side="left")
        self.table = DataTable(self, [
            ("log_id", "#", 60, "center"), ("created_at", "When", 170, "w"), ("who", "User", 170, "w"),
            ("action", "Action", 150, "w"), ("details", "Details", 450, "w")],
            tag_fn=lambda r: "bad" if r["action"] in ("LOGIN_FAILED", "ACCOUNT_LOCKED", "EVENT_DELETED",
                                                      "CANCEL") else None)
        self.table.pack(fill="both", expand=True)

    def refresh(self):
        self.table.set_rows(reports.audit_log(self.search.get().strip()))


# =====================================================================================
class SettingsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        PageHeader(scroll, "Settings", "Symposium details, administrators and your account").pack(fill="x", padx=(0, 8))

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="both", expand=True, pady=14, padx=(0, 8))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="s")

        # symposium details
        card = Card(grid)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 16))
        label(card, "Symposium details", 16, "bold").pack(anchor="w", padx=20, pady=(16, 2))
        label(card, "Shown on the login screen, receipts and certificates", 11, color=T.MUTED).pack(anchor="w", padx=20)
        self.inputs = {}
        for key, text in (("symposium_name", "Symposium name"), ("tagline", "Tagline"),
                          ("host_institution", "Host department / institution"),
                          ("contact_email", "Contact e-mail"), ("contact_phone", "Contact phone")):
            label(card, text, 12, "bold", T.MUTED).pack(anchor="w", padx=20, pady=(10, 2))
            e = ctk.CTkEntry(card, height=36, font=T.f(12))
            e.pack(fill="x", padx=20)
            self.inputs[key] = e
        button(card, "Save details", self.save_settings, width=140).pack(anchor="e", padx=20, pady=16)

        # change password
        pw = Card(grid)
        pw.grid(row=0, column=1, sticky="nsew", pady=(0, 16))
        label(pw, "Change my password", 16, "bold").pack(anchor="w", padx=20, pady=(16, 2))
        label(pw, "Use at least 8 characters with upper & lower case and a digit", 11,
              color=T.MUTED).pack(anchor="w", padx=20)
        self.pw_old = PasswordEntry(pw, "Current password", width=400, height=38)
        self.pw_new = PasswordEntry(pw, "New password", width=400, height=38)
        self.pw_new2 = PasswordEntry(pw, "Confirm new password", width=400, height=38)
        for w in (self.pw_old, self.pw_new, self.pw_new2):
            w.pack(fill="x", padx=20, pady=(12, 0))
        button(pw, "Update password", self.change_password, width=160).pack(anchor="e", padx=20, pady=16)

        info = Card(pw, fg_color=T.SURFACE_2)
        info.pack(fill="x", padx=20, pady=(0, 16))
        self.db_info = label(info, "", 11, color=T.MUTED, justify="left")
        self.db_info.pack(anchor="w", padx=14, pady=10)
        button(info, "Open exports folder", lambda: config.open_file(config.export_path("")),
               kind="ghost", width=160).pack(anchor="w", padx=6, pady=(0, 8))

        # admins
        adm = Card(grid)
        adm.grid(row=1, column=0, columnspan=2, sticky="nsew")
        top = ctk.CTkFrame(adm, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 8))
        label(top, "Administrators", 16, "bold").pack(side="left")
        button(top, "+  Add administrator", self.add_admin, width=170).pack(side="right")
        self.admins = DataTable(adm, [("user_id", "ID", 50, "center"), ("full_name", "Name", 200, "w"),
                                      ("email", "E-mail", 250, "w"), ("phone", "Phone", 120, "w"),
                                      ("last_login", "Last login", 180, "w")])
        self.admins.configure(height=200)
        self.admins.pack(fill="x", padx=20, pady=(0, 20))

    def refresh(self):
        s = catalog.settings()
        for key, e in self.inputs.items():
            e.delete(0, "end")
            e.insert(0, s.get(key, ""))
        self.admins.set_rows(reports.admins())
        p = db.get().params
        counts = db.get().fetch_one(
            "SELECT (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_TYPE='BASE TABLE') AS t, (SELECT COUNT(*) FROM information_schema.VIEWS "
            "WHERE TABLE_SCHEMA = DATABASE()) AS v, (SELECT COUNT(*) FROM information_schema.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = DATABASE()) AS tr, (SELECT COUNT(*) FROM information_schema.ROUTINES "
            "WHERE ROUTINE_SCHEMA = DATABASE()) AS r, VERSION() AS ver")
        self.db_info.configure(text=f"Database  {p['database']} @ {p['host']}:{p['port']}  ·  MySQL {counts['ver']}\n"
                                    f"{counts['t']} tables · {counts['v']} views · {counts['tr']} triggers · "
                                    f"{counts['r']} stored routines")

    def save_settings(self):
        values = {k: e.get().strip() for k, e in self.inputs.items()}
        if not values["symposium_name"]:
            error(self, "Symposium name cannot be empty.")
            return
        if values["contact_email"] and not valid_email(values["contact_email"]):
            error(self, "Contact e-mail is not valid.")
            return
        if self.safe(catalog.save_settings, values, self.user.user_id, success="Symposium details saved")[0]:
            self.app.reload_settings()

    def change_password(self):
        new, new2 = self.pw_new.get(), self.pw_new2.get()
        problems = password_problems(new)
        if problems:
            error(self, "New password needs " + ", ".join(problems) + ".")
            return
        if new != new2:
            error(self, "New passwords do not match.")
            return
        try:
            auth.change_password(self.user.user_id, self.pw_old.get(), new)
        except (auth.AuthError, db.DatabaseError) as exc:
            error(self, str(exc))
            return
        for w in (self.pw_old, self.pw_new, self.pw_new2):
            w.delete(0, "end")
        Toast.show(self, "Password updated")

    def add_admin(self):
        def validate(v):
            if not valid_email(v["email"]):
                return "Enter a valid e-mail address."
            if v["phone"] and not valid_phone(v["phone"]):
                return "Phone must be 10 digits."
            problems = password_problems(v["password"])
            return ("Password needs " + ", ".join(problems) + ".") if problems else None

        def submit(v):
            auth.create_admin(v["full_name"], v["email"], v["phone"] or "", v["password"], self.user.user_id)
            Toast.show(self, "Administrator added")
            self.refresh()
        FormDialog(self, "Add administrator", [
            dict(key="full_name", label="Full name"), dict(key="email", label="E-mail"),
            dict(key="phone", label="Phone", required=False),
            dict(key="password", label="Initial password", type="password")], submit, validate, "Add admin")
