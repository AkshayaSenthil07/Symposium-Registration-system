"""First-run screen: MySQL connection settings + one-click database initialisation."""
import customtkinter as ctk

from symposium import config, db
from symposium.services import setup
from symposium.ui import theme as T
from symposium.ui.widgets import Card, PasswordEntry, Toast, button, confirm, label


class SetupView(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=T.BG)
        self.app = app
        card = Card(self)
        card.place(relx=0.5, rely=0.5, anchor="center")

        label(card, "Database Setup", 24, "bold").pack(anchor="w", padx=32, pady=(28, 0))
        label(card, "Connect the application to your MySQL server.", 13, color=T.MUTED).pack(
            anchor="w", padx=32)

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(fill="x", padx=32, pady=16)
        form.grid_columnconfigure((0, 1), weight=1)
        params = config.mysql_params(app.cfg)
        self.inputs = {}
        specs = [("host", "Host", 0, 0), ("port", "Port", 0, 1), ("user", "Username", 1, 0),
                 ("database", "Database name", 1, 1)]
        for key, text, r, c in specs:
            cell = ctk.CTkFrame(form, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="ew", padx=6, pady=6)
            label(cell, text, 12, "bold", T.MUTED).pack(anchor="w")
            e = ctk.CTkEntry(cell, width=230, height=38, font=T.f(12))
            e.insert(0, str(params[key]))
            e.pack(fill="x")
            self.inputs[key] = e
        cell = ctk.CTkFrame(form, fg_color="transparent")
        cell.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        label(cell, "Password", 12, "bold", T.MUTED).pack(anchor="w")
        self.password = PasswordEntry(cell, "MySQL password", width=472, height=38)
        self.password.pack(fill="x")
        if params["password"]:
            self.password.entry.insert(0, params["password"])

        self.sample = ctk.CTkCheckBox(card, text="Load sample data (events, participants, registrations)",
                                      font=T.f(12))
        self.sample.select()
        self.sample.pack(anchor="w", padx=38)

        self.status = label(card, "", 12, color=T.MUTED, wraplength=480, justify="left")
        self.status.pack(anchor="w", padx=38, pady=(10, 0))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=32, pady=(10, 28))
        button(btns, "Test Connection", self.test, kind="secondary", width=150).pack(side="left", padx=6)
        button(btns, "Initialise Database", self.initialise, kind="danger", width=170).pack(side="right", padx=6)
        button(btns, "Save & Continue", self.save_continue, width=150).pack(side="right", padx=6)

    def params(self) -> dict:
        try:
            port = int(self.inputs["port"].get())
        except ValueError:
            port = 3306
        return {"host": self.inputs["host"].get().strip() or "localhost", "port": port,
                "user": self.inputs["user"].get().strip(), "password": self.password.get(),
                "database": self.inputs["database"].get().strip() or "symposium_db"}

    def _save(self, p):
        cfg = self.app.cfg
        for k, v in p.items():
            cfg["mysql"][k] = str(v)
        config.save(cfg)

    def _status(self, text, color=T.MUTED):
        self.status.configure(text=text, text_color=color)
        self.update_idletasks()

    def test(self):
        ok, msg = db.test_connection(self.params(), with_database=False)
        self._status(("✔ " if ok else "✖ ") + msg, T.SUCCESS if ok else T.DANGER)

    def save_continue(self):
        p = self.params()
        ok, msg = db.test_connection(p, with_database=False)
        if not ok:
            self._status("✖ " + msg, T.DANGER)
            return
        if not db.schema_ready(p):
            self._status(f"✖ Database '{p['database']}' is not set up yet - click "
                         "'Initialise Database'.", T.WARNING)
            return
        self._save(p)
        self.app.database_ready(p)

    def initialise(self):
        p = self.params()
        ok, msg = db.test_connection(p, with_database=False)
        if not ok:
            self._status("✖ " + msg, T.DANGER)
            return
        if not confirm(self, f"This will ERASE and recreate the database '{p['database']}'.\n\nContinue?",
                       "Initialise database"):
            return
        try:
            setup.initialize(p, with_sample=bool(self.sample.get()), log=lambda m: self._status(m))
        except Exception as exc:  # noqa: BLE001
            self._status(f"✖ Setup failed: {exc}", T.DANGER)
            return
        self._save(p)
        Toast.show(self.app, "Database created successfully")
        self.app.database_ready(p)
