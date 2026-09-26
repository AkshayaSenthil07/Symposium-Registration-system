"""Participant portal pages."""
import datetime as dt
import tkinter as tk

import customtkinter as ctk

from symposium import config, db
from symposium.security import password_problems, valid_phone
from symposium.services import auth, catalog, pdf, registrations
from symposium.ui import theme as T
from symposium.ui.shell import Page
from symposium.ui.widgets import (Badge, Card, DataTable, PageHeader, PasswordEntry, SearchBox, StatCard,
                                  Toast, button, confirm, error, fmt_time, label, money)

CATEGORY_COLORS = {"Technical": "#6366F1", "Non-Technical": "#EC4899", "Workshop": "#F59E0B",
                   "Online": "#06B6D4"}
STATUS_TAG = {"CONFIRMED": "ok", "PENDING": "warn", "CANCELLED": "bad"}


def cat_color(name):
    return CATEGORY_COLORS.get(name, T.CHART_COLORS[hash(name) % len(T.CHART_COLORS)])


# =====================================================================================
class ExplorePage(Page):
    COLUMNS = 3

    def __init__(self, shell):
        super().__init__(shell)
        self.header = PageHeader(self, "Explore Events", "")
        self.header.pack(fill="x")
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(14, 10))
        self.search = SearchBox(bar, lambda _: self.render(), "Search events…", 260)
        self.search.pack(side="left")
        self.category = ctk.CTkSegmentedButton(bar, values=["All"], command=lambda _: self.render(),
                                               height=36, font=T.f(12))
        self.category.set("All")
        self.category.pack(side="left", padx=10)
        self.only_open = ctk.CTkSwitch(bar, text="Only events I can join", font=T.f(12),
                                       command=self.render)
        self.only_open.pack(side="right")
        self.grid_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_area.pack(fill="both", expand=True)
        for c in range(self.COLUMNS):
            self.grid_area.grid_columnconfigure(c, weight=1, uniform="ev")
        self.events, self.mine = [], {}

    def refresh(self):
        cats = ["All"] + [c["category_name"] for c in catalog.categories()]
        self.category.configure(values=cats)
        if self.category.get() not in cats:
            self.category.set("All")
        self.events = [e for e in catalog.list_events() if e["status"] != "CANCELLED"]
        self.mine = registrations.active_event_ids(self.user.user_id)
        open_count = sum(e["status"] == "OPEN" and e["event_date"] >= dt.date.today() for e in self.events)
        self.header.sub.configure(text=f"Hi {self.user.first_name}! {open_count} events are open for "
                                       f"registration at {self.app.settings['symposium_name']}.")
        self.render()

    def _state(self, e):
        """Returns (button text, enabled, kind)."""
        registered = e["event_id"] in self.mine
        if e["status"] == "COMPLETED" or e["event_date"] < dt.date.today():
            return ("✔  You participated" if registered else "Event completed"), False,                 "success" if registered else "secondary"
        if registered:
            if self.mine[e["event_id"]] == "PENDING":
                return "⏳  Registered · pay at desk", False, "secondary"
            return "✔  You're registered", False, "success"
        if e["status"] != "OPEN":
            return "Registrations closed", False, "secondary"
        if e["seats_left"] <= 0:
            return "Housefull", False, "secondary"
        return f"Register  ·  {money(e['registration_fee'])}", True, "primary"

    def render(self):
        for w in self.grid_area.winfo_children():
            w.destroy()
        text = self.search.get().strip().lower()
        cat = self.category.get()
        shown = []
        for e in self.events:
            if cat != "All" and e["category_name"] != cat:
                continue
            if text and text not in (e["event_name"] + " " + (e["description"] or "")).lower():
                continue
            if self.only_open.get() and not self._state(e)[1]:
                continue
            shown.append(e)
        if not shown:
            label(self.grid_area, "No events match your filters.", 14, color=T.MUTED).grid(
                row=0, column=0, columnspan=self.COLUMNS, pady=60)
            return
        for i, e in enumerate(shown):
            self._card(e).grid(row=i // self.COLUMNS, column=i % self.COLUMNS, sticky="nsew",
                               padx=(0 if i % self.COLUMNS == 0 else 12, 0), pady=(0, 12))

    def _card(self, e):
        color = cat_color(e["category_name"])
        card = Card(self.grid_area)
        ctk.CTkFrame(card, height=6, fg_color=color, corner_radius=3).pack(fill="x", padx=14, pady=(12, 0))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(10, 0))
        Badge(top, e["category_name"], color).pack(side="left")
        if e["status"] != "OPEN":
            Badge(top, e["status"].title()).pack(side="left", padx=6)
        label(top, money(e["registration_fee"]), 15, "bold", T.PRIMARY).pack(side="right")

        label(card, e["event_name"], 17, "bold", anchor="w").pack(fill="x", padx=16, pady=(8, 0))
        meta = (f"📅  {e['event_date'].strftime('%a, %d %b %Y')}\n"
                f"🕘  {fmt_time(e['start_time'])} – {fmt_time(e['end_time'])}\n"
                f"📍  {e['venue_name'] or 'Online'}")
        label(card, meta, 12, color=T.MUTED, justify="left", anchor="w").pack(fill="x", padx=16, pady=(4, 0))
        desc = e["description"] or ""
        label(card, desc[:120] + ("…" if len(desc) > 120 else ""), 12, justify="left", anchor="w",
              wraplength=300).pack(fill="x", padx=16, pady=(8, 0))

        filled = e["registered"] / e["max_participants"] if e["max_participants"] else 1
        seats = ctk.CTkFrame(card, fg_color="transparent")
        seats.pack(fill="x", padx=16, pady=(10, 0))
        bar_color = T.DANGER if filled >= 0.9 else (T.WARNING if filled >= 0.6 else T.SUCCESS)
        pb = ctk.CTkProgressBar(seats, height=6, progress_color=bar_color)
        pb.set(min(filled, 1))
        pb.pack(fill="x")
        label(seats, f"{max(e['seats_left'], 0)} of {e['max_participants']} seats left", 11,
              color=T.MUTED).pack(anchor="w", pady=(2, 0))
        if e["coordinator_name"]:
            label(card, f"Coordinator: {e['coordinator_name']}"
                        + (f"  ·  {e['coordinator_phone']}" if e["coordinator_phone"] else ""),
                  11, color=T.MUTED, anchor="w").pack(fill="x", padx=16)

        text, enabled, kind = self._state(e)
        btn = button(card, text, lambda: RegisterDialog(self, e), kind=kind, width=200)
        if not enabled:
            btn.configure(state="disabled", text_color_disabled="#FFFFFF" if kind == "success" else T.MUTED)
        btn.pack(fill="x", padx=16, pady=(10, 16))
        return card


