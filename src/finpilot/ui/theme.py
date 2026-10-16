"""FinPilot design system: colour tokens, typography and Qt style sheets."""
from __future__ import annotations

import sys
from dataclasses import dataclass

BRAND = {
    "navy": "#101D2B",
    "teal": "#59D6C0",
    "amber": "#F3B65B",
    "cream": "#F5F1E8",
    "coral": "#E0675A",
}


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str            # window background
    surface: str       # panels
    surface_alt: str   # subtle raised areas / zebra rows
    sidebar: str
    sidebar_text: str
    sidebar_active: str
    text: str
    muted: str
    border: str
    accent: str        # teal fill
    accent_text: str   # teal used as text on bg (contrast-safe)
    on_accent: str
    amber: str
    amber_soft: str
    coral: str
    coral_soft: str
    success: str
    success_soft: str
    input_text: str
    input_bg: str
    output_bg: str
    grid_line: str
    chart_series: tuple


LIGHT = Palette(
    name="light", bg="#F5F1E8", surface="#FCFAF5", surface_alt="#EFE9DC", sidebar="#101D2B",
    sidebar_text="#C9D3DD", sidebar_active="#59D6C0", text="#17212E", muted="#5B6675", border="#DDD5C4",
    accent="#59D6C0", accent_text="#16806E", on_accent="#0B1620", amber="#F3B65B", amber_soft="#FBEBD0",
    coral="#C8493C", coral_soft="#F8DDD8", success="#1E8C6A", success_soft="#D7F1E8", input_text="#1F4FBF",
    input_bg="#FFF6E2", output_bg="#E3F6F1", grid_line="#E6E0D3",
    chart_series=("#16806E", "#F3B65B", "#5B6675", "#C8493C", "#7A8FD6"),
)

DARK = Palette(
    name="dark", bg="#0E1824", surface="#142131", surface_alt="#1A2A3D", sidebar="#0A121C",
    sidebar_text="#9FB0C1", sidebar_active="#59D6C0", text="#E7EDF3", muted="#9AA8B6", border="#263A50",
    accent="#59D6C0", accent_text="#59D6C0", on_accent="#0B1620", amber="#F3B65B", amber_soft="#3A3020",
    coral="#F08A7E", coral_soft="#3B2224", success="#5FD3A8", success_soft="#17352C", input_text="#8FB2FF",
    input_bg="#1E2A3A", output_bg="#163330", grid_line="#22344A",
    chart_series=("#59D6C0", "#F3B65B", "#9AA8B6", "#F08A7E", "#8FB2FF"),
)

_current = LIGHT


def palette() -> Palette:
    return _current


def set_theme(name: str) -> Palette:
    global _current
    _current = DARK if name == "dark" else LIGHT
    return _current


def font_family() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    return "DejaVu Sans"


