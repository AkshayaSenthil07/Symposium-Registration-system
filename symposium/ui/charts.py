"""Matplotlib charts embedded in CTk frames, coloured for the current appearance mode."""
import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from symposium.ui import theme as T  # noqa: E402


class ChartCard:
    """Holds a Figure + canvas inside `master`; call draw(fn) to (re)render."""

    def __init__(self, master, height_px: int = 280):
        self.master = master
        self.fig = Figure(figsize=(5, height_px / 100), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=master)
        widget = self.canvas.get_tk_widget()
        widget.configure(highlightthickness=0, borderwidth=0, height=height_px)
        widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def draw(self, render):
        bg, fg, grid = T.pick(T.SURFACE), T.pick(T.TEXT), T.pick(T.BORDER)
        muted = T.pick(T.MUTED)
        self.fig.clear()
        self.fig.set_facecolor(bg)
        self.canvas.get_tk_widget().configure(bg=bg)
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(bg)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(colors=muted, labelsize=8.5)
        ax.xaxis.label.set_color(muted)
        ax.yaxis.label.set_color(muted)
        render(ax, fg=fg, muted=muted, grid=grid, bg=bg)
        self.fig.tight_layout(pad=1.2)
        self.canvas.draw_idle()


def registrations_bar(rows):
    def render(ax, fg, muted, grid, bg):
        rows_sorted = list(reversed(rows[:10]))
        names = [r["event_name"][:24] for r in rows_sorted]
        reg = [r["registered"] for r in rows_sorted]
        cap = [r["max_participants"] for r in rows_sorted]
        fill = [min(r / c, 1) if c else 0 for r, c in zip(reg, cap)]
        colors = [T.DANGER if f >= 0.9 else (T.WARNING if f >= 0.6 else T.CHART_COLORS[0]) for f in fill]
        bars = ax.barh(names, reg, color=colors, height=0.6)
        for bar, r, c in zip(bars, reg, cap):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2, f"{r}/{c}",
                    va="center", fontsize=8, color=muted)
        ax.grid(axis="x", color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", colors=fg)
        ax.set_xlim(0, max(reg + [1]) * 1.2)
    return render


def revenue_donut(rows):
    def render(ax, fg, muted, grid, bg):
        data = [(r["category_name"], float(r["revenue"] or 0)) for r in rows if (r["revenue"] or 0) > 0]
        if not data:
            ax.text(0.5, 0.5, "No revenue yet", ha="center", va="center", color=muted)
            ax.axis("off")
            return
        labels, values = zip(*data)
        wedges, _ = ax.pie(values, colors=T.CHART_COLORS[:len(values)], startangle=90,
                           wedgeprops=dict(width=0.38, edgecolor=bg, linewidth=2))
        total = sum(values)
        ax.text(0, 0.08, f"₹{total:,.0f}", ha="center", va="center", fontsize=15, fontweight="bold", color=fg)
        ax.text(0, -0.16, "collected", ha="center", va="center", fontsize=8.5, color=muted)
        ax.legend(wedges, [f"{lbl}  ₹{v:,.0f}" for lbl, v in data], loc="upper center",
                  bbox_to_anchor=(0.5, 0.02), ncol=2, frameon=False, fontsize=8, labelcolor=fg)
        ax.set_aspect("equal")
    return render


def daily_line(rows):
    def render(ax, fg, muted, grid, bg):
        days = [r["day"].strftime("%d %b") for r in rows]
        counts = [r["n"] for r in rows]
        x = range(len(days))
        ax.plot(x, counts, color=T.CHART_COLORS[0], linewidth=2.2, marker="o", markersize=4)
        ax.fill_between(x, counts, color=T.CHART_COLORS[0], alpha=0.15)
        ax.set_xticks(list(x)[::2])
        ax.set_xticklabels(days[::2])
        ax.grid(axis="y", color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_ylim(bottom=0)
    return render