class RegisterDialog(ctk.CTkToplevel):
    def __init__(self, page: ExplorePage, event: dict):
        super().__init__(page)
        self.withdraw()
        self.page, self.event = page, event
        self.title(f"Register · {event['event_name']}")
        self.configure(fg_color=T.BG)
        self.resizable(False, False)
        self.body = Card(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=16)
        self._form()
        self.transient(page.winfo_toplevel())
        self.update_idletasks()
        top = page.winfo_toplevel()
        self.geometry(f"+{top.winfo_rootx() + (top.winfo_width() - 480) // 2}+{top.winfo_rooty() + 80}")
        self.deiconify()
        self.after(80, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _form(self):
        e, b = self.event, self.body
        label(b, "Confirm registration", 20, "bold").pack(anchor="w", padx=24, pady=(20, 0))
        label(b, "Review the details and choose how you'd like to pay", 12, color=T.MUTED).pack(anchor="w", padx=24)
        summary = ctk.CTkFrame(b, fg_color=T.SURFACE_2, corner_radius=10)
        summary.pack(fill="x", padx=24, pady=14)
        label(summary, e["event_name"], 16, "bold").pack(anchor="w", padx=14, pady=(10, 0))
        label(summary, f"{e['event_date'].strftime('%a, %d %b %Y')} · {fmt_time(e['start_time'])} – "
                       f"{fmt_time(e['end_time'])} · {e['venue_name'] or 'Online'}", 12,
              color=T.MUTED).pack(anchor="w", padx=14, pady=(0, 10))

        label(b, "Team name (optional)", 12, "bold", T.MUTED).pack(anchor="w", padx=24)
        self.team = ctk.CTkEntry(b, placeholder_text="Leave empty for individual participation",
                                 width=420, height=38, font=T.f(12))
        self.team.pack(padx=24, pady=(3, 12))

        fee = e["registration_fee"]
        self.method = tk.StringVar(value="UPI")
        if fee:
            label(b, "Payment method", 12, "bold", T.MUTED).pack(anchor="w", padx=24)
            for key, text in registrations.PAYMENT_METHODS.items():
                ctk.CTkRadioButton(b, text=text, variable=self.method, value=key, font=T.f(12)).pack(
                    anchor="w", padx=30, pady=3)
            label(b, "ⓘ Demo payment gateway - no real money is charged.", 11, color=T.MUTED).pack(
                anchor="w", padx=24, pady=(6, 0))
        else:
            label(b, "This event is free - no payment needed.", 13, "bold", T.SUCCESS).pack(anchor="w", padx=24)

        total = ctk.CTkFrame(b, fg_color="transparent")
        total.pack(fill="x", padx=24, pady=(14, 0))
        label(total, "Total", 14, "bold").pack(side="left")
        label(total, f"₹{fee:,.2f}", 18, "bold", T.PRIMARY).pack(side="right")
        self.error = label(b, "", 12, color=T.DANGER, wraplength=420, justify="left")
        self.error.pack(anchor="w", padx=24)
        btns = ctk.CTkFrame(b, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=(8, 20))
        self.pay_btn = button(btns, f"Pay ₹{fee:,.0f} & Register" if fee else "Register now",
                              self._pay, width=240, height=42)
        self.pay_btn.pack(side="right")
        button(btns, "Cancel", self.destroy, kind="secondary", width=100, height=42).pack(side="right", padx=8)

    def _pay(self):
        self.pay_btn.configure(state="disabled", text="Processing payment…")
        self.after(900, self._submit)          # simulate a payment gateway round-trip

    def _submit(self):
        try:
            reg_id = registrations.register(self.page.user.user_id, self.event["event_id"],
                                            self.team.get().strip(), self.method.get())
        except db.DatabaseError as exc:
            self.error.configure(text=f"⚠  {exc}")
            fee = self.event["registration_fee"]
            self.pay_btn.configure(state="normal", text=f"Pay ₹{fee:,.0f} & Register" if fee else "Register now")
            return
        self.reg = registrations.get(reg_id)
        self._success()
        self.page.refresh()

    def _success(self):
        self._clear()
        r, b = self.reg, self.body
        pending = r["payment_status"] == "PENDING"
        color = T.WARNING if pending else T.SUCCESS
        circle = ctk.CTkLabel(b, text="⏳" if pending else "✔", width=72, height=72, corner_radius=36,
                              fg_color=color, text_color="#FFFFFF", font=T.f(30, "bold"))
        circle.pack(pady=(28, 10))
        label(b, "Seat reserved!" if pending else "You're registered!", 22, "bold").pack()
        msg = (f"Pay ₹{r['amount']:,.0f} at the registration desk to confirm your seat."
               if pending else f"See you at {r['event_name']}.")
        label(b, msg, 13, color=T.MUTED, wraplength=380).pack(pady=(2, 14))
        info = ctk.CTkFrame(b, fg_color=T.SURFACE_2, corner_radius=10)
        info.pack(fill="x", padx=30)
        for k, v in (("Registration ID", f"REG-{r['reg_id']:05d}"), ("Transaction ref", r["transaction_ref"]),
                     ("Amount", f"₹{r['amount']:,.2f}"), ("Status", r["status"])):
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=3)
            label(row, k, 12, color=T.MUTED).pack(side="left")
            label(row, v, 12, "bold").pack(side="right", padx=(28, 0))
        btns = ctk.CTkFrame(b, fg_color="transparent")
        btns.pack(pady=(18, 24))
        button(btns, "Download receipt", lambda: config.open_file(pdf.receipt(r, self.page.app.settings)),
               kind="secondary", width=160, height=40).pack(side="left", padx=6)
        button(btns, "Done", self.destroy, width=120, height=40).pack(side="left", padx=6)


