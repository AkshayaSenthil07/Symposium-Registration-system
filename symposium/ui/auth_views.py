"""Login and participant sign-up screens."""
import customtkinter as ctk

from symposium import db
from symposium.security import password_problems, password_strength, valid_email, valid_phone
from symposium.services import auth, catalog
from symposium.ui import theme as T
from symposium.ui.widgets import Card, PasswordEntry, Toast, button, label


class LoginView(ctk.CTkFrame):
    def __init__(self, app, email: str = ""):
        super().__init__(app, fg_color=T.BG)
        self.app = app
        s = app.settings
        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        # ---- brand panel
        brand = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0)
        brand.grid(row=0, column=0, sticky="nsew")
        inner = ctk.CTkFrame(brand, fg_color="transparent")
        inner.place(relx=0.12, rely=0.5, anchor="w")
        label(inner, s["host_institution"].upper(), 12, "bold", "#A5B4FC").pack(anchor="w")
        label(inner, s["symposium_name"], 46, "bold", "#FFFFFF").pack(anchor="w", pady=(6, 0))
        label(inner, s["tagline"], 18, color="#C7D2FE").pack(anchor="w")
        ctk.CTkFrame(inner, height=3, width=80, fg_color="#818CF8").pack(anchor="w", pady=26)
        for line in ("Browse technical & non-technical events",
                     "Register and pay in seconds",
                     "Download receipts and certificates instantly",
                     "Live results and college leaderboard"):
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(anchor="w", pady=5)
            label(row, "●", 12, color="#818CF8").pack(side="left")
            label(row, "  " + line, 14, color="#E0E7FF").pack(side="left")
        try:
            stats = db.get().fetch_one(
                "SELECT (SELECT COUNT(*) FROM event WHERE status='OPEN') AS ev, "
                "(SELECT COUNT(*) FROM app_user WHERE role='PARTICIPANT') AS pa, "
                "(SELECT COUNT(*) FROM college) AS co")
            chips = ctk.CTkFrame(inner, fg_color="transparent")
            chips.pack(anchor="w", pady=(30, 0))
            for value, text in ((stats["ev"], "Open events"), (stats["pa"], "Participants"),
                                (stats["co"], "Colleges")):
                chip = ctk.CTkFrame(chips, fg_color="#312E81", corner_radius=12)
                chip.pack(side="left", padx=(0, 12))
                label(chip, str(value), 22, "bold", "#FFFFFF").pack(padx=18, pady=(10, 0))
                label(chip, text, 11, color="#C7D2FE").pack(padx=18, pady=(0, 10))
        except db.DatabaseError:
            pass

        # ---- form
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=16)
        button(top, "☀ / ☾  Theme", app.toggle_theme, kind="ghost", width=110).pack(side="right")

        card = Card(right)
        card.place(relx=0.5, rely=0.5, anchor="center")
        label(card, "Welcome back 👋", 26, "bold").pack(anchor="w", padx=36, pady=(34, 0))
        label(card, "Sign in to your account to continue", 13, color=T.MUTED).pack(anchor="w", padx=36)

        label(card, "E-mail address", 12, "bold", T.MUTED).pack(anchor="w", padx=36, pady=(24, 4))
        self.email = ctk.CTkEntry(card, placeholder_text="you@college.edu", width=340, height=42,
                                  corner_radius=8, font=T.f(13))
        self.email.pack(padx=36)
        if email:
            self.email.insert(0, email)
        label(card, "Password", 12, "bold", T.MUTED).pack(anchor="w", padx=36, pady=(14, 4))
        self.password = PasswordEntry(card, "Enter your password", width=340)
        self.password.pack(padx=36)

        self.error = label(card, "", 12, color=T.DANGER, wraplength=330, justify="left")
        self.error.pack(anchor="w", padx=36, pady=(8, 0))
        self.submit = button(card, "Sign in", self.login, width=340, height=44)
        self.submit.pack(padx=36, pady=(6, 0))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=(18, 4))
        label(row, "New participant?", 12, color=T.MUTED).pack(side="left")
        button(row, "Create an account", app.show_signup, kind="ghost", width=130).pack(side="left")

        hint = ctk.CTkFrame(card, fg_color=T.PRIMARY_SOFT, corner_radius=8)
        hint.pack(fill="x", padx=36, pady=(8, 32))
        label(hint, "Demo  ·  admin@symposium.edu / Admin@123\n"
                    "           student@symposium.edu / Student@123",
              11, color=T.MUTED, justify="left").pack(anchor="w", padx=12, pady=8)

        for w in (self.email, self.password):
            w.bind("<Return>", lambda e: self.login())
        self.after(150, (self.password if email else self.email).focus_set)

    def login(self):
        self.error.configure(text="")
        try:
            user = auth.login(self.email.get(), self.password.get())
        except (auth.AuthError, db.DatabaseError) as exc:
            self.error.configure(text=f"⚠  {exc}")
            self.password.delete(0, "end")
            return
        self.app.show_home(user)
        Toast.show(self.app, f"Welcome, {user.first_name}!")


