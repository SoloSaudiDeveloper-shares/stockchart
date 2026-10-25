"""Shareable PNG charts per symbol, the successors of the old TradingView screenshots.

Each chart is a pair of stacked panels sharing the year axis rather than one panel
with two y-scales: amounts on top, the related percentage below.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE, ORANGE, VIOLET = "#2a78d6", "#eb6834", "#6250d6"

WIDTH_PX, HEIGHT_PX, DPI = 1200, 750, 150
LEFT, RIGHT = 0.08, 0.97
MAX_BAR_PX, GAP_PX = 24, 2
YEARS = 10


def compact(value: float, _=None) -> str:
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            return f"{value / size:.3g}{suffix}"
    return f"{value:.3g}"


def dividends_chart(summary: dict, path: Path, source_note: str) -> bool:
    rows = [r for r in summary["annual"] if r["dps"]][-YEARS:]
    if not rows:
        return False
    years = [r["year"] for r in rows]
    yields = [(r["year"], r["yield"]) for r in rows if r["yield"] is not None]
    fig, top, bottom = _figure(
        summary, "Dividends per share (SAR), by ex-date year", source_note, two_panels=bool(yields)
    )
    _columns(top, years, [[r["dps"] for r in rows]], [BLUE])
    top.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    _label_cap(top, years[-1], rows[-1]["dps"], f"{rows[-1]['dps']:g}")
    if bottom:
        _line(bottom, yields, "Dividend yield, %")
    _save(fig, path)
    return True


def performance_chart(summary: dict, path: Path, source_note: str) -> bool:
    rows = [r for r in summary["annual"] if r["revenue"] is not None or r["net_income"] is not None]
    if not rows:
        return False
    years = [r["year"] for r in rows]
    margins = [(r["year"], r["margin"]) for r in rows if r["margin"] is not None]
    fig, top, bottom = _figure(summary, "Revenue and net income (SAR)", source_note, two_panels=bool(margins))
    revenue = [r["revenue"] or 0 for r in rows]
    income = [r["net_income"] or 0 for r in rows]
    bars = _columns(top, years, [revenue, income], [BLUE, ORANGE])
    top.yaxis.set_major_formatter(FuncFormatter(compact))
    top.legend(bars, ["Revenue", "Net income"], loc="upper left", frameon=False, ncols=2,
               labelcolor=INK_2, fontsize=8, handlelength=1, handleheight=1, borderaxespad=0)
    if bottom:
        _line(bottom, margins, "Net margin, %")
    _save(fig, path)
    return True


def _figure(summary, subtitle, source_note, two_panels):
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=SURFACE)
    title = summary["code"] + (f" · {summary['name']}" if summary.get("name") else "")
    fig.text(LEFT, 0.95, title, fontsize=12, fontweight="bold", color=INK, va="top")
    fig.text(LEFT, 0.895, subtitle, fontsize=8.5, color=INK_2, va="top")
    fig.text(LEFT, 0.03, source_note, fontsize=6.5, color=MUTED)
    if two_panels:
        grid = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.45,
                                left=LEFT, right=RIGHT, top=0.80, bottom=0.12)
        top = fig.add_subplot(grid[0])
        bottom = fig.add_subplot(grid[1], sharex=top)
    else:
        top = fig.add_axes((LEFT, 0.12, RIGHT - LEFT, 0.68))
        bottom = None
    for ax in (top, bottom):
        if ax:
            _style(ax)
    return fig, top, bottom


def _style(ax):
    ax.set_facecolor(SURFACE)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.axhline(0, color=BASELINE, linewidth=0.8, zorder=1)  # the baseline, wherever zero sits
    ax.tick_params(colors=MUTED, labelsize=7.5, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))


def _columns(ax, years, series, colors):
    """Grouped columns capped at 24px each, 2px apart."""
    ax.set_xlim(years[0] - 0.6, years[-1] + 0.6)
    axes_px = ax.get_position().width * WIDTH_PX
    px_per_year = axes_px / (years[-1] - years[0] + 1.2)
    slot_px = min(MAX_BAR_PX, (px_per_year * 0.7 - GAP_PX * (len(series) - 1)) / len(series))
    width = slot_px / px_per_year
    step = (slot_px + GAP_PX) / px_per_year
    bars = []
    for i, (values, color) in enumerate(zip(series, colors)):
        offset = (i - (len(series) - 1) / 2) * step
        bars.append(ax.bar([y + offset for y in years], values, width=width, color=color, linewidth=0))
    return bars


def _label_cap(ax, x, y, text):
    ax.annotate(text, (x, y), xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", fontsize=7.5, color=INK_2)


def _line(ax, points, title):
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=VIOLET, linewidth=1.5, solid_capstyle="round", solid_joinstyle="round",
            marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)
    ax.set_title(title, loc="left", fontsize=8.5, color=INK_2, pad=6)
    low, high = min(0, *ys), max(0, *ys)
    pad = (high - low) * 0.25 or 1
    ax.set_ylim(low - pad if low < 0 else 0, high + pad)
    _label_cap(ax, xs[-1], ys[-1], f"{ys[-1]:.2f}%")


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
