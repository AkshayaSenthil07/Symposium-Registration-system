"""Sidebar + content layout shared by the admin and participant portals."""
import customtkinter as ctk

from symposium import db
from symposium.ui import theme as T
from symposium.ui.widgets import error, label


class Page(ctk.CTkFrame):
    """Base class for every page inside the shell."""

    def __init__(self, shell):
        super().__init__(shell.content, fg_color="transparent")
        self.shell = shell
        self.app = shell.app
        self.user = shell.user

    def refresh(self):
        pass

    def on_theme_change(self):
        pass

    def safe(self, fn, *args, success: str | None = None, **kwargs):
        """Run a service call, show DB errors nicely. Returns (ok, result)."""
        from symposium.ui.widgets import Toast
        try:
            result = fn(*args, **kwargs)
        except db.DatabaseError as exc:
            error(self, str(exc))
            return False, None
        if success:
            Toast.show(self, success)
        return True, result


class NavItem(ctk.CTkFrame):
    def __init__(self, master, icon: str, text: str, command, show_icon: bool):
        super().__init__(master, fg_color="transparent", corner_radius=10, height=42, cursor="hand2")
        self.command = command
        self.active = False
        self.icon = ctk.CTkLabel(self, text=icon if show_icon else "•", width=28,
                                 font=(T.ICON_FONT, 15) if show_icon else T.f(14),
                                 text_color=T.SIDEBAR_TEXT)
        self.icon.pack(side="left", padx=(14, 6), pady=9)
        self.text = ctk.CTkLabel(self, text=text, font=T.f(13), text_color=T.SIDEBAR_TEXT, anchor="w")
        self.text.pack(side="left", fill="x", expand=True)
        for w in (self, self.icon, self.text):
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    def _hover(self, on):
        if not self.active:
            self.configure(fg_color=T.SIDEBAR_HOVER if on else "transparent")

    def set_active(self, active):
        self.active = active
        self.configure(fg_color=T.SIDEBAR_ACTIVE if active else "transparent")
        color = "#FFFFFF" if active else T.SIDEBAR_TEXT
        self.icon.configure(text_color=color)
        self.text.configure(text_color=color, font=T.f(13, "bold" if active else "normal"))


class Shell(ctk.CTkFrame):
    def __init__(self, app, user, nav_items: list[tuple]):
        """nav_items: (key, label, icon_key, PageClass)"""
        super().__init__(app, fg_color=T.BG)
        self.app = app
        self.user = user
        self.pages: dict[str, Page] = {}
        self.factories = {k: cls for k, _, _, cls in nav_items}
        self.nav: dict[str, NavItem] = {}
        self.current: str | None = None

        sidebar = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(24, 18))
        label(brand, app.settings["symposium_name"], 20, "bold", "#FFFFFF").pack(anchor="w")
        label(brand, "Admin Console" if user.is_admin else "Participant Portal", 12,
              color="#A5B4FC").pack(anchor="w")

        show_icon = T.icon_available(self)
        for key, text, icon, _ in nav_items:
            item = NavItem(sidebar, T.ICONS[icon], text, lambda k=key: self.navigate(k), show_icon)
            item.pack(fill="x", padx=12, pady=2)
            self.nav[key] = item

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=12, pady=16)
        self.theme_switch = ctk.CTkSwitch(bottom, text="Dark mode", font=T.f(12),
                                          text_color=T.SIDEBAR_TEXT, command=app.toggle_theme,
                                          progress_color="#6366F1")
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()
        self.theme_switch.pack(anchor="w", padx=10, pady=(0, 12))

        who = ctk.CTkFrame(bottom, fg_color=T.SIDEBAR_HOVER, corner_radius=12)
        who.pack(fill="x")
        initials = "".join(p[0] for p in user.full_name.split()[:2]).upper()
        avatar = ctk.CTkLabel(who, text=initials, width=40, height=40, corner_radius=20,
                              fg_color="#6366F1", text_color="#FFFFFF", font=T.f(13, "bold"))
        avatar.pack(side="left", padx=10, pady=10)
        info = ctk.CTkFrame(who, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        label(info, user.full_name[:22], 12, "bold", "#FFFFFF").pack(anchor="w")
        label(info, user.email[:26], 10, color="#A5B4FC").pack(anchor="w")
        out = NavItem(bottom, T.ICONS["logout"], "Sign out", app.logout, show_icon)
        out.pack(fill="x", pady=(8, 0))

        self.content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self.navigate(nav_items[0][0])

    def navigate(self, key: str):
        if self.current == key:
            self.pages[key].refresh()
            return
        if self.current:
            self.pages[self.current].pack_forget()
            self.nav[self.current].set_active(False)
        if key not in self.pages:
            self.pages[key] = self.factories[key](self)
        page = self.pages[key]
        page.pack(fill="both", expand=True, padx=28, pady=22)
        self.nav[key].set_active(True)
        self.current = key
        try:
            page.refresh()
        except db.DatabaseError as exc:
            error(self, str(exc))

    def on_theme_change(self):
        for page in self.pages.values():
            page.on_theme_change()


def build_shell(app, user) -> Shell:
    if user.is_admin:
        from symposium.ui.admin import pages as a
        items = [
            ("dashboard", "Dashboard", "home", a.DashboardPage),
            ("events", "Events", "calendar", a.EventsPage),
            ("registrations", "Registrations", "list", a.RegistrationsPage),
            ("participants", "Participants", "people", a.ParticipantsPage),
            ("results", "Results & Prizes", "star", a.ResultsPage),
            ("reports", "Reports", "report", a.ReportsPage),
            ("masters", "Master Data", "library", a.MasterDataPage),
            ("sql", "SQL Console", "code", a.SqlConsolePage),
            ("audit", "Audit Log", "history", a.AuditPage),
            ("settings", "Settings", "settings", a.SettingsPage),
        ]
    else:
        from symposium.ui.participant import pages as p
        items = [
            ("explore", "Explore Events", "calendar", p.ExplorePage),
            ("mine", "My Registrations", "list", p.MyRegistrationsPage),
            ("results", "Results & Leaderboard", "star", p.LeaderboardPage),
            ("profile", "My Profile", "user", p.ProfilePage),
        ]
    return Shell(app, user, items)
