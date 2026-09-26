"""Colours, fonts and ttk styling shared by every screen. (light, dark) tuples follow CTk convention."""
import tkinter.font as tkfont
from tkinter import ttk

import customtkinter as ctk

BG = ("#EEF2F7", "#0B1120")
SURFACE = ("#FFFFFF", "#151E2F")
SURFACE_2 = ("#F6F8FB", "#1C273B")
BORDER = ("#E2E8F0", "#26324A")
TEXT = ("#0F172A", "#E8EDF5")
MUTED = ("#64748B", "#94A3B8")
PRIMARY = ("#4F46E5", "#6366F1")
PRIMARY_HOVER = ("#4338CA", "#4F46E5")
PRIMARY_SOFT = ("#EEF2FF", "#1E2350")
SIDEBAR = ("#1E1B4B", "#0F1629")
SIDEBAR_HOVER = ("#312E81", "#1C2540")
SIDEBAR_ACTIVE = ("#4338CA", "#4F46E5")
SIDEBAR_TEXT = ("#C7D2FE", "#A5B4FC")

SUCCESS = "#16A34A"
WARNING = "#D97706"
DANGER = "#DC2626"
DANGER_HOVER = "#B91C1C"
INFO = "#0891B2"
CHART_COLORS = ["#6366F1", "#06B6D4", "#F59E0B", "#10B981", "#EC4899", "#8B5CF6", "#EF4444", "#84CC16"]

FONT = "Segoe UI"
ICON_FONT = "Segoe MDL2 Assets"

# Segoe MDL2 glyphs (fall back to blank when the font is unavailable)
ICONS = {
    "home": "", "calendar": "", "list": "", "people": "",
    "star": "", "report": "", "library": "", "code": "",
    "history": "", "settings": "", "logout": "", "user": "",
    "search": "", "add": "", "edit": "", "delete": "",
    "refresh": "", "download": "", "check": "", "globe": "",
    "location": "", "clock": "", "lock": "", "mail": "",
    "education": "", "theme": "",
}


def f(size: int = 13, weight: str = "normal") -> tuple:
    return (FONT, size, weight)


def icon_available(root) -> bool:
    return ICON_FONT in tkfont.families(root)


def pick(color) -> str:
    """Resolve a (light, dark) tuple for plain Tk / matplotlib widgets."""
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def apply_tree_style(root) -> None:
    """ttk.Treeview is not a CTk widget - style it to match the current appearance."""
    style = ttk.Style(root)
    style.theme_use("clam")
    scale = ctk.ScalingTracker.get_widget_scaling(root)
    bg, fg, head = pick(SURFACE), pick(TEXT), pick(SURFACE_2)
    style.configure("Sym.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                    rowheight=int(32 * scale), borderwidth=0, relief="flat", font=f(11))
    style.configure("Sym.Treeview.Heading", background=head, foreground=pick(MUTED),
                    font=f(10, "bold"), relief="flat", borderwidth=0, padding=(8, 8))
    style.map("Sym.Treeview.Heading", background=[("active", pick(BORDER))])
    style.map("Sym.Treeview", background=[("selected", pick(PRIMARY))],
              foreground=[("selected", "#FFFFFF")])
    style.layout("Sym.Treeview", [("Sym.Treeview.treearea", {"sticky": "nswe"})])
