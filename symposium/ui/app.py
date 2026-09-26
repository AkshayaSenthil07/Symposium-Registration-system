"""Main window: owns the database bootstrap and switches between top-level views."""
import sys

import customtkinter as ctk

from symposium import config, db
from symposium.services import catalog
from symposium.ui import theme as T
from symposium.ui.widgets import DataTable, confirm


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        ctk.set_appearance_mode(self.cfg["app"].get("appearance", "dark"))
        ctk.set_default_color_theme("blue")
        self.title("Symposium Management System")
        self.configure(fg_color=T.BG)
        # CTk scales geometry by the DPI factor, so work in logical (unscaled) pixels
        scale = ctk.ScalingTracker.get_window_scaling(self)
        screen_w = int(self.winfo_screenwidth() / scale)
        screen_h = int(self.winfo_screenheight() / scale)
        width, height = min(1360, screen_w - 40), min(860, screen_h - 90)
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{max(0, (screen_h - height) // 2 - 30)}")
        self.minsize(min(1100, width), min(640, height))
        if sys.platform.startswith("win"):
            self.after(0, lambda: self.state("zoomed"))
        T.apply_tree_style(self)
        self.view = None
        self.settings = dict(catalog.DEFAULT_SETTINGS)
        self.after(10, self.boot)

    # ------------------------------------------------------------ bootstrap
    def boot(self):
        params = config.mysql_params(self.cfg)
        if config.exists():
            ok, _ = db.test_connection(params)
            if ok and db.schema_ready(params):
                self.database_ready(params)
                return
        self.show_setup()

    def database_ready(self, params: dict):
        db.init(params)
        self.reload_settings()
        self.show_login()

    def reload_settings(self):
        try:
            self.settings = catalog.settings()
        except db.DatabaseError:
            self.settings = dict(catalog.DEFAULT_SETTINGS)
        self.title(f"{self.settings['symposium_name']} · Symposium Management System")

    # ------------------------------------------------------------ navigation
    def _swap(self, view):
        if self.view is not None:
            self.view.destroy()
        self.view = view
        view.pack(fill="both", expand=True)

    def show_setup(self):
        from symposium.ui.setup_view import SetupView
        self._swap(SetupView(self))

    def show_login(self, email: str = ""):
        from symposium.ui.auth_views import LoginView
        self._swap(LoginView(self, email))

    def show_signup(self):
        from symposium.ui.auth_views import SignupView
        self._swap(SignupView(self))

    def show_home(self, user):
        from symposium.ui.shell import build_shell
        self._swap(build_shell(self, user))

    def logout(self):
        if confirm(self, "Do you want to sign out?", "Sign out"):
            self.show_login()

    # ------------------------------------------------------------ appearance
    def toggle_theme(self):
        mode = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(mode)
        self.cfg["app"]["appearance"] = mode
        if config.exists():
            config.save(self.cfg)
        T.apply_tree_style(self)
        self._restyle(self)
        if hasattr(self.view, "on_theme_change"):
            self.view.on_theme_change()

    def _restyle(self, widget):
        if isinstance(widget, DataTable):
            widget.restyle()
        for child in widget.winfo_children():
            self._restyle(child)