# =====================================================================================
class MyRegistrationsPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        PageHeader(self, "My Registrations", "Your events, receipts and certificates").pack(fill="x")
        self.cards = ctk.CTkFrame(self, fg_color="transparent")
        self.cards.pack(fill="x", pady=14)
        self.cards.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="c")
        self.stats = {}
        for i, (key, title, color) in enumerate([("upcoming", "Upcoming events", T.CHART_COLORS[0]),
                                                 ("pending", "Awaiting payment", T.WARNING),
                                                 ("spent", "Total paid", T.CHART_COLORS[1]),
                                                 ("certs", "Certificates", T.SUCCESS)]):
            c = StatCard(self.cards, title, "–", "", color)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.stats[key] = c

        self.table = DataTable(self, [
            ("reg_id", "Reg ID", 70, "center"), ("event_name", "Event", 200, "w"),
            ("event_date", "Date", 110, "w"), ("start_time", "Time", 150, "w"),
            ("venue_name", "Venue", 150, "w"), ("team_name", "Team", 110, "w"),
            ("amount", "Amount", 80, "e"), ("payment_status", "Payment", 90, "center"),
            ("status", "Status", 100, "center"), ("result", "Result", 110, "center")],
            tag_fn=lambda r: STATUS_TAG.get(r["status"]),
            empty_text="You haven't registered for any event yet - head to Explore Events!",
            formatters={
                "reg_id": lambda r: f"REG-{r['reg_id']:05d}",
                "start_time": lambda r: f"{fmt_time(r['start_time'])} – {fmt_time(r['end_time'])}",
                "venue_name": lambda r: r["venue_name"] or "Online",
                "amount": lambda r: money(r["amount"]),
                "result": lambda r: ({1: "★ Winner", 2: "★ Runner-up", 3: "★ Third place"}.get(r["result_position"])
                                     or ("✔ Attended" if r["attended"] else ""))})
        self.table.pack(fill="both", expand=True)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", pady=(10, 0))
        button(actions, "Download Receipt", self.receipt, width=160).pack(side="left")
        button(actions, "Download Certificate", self.certificate, kind="success", width=180).pack(side="left", padx=8)
        button(actions, "Cancel Registration", self.cancel, kind="danger", width=170).pack(side="right")

    def refresh(self):
        rows = registrations.my_registrations(self.user.user_id)
        self.table.set_rows(rows)
        today = dt.date.today()
        active = [r for r in rows if r["status"] != "CANCELLED"]
        self.stats["upcoming"].value.configure(text=str(sum(r["event_date"] >= today for r in active)))
        self.stats["pending"].value.configure(text=str(sum(r["status"] == "PENDING" for r in active)))
        spent = sum(r["amount"] or 0 for r in rows if r["payment_status"] == "SUCCESS")
        self.stats["spent"].value.configure(text=f"₹{spent:,.0f}")
        self.stats["certs"].value.configure(text=str(sum(bool(r["attended"]) for r in active)))
        self.stats["certs"].note.configure(text="available to download")

    def _selected(self):
        r = self.table.selected()
        if not r:
            Toast.show(self, "Select a registration first", "warning")
        return r

    def receipt(self):
        r = self._selected()
        if r:
            config.open_file(pdf.receipt(r, self.app.settings))

    def certificate(self):
        r = self._selected()
        if not r:
            return
        if r["status"] == "CANCELLED" or not r["attended"]:
            error(self, "Certificates become available once your attendance is recorded at the event.",
                  "Certificate not available yet")
            return
        config.open_file(pdf.certificate(r, self.app.settings, r["result_position"]))

    def cancel(self):
        r = self._selected()
        if not r:
            return
        if r["status"] == "CANCELLED":
            error(self, "This registration is already cancelled.")
            return
        if r["event_date"] <= dt.date.today():
            error(self, "Registrations can only be cancelled before the event day.")
            return
        refund = " Your payment will be refunded." if r["payment_status"] == "SUCCESS" and r["amount"] else ""
        if confirm(self, f"Cancel your registration for {r['event_name']}?{refund}", "Cancel registration"):
            if self.safe(registrations.cancel, r["reg_id"], self.user.user_id,
                         success="Registration cancelled")[0]:
                self.refresh()