class SignupView(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=T.BG)
        self.app = app
        self.colleges = {c["college_name"]: c["college_id"] for c in catalog.colleges()}
        self.depts = {d["dept_name"]: d["dept_id"] for d in catalog.departments()}

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        card = Card(scroll)
        card.pack(pady=30)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=36, pady=(30, 6))
        text = ctk.CTkFrame(head, fg_color="transparent")
        text.pack(side="left")
        label(text, "Create your participant account", 24, "bold").pack(anchor="w")
        label(text, f"Register once, then join any event at {app.settings['symposium_name']}",
              13, color=T.MUTED).pack(anchor="w")
        button(head, "← Back to sign in", app.show_login, kind="ghost", width=140).pack(side="right")

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=30, pady=10)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="c")

        def field(r, c, title, widget_factory, span=1):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, columnspan=span, sticky="ew", padx=8, pady=7)
            label(cell, title, 12, "bold", T.MUTED).pack(anchor="w")
            w = widget_factory(cell)
            w.pack(fill="x", pady=(3, 0))
            return w

        entry = lambda ph: (lambda p: ctk.CTkEntry(p, placeholder_text=ph, width=300, height=40,
                                                    corner_radius=8, font=T.f(12)))
        self.name = field(0, 0, "Full name *", entry("e.g. Priya Raman"))
        self.email = field(0, 1, "E-mail address *", entry("you@college.edu"))
        self.phone = field(1, 0, "Mobile number *", entry("10-digit mobile number"))
        self.gender = field(1, 1, "Gender", lambda p: ctk.CTkSegmentedButton(
            p, values=["Male", "Female", "Other"], height=40, font=T.f(12)))
        self.college = field(2, 0, "College *  (type to add yours if missing)", lambda p: ctk.CTkComboBox(
            p, values=list(self.colleges), width=300, height=40, corner_radius=8, font=T.f(12)))
        self.college.set("")
        self.dept = field(2, 1, "Department *", lambda p: ctk.CTkComboBox(
            p, values=list(self.depts), width=300, height=40, corner_radius=8, font=T.f(12),
            state="readonly"))
        self.year = field(3, 0, "Year of study *", lambda p: ctk.CTkSegmentedButton(
            p, values=["1", "2", "3", "4", "5"], height=40, font=T.f(12)))
        self.password = field(4, 0, "Password *", lambda p: PasswordEntry(p, "Min 8 chars, Aa + digit",
                                                                          width=300, height=40))
        self.confirm = field(4, 1, "Confirm password *", lambda p: PasswordEntry(p, "Re-enter password",
                                                                                 width=300, height=40))
        meter = ctk.CTkFrame(grid, fg_color="transparent")
        meter.grid(row=5, column=0, sticky="ew", padx=8)
        self.strength = ctk.CTkProgressBar(meter, height=6, progress_color=T.DANGER)
        self.strength.set(0)
        self.strength.pack(side="left", fill="x", expand=True)
        self.strength_lbl = label(meter, "", 11, "bold", T.MUTED, width=60)
        self.strength_lbl.pack(side="left", padx=8)
        self.password.bind("<KeyRelease>", self._update_strength)

        self.error = label(card, "", 12, color=T.DANGER, wraplength=600, justify="left")
        self.error.pack(anchor="w", padx=38, pady=(8, 0))
        button(card, "Create account", self.submit, width=620, height=44).pack(padx=36, pady=(8, 34))

    def _update_strength(self, _e=None):
        value, text = password_strength(self.password.get())
        color = {"Weak": T.DANGER, "Medium": T.WARNING, "Strong": T.SUCCESS}.get(text, T.DANGER)
        self.strength.configure(progress_color=color)
        self.strength.set(value)
        self.strength_lbl.configure(text=text, text_color=color)

    def submit(self):
        name, email = self.name.get().strip(), self.email.get().strip()
        phone, college = self.phone.get().strip(), self.college.get().strip()
        dept, year = self.dept.get(), self.year.get()
        pwd, pwd2 = self.password.get(), self.confirm.get()
        problems = []
        if len(name) < 3:
            problems.append("Enter your full name.")
        if not valid_email(email):
            problems.append("Enter a valid e-mail address.")
        if not valid_phone(phone):
            problems.append("Mobile number must be exactly 10 digits.")
        if len(college) < 3:
            problems.append("Select or type your college.")
        if dept not in self.depts:
            problems.append("Select your department.")
        if not year:
            problems.append("Select your year of study.")
        weak = password_problems(pwd)
        if weak:
            problems.append("Password needs " + ", ".join(weak) + ".")
        elif pwd != pwd2:
            problems.append("Passwords do not match.")
        if problems:
            self.error.configure(text="⚠  " + "\n⚠  ".join(problems))
            return
        try:
            auth.register_participant(name, email, phone, pwd, college, self.depts[dept], int(year),
                                      self.gender.get() or None)
        except db.DatabaseError as exc:
            self.error.configure(text=f"⚠  {exc}")
            return
        self.app.show_login(email.lower())
        Toast.show(self.app, "Account created - please sign in")