def stylesheet(p: Palette | None = None) -> str:
    p = p or _current
    f = font_family()
    return f"""
* {{ font-family: "{f}"; }}
QWidget {{ color: {p.text}; font-size: 10pt; }}
QMainWindow, QWidget#Page, QScrollArea#PageScroll, QWidget#PageInner {{ background: {p.bg}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {p.sidebar}; color: #FFFFFF; border: 1px solid {p.accent}; padding: 6px; }}

/* Sidebar */
QFrame#Sidebar {{ background: {p.sidebar}; }}
QLabel#Brand {{ color: #FFFFFF; font-size: 15pt; font-weight: 700; }}
QLabel#Tagline {{ color: {p.amber}; font-size: 8pt; font-style: italic; }}
QPushButton#NavButton {{ text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    color: {p.sidebar_text}; background: transparent; font-size: 10pt; }}
QPushButton#NavButton:hover {{ background: rgba(89,214,192,0.10); color: #FFFFFF; }}
QPushButton#NavButton:checked {{ background: rgba(89,214,192,0.16); color: {p.sidebar_active}; font-weight: 600; }}
QLabel#NavSection {{ color: #6F8195; font-size: 8pt; letter-spacing: 1px; padding: 10px 14px 2px 14px; }}

/* Typography */
QLabel#H1 {{ font-size: 20pt; font-weight: 700; color: {p.text}; }}
QLabel#H2 {{ font-size: 13.5pt; font-weight: 650; color: {p.text}; }}
QLabel#H3 {{ font-size: 11pt; font-weight: 650; color: {p.text}; }}
QLabel#Eyebrow {{ font-size: 8.5pt; font-weight: 700; color: {p.accent_text}; letter-spacing: 1px; }}
QLabel#Muted {{ color: {p.muted}; }}
QLabel#Body {{ font-size: 10.5pt; line-height: 140%; }}
QLabel#Big {{ font-size: 19pt; font-weight: 700; }}
QLabel#Formula {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; background: {p.surface_alt};
    border-radius: 6px; padding: 6px 10px; }}

/* Surfaces */
QFrame#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame#Hero {{ background: {p.sidebar}; border-radius: 16px; }}
QFrame#Hero QLabel {{ color: #FFFFFF; }}
QFrame#Hero QLabel#Muted {{ color: #AFC0CF; }}
QFrame#Callout {{ background: {p.amber_soft}; border-left: 4px solid {p.amber}; border-radius: 8px; }}
QFrame#FeedbackGood {{ background: {p.success_soft}; border-left: 4px solid {p.success}; border-radius: 8px; }}
QFrame#FeedbackBad {{ background: {p.coral_soft}; border-left: 4px solid {p.coral}; border-radius: 8px; }}
QFrame#FeedbackInfo {{ background: {p.surface_alt}; border-left: 4px solid {p.accent}; border-radius: 8px; }}
QFrame#Divider {{ background: {p.border}; max-height: 1px; min-height: 1px; }}

/* Buttons */
QPushButton {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 7px 14px; }}
QToolButton {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 7px 14px; color: {p.text}; }}
QToolButton::menu-indicator {{ image: none; }}
QPushButton:hover {{ border-color: {p.accent}; }}
QPushButton:disabled {{ color: {p.muted}; background: {p.surface_alt}; }}
QPushButton#Primary {{ background: {p.accent}; color: {p.on_accent}; border: none; font-weight: 650; }}
QPushButton#Primary:hover {{ background: #4CC7B1; }}
QPushButton#Primary:disabled {{ background: {p.border}; color: {p.muted}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.accent_text}; font-weight: 600; padding: 6px 8px; }}
QPushButton#Ghost:hover {{ text-decoration: underline; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {p.coral}; color: {p.coral}; }}
QPushButton#Choice {{ text-align: left; padding: 10px 14px; background: {p.surface}; }}
QPushButton#Choice:checked {{ border: 2px solid {p.accent}; background: {p.output_bg}; }}
QPushButton#Chip {{ border-radius: 13px; padding: 4px 12px; background: {p.surface_alt}; border: none; }}
QPushButton#Chip:checked {{ background: {p.accent}; color: {p.on_accent}; }}

/* Inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 7px; padding: 6px 8px;
    selection-background-color: {p.accent}; selection-color: {p.on_accent}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p.accent}; }}
QSpinBox, QDoubleSpinBox {{ min-height: 20px; padding: 4px 6px; }}
QLineEdit#FormulaBar {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 10.5pt; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border}; selection-background-color: {p.output_bg}; selection-color: {p.text}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {p.surface}; border: 2px solid {p.accent}; width: 14px; height: 14px; margin: -6px 0; border-radius: 8px; }}

/* Tables */
QTableView, QTableWidget, QListWidget, QTreeWidget {{ background: {p.surface}; border: 1px solid {p.border};
    border-radius: 8px; gridline-color: {p.grid_line}; selection-background-color: {p.output_bg};
    selection-color: {p.text}; alternate-background-color: {p.surface_alt}; }}
QHeaderView::section {{ background: {p.surface_alt}; color: {p.muted}; border: none;
    border-right: 1px solid {p.grid_line}; border-bottom: 1px solid {p.grid_line}; padding: 4px 6px; font-weight: 600; }}
QTableCornerButton::section {{ background: {p.surface_alt}; border: none; }}
QListWidget::item {{ padding: 8px; border-bottom: 1px solid {p.grid_line}; }}
QListWidget::item:selected {{ background: {p.output_bg}; color: {p.text}; }}

/* Tabs & progress */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {p.muted}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; font-weight: 600; }}
QProgressBar {{ background: {p.surface_alt}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {p.surface}; color: {p.muted}; border-top: 1px solid {p.border}; }}
QMenuBar {{ background: {p.surface}; border-bottom: 1px solid {p.border}; }}
QMenuBar::item:selected {{ background: {p.output_bg}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; }}
QMenu::item:selected {{ background: {p.output_bg}; color: {p.text}; }}
QSplitter::handle {{ background: {p.border}; }}
"""