# =====================================================================================
class LeaderboardPage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        PageHeader(self, "Results & Leaderboard", "Winners of completed events and the college championship").pack(fill="x")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(14, 0))
        body.grid_columnconfigure(0, weight=3, uniform="l")
        body.grid_columnconfigure(1, weight=2, uniform="l")
        body.grid_rowconfigure(1, weight=1)
        label(body, "Event winners", 15, "bold").grid(row=0, column=0, sticky="w", pady=(0, 6))
        label(body, "College championship  (5 / 3 / 1 points)", 15, "bold").grid(row=0, column=1, sticky="w",
                                                                              padx=(12, 0), pady=(0, 6))
        medal = {1: "1st ★", 2: "2nd", 3: "3rd"}
        self.winners = DataTable(body, [
            ("event_name", "Event", 190, "w"), ("position", "Place", 70, "center"),
            ("full_name", "Winner", 150, "w"), ("college_name", "College", 190, "w")],
            empty_text="Results will appear here once events are completed",
            formatters={"position": lambda r: medal[r["position"]],
                        "full_name": lambda r: r["team_name"] or r["full_name"]})
        self.winners.grid(row=1, column=0, sticky="nsew")
        self.colleges = DataTable(body, [
            ("rank", "#", 40, "center"), ("college_name", "College", 210, "w"),
            ("gold", "Gold", 50, "center"), ("silver", "Silver", 55, "center"), ("bronze", "Bronze", 60, "center"),
            ("points", "Pts", 50, "center")],
            tag_fn=lambda r: "ok" if r["rank"] == 1 and r["points"] else None)
        self.colleges.grid(row=1, column=1, sticky="nsew", padx=(12, 0))

    def refresh(self):
        self.winners.set_rows(registrations.results())
        rows = db.get().fetch_all("SELECT * FROM v_college_leaderboard WHERE registrations > 0 "
                                  "ORDER BY points DESC, gold DESC, registrations DESC")
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        self.colleges.set_rows(rows)


