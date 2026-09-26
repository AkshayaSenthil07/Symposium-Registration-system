"""Symposium Management System - entry point.

    python main.py
"""
import ctypes
import sys


def _enable_dpi_awareness():
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    from symposium.ui.app import App
    App().mainloop()
