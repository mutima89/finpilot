"""Number formatting shared by the UI and exports."""
from __future__ import annotations

import math
from typing import Any

from .formula.errors import CellError

CURRENCY = "$"


def format_value(v: Any, fmt: str = "general", currency: str | None = None) -> str:
    cur = CURRENCY if currency is None else currency
    if v is None:
        return ""
    if isinstance(v, CellError):
        return v.code
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return v
    if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
        return str(v)
    x = float(v)
    neg = x < 0
    a = abs(x)
    if fmt == "percent":
        s = f"{a * 100:,.1f}%"
    elif fmt == "percent0":
        s = f"{a * 100:,.0f}%"
    elif fmt == "currency":
        s = f"{cur}{a:,.2f}"
    elif fmt == "currency0":
        s = f"{cur}{a:,.0f}"
    elif fmt == "number":
        s = f"{a:,.2f}"
    elif fmt == "number0":
        s = f"{a:,.0f}"
    elif fmt == "date":
        try:
            from .formula.functions import serial_to_date
            return serial_to_date(x).strftime("%d %b %Y")
        except Exception:
            s = f"{a:g}"
    else:
        if a != 0 and (a >= 1e12 or a < 1e-6):
            s = f"{a:.4e}"
        elif float(a).is_integer():
            s = f"{a:.0f}"  # Excel's General format has no thousands separator
        else:
            s = f"{a:.6f}".rstrip("0").rstrip(".")
    if neg and fmt in ("currency", "currency0", "number", "number0"):
        return f"({s})"  # accounting style
    return ("-" if neg else "") + s


def fmt_opt(v, fmt: str = "general", na: str = "n/a") -> str:
    """Format a value that may be None (undefined, e.g. zero denominator)."""
    return na if v is None else format_value(v, fmt)