# =====================================================================================
class ProfilePage(Page):
    def __init__(self, shell):
        super().__init__(shell)
        PageHeader(self, "My Profile", "Keep your details up to date - they appear on your certificates").pack(fill="x")
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, pady=14)
        grid.grid_columnconfigure(0, weight=3, uniform="p")
        grid.grid_columnconfigure(1, weight=2, uniform="p")

        card = Card(grid)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        label(card, "Personal details", 16, "bold").pack(anchor="w", padx=22, pady=(18, 4))
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=16)
        form.grid_columnconfigure((0, 1), weight=1, uniform="f")

        def cell(r, c, title, widget, span=1):
            f = ctk.CTkFrame(form, fg_color="transparent")
            f.grid(row=r, column=c, columnspan=span, sticky="ew", padx=6, pady=6)
            label(f, title, 12, "bold", T.MUTED).pack(anchor="w")
            w = widget(f)
            w.pack(fill="x", pady=(3, 0))
            return w

        entry = lambda p: ctk.CTkEntry(p, height=38, font=T.f(12))
        self.name = cell(0, 0, "Full name", entry)
        self.email = cell(0, 1, "E-mail (login id)", entry)
        self.phone = cell(1, 0, "Mobile number", entry)
        self.gender = cell(1, 1, "Gender", lambda p: ctk.CTkSegmentedButton(
            p, values=["Male", "Female", "Other"], height=38, font=T.f(12)))
        self.colleges = {}
        self.depts = {}
        self.college = cell(2, 0, "College", lambda p: ctk.CTkComboBox(p, values=[], height=38, font=T.f(12)), 2)
        self.dept = cell(3, 0, "Department", lambda p: ctk.CTkComboBox(p, values=[], height=38, font=T.f(12),
                                                                      state="readonly"))
        self.year = cell(3, 1, "Year of study", lambda p: ctk.CTkSegmentedButton(
            p, values=["1", "2", "3", "4", "5"], height=38, font=T.f(12)))
        button(card, "Save changes", self.save, width=150).pack(anchor="e", padx=22, pady=18)

        pw = Card(grid)
        pw.grid(row=0, column=1, sticky="nsew")
        label(pw, "Change password", 16, "bold").pack(anchor="w", padx=22, pady=(18, 2))
        label(pw, "At least 8 characters with A-Z, a-z and 0-9", 11, color=T.MUTED).pack(anchor="w", padx=22)
        self.pw_old = PasswordEntry(pw, "Current password", width=340, height=38)
        self.pw_new = PasswordEntry(pw, "New password", width=340, height=38)
        self.pw_new2 = PasswordEntry(pw, "Confirm new password", width=340, height=38)
        for w in (self.pw_old, self.pw_new, self.pw_new2):
            w.pack(fill="x", padx=22, pady=(12, 0))
        button(pw, "Update password", self.change_password, width=160).pack(anchor="e", padx=22, pady=18)

    def refresh(self):
        self.colleges = {c["college_name"]: c["college_id"] for c in catalog.colleges()}
        self.depts = {d["dept_name"]: d["dept_id"] for d in catalog.departments()}
        self.college.configure(values=list(self.colleges))
        self.dept.configure(values=list(self.depts))
        p = auth.get_profile(self.user.user_id)
        for w, v in ((self.name, p["full_name"]), (self.email, p["email"]), (self.phone, p["phone"] or "")):
            w.configure(state="normal")
            w.delete(0, "end")
            w.insert(0, v)
        self.email.configure(state="disabled")
        self.gender.set(p["gender"] or "")
        self.college.set(p["college_name"] or "")
        self.dept.set(p["dept_name"] or "")
        self.year.set(str(p["year_of_study"] or ""))

    def save(self):
        name, phone = self.name.get().strip(), self.phone.get().strip()
        college, dept, year = self.college.get().strip(), self.dept.get(), self.year.get()
        if len(name) < 3:
            return error(self, "Please enter your full name.")
        if not valid_phone(phone):
            return error(self, "Mobile number must be exactly 10 digits.")
        if len(college) < 3 or dept not in self.depts or not year:
            return error(self, "Please choose your college, department and year.")
        if self.safe(auth.update_profile, self.user.user_id, name, phone, college, self.depts[dept],
                     int(year), self.gender.get() or None, success="Profile updated")[0]:
            self.user.full_name = name
            self.refresh()

    def change_password(self):
        new = self.pw_new.get()
        problems = password_problems(new)
        if problems:
            return error(self, "New password needs " + ", ".join(problems) + ".")
        if new != self.pw_new2.get():
            return error(self, "New passwords do not match.")
        try:
            auth.change_password(self.user.user_id, self.pw_old.get(), new)
        except (auth.AuthError, db.DatabaseError) as exc:
            return error(self, str(exc))
        for w in (self.pw_old, self.pw_new, self.pw_new2):
            w.delete(0, "end")
        Toast.show(self, "Password updated")
