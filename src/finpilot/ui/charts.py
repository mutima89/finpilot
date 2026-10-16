"""Matplotlib charts styled with the FinPilot palette."""
from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .theme import palette  # noqa: E402


def money_fmt(x, _pos=None):
    a = abs(x)
    sign = "-" if x < 0 else ""
    if a >= 1e6:
        return f"{sign}${a / 1e6:.1f}m"
    if a >= 1e3:
        return f"{sign}${a / 1e3:.0f}k"
    return f"{sign}${a:.0f}"


def pct_fmt(x, _pos=None):
    return f"{x:.0%}"


class Chart(FigureCanvasQTAgg):
    def __init__(self, width: float = 6, height: float = 2.8):
        self.fig = Figure(figsize=(width, height), dpi=100)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.setMinimumHeight(int(height * 70))
        self._style()

    def _style(self):
        p = palette()
        self.fig.patch.set_facecolor(p.surface)
        ax = self.ax
        ax.set_facecolor(p.surface)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(p.border)
        ax.tick_params(colors=p.muted, labelsize=8)
        ax.yaxis.label.set_color(p.muted)
        ax.grid(axis="y", color=p.grid_line, linewidth=0.7)
        ax.set_axisbelow(True)

    def reset(self):
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self._style()

    def finish(self, legend: bool = True, title: str = ""):
        p = palette()
        if title:
            self.ax.set_title(title, color=p.text, fontsize=9.5, loc="left", fontweight="bold")
        if legend and self.ax.get_legend_handles_labels()[0]:
            leg = self.ax.legend(frameon=False, fontsize=8, loc="upper left")
            for t in leg.get_texts():
                t.set_color(p.text)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.fig.tight_layout()
        self.draw_idle()

    def bars(self, labels, series: list[tuple[str, list[float]]], money: bool = True, title: str = ""):
        self.reset()
        p = palette()
        n = max(1, len(series))
        width = 0.8 / n
        x = list(range(len(labels)))
        for i, (name, vals) in enumerate(series):
            self.ax.bar([xi - 0.4 + width * (i + 0.5) for xi in x], vals, width=width * 0.95,
                        color=p.chart_series[i % len(p.chart_series)] if i else p.chart_series[2], label=name)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels)
        if money:
            self.ax.yaxis.set_major_formatter(FuncFormatter(money_fmt))
        self.finish(title=title)

    def lines(self, labels, series: list[tuple[str, list[float]]], fmt: str = "money", title: str = ""):
        self.reset()
        p = palette()
        x = list(range(len(labels)))
        for i, (name, vals) in enumerate(series):
            clean = [v if isinstance(v, (int, float)) else float("nan") for v in vals]
            self.ax.plot(x, clean, marker="o", markersize=3.5, linewidth=2,
                         color=p.chart_series[i % len(p.chart_series)], label=name)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels)
        if fmt == "money":
            self.ax.yaxis.set_major_formatter(FuncFormatter(money_fmt))
        elif fmt == "pct":
            self.ax.yaxis.set_major_formatter(FuncFormatter(pct_fmt))
        self.finish(title=title)

    def waterfall(self, steps: list[tuple[str, float]], start_label: str, start: float, end_label: str,
                  title: str = ""):
        """Revenue bridge: start bar, signed steps, end bar."""
        self.reset()
        p = palette()
        labels = [start_label] + [s[0] for s in steps] + [end_label]
        self.ax.bar(0, start, color=p.chart_series[2])
        running = start
        for i, (_, v) in enumerate(steps, start=1):
            color = p.success if v >= 0 else p.coral
            self.ax.bar(i, v, bottom=running if v >= 0 else running + v, color=color)
            self.ax.text(i, running + max(v, 0) , money_fmt(v), ha="center", va="bottom", fontsize=8, color=p.text)
            running += v
        self.ax.bar(len(labels) - 1, running, color=p.chart_series[0])
        lo = min(start, running) * 0.97
        hi = max(start, running) * 1.015
        self.ax.set_ylim(lo, hi)
        self.ax.set_xticks(range(len(labels)))
        self.ax.set_xticklabels(labels)
        self.ax.yaxis.set_major_formatter(FuncFormatter(money_fmt))
        self.finish(legend=False, title=title)
