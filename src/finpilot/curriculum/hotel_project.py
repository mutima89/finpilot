"""Guided project: build the 12-month hotel revenue model in the Modeling Lab.

The learner fills in each calculation row. Every task is checked by behaviour:
the learner's cells are compared with reference formulas on the original
inputs and on perturbed inputs (more rooms, different occupancy and rates),
which catches hard-coded numbers and broken absolute references. The finished
model is additionally verified against the independent Python hotel model in
``core.hotel`` (not the formula engine), so a passing model is genuinely right.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..core import hotel_sheet as hs
from ..core.formula import CellError, parse, shift, to_formula
from ..core.formula.parser import numeric_literals
from ..core.formula.refs import a1_to_key
from ..core.hotel import HotelAssumptions, MonthInput, compute
from ..core.sheet import Sheet
from .grading import Feedback


@dataclass
class LabTask:
    id: str
    title: str
    instruction: str
    cells: list[str]                         # target cells the learner must fill
    reference: dict[str, str]                # cell -> reference formula
    hints: list[str]
    solution: str
    why: str = ""
    accept_alternatives: list[dict[str, str]] = field(default_factory=list)


def _row_task(tid: str, title: str, row: int, instruction: str, hints: list[str], why: str) -> LabTask:
    ref = {f"{c}{row}": hs.shifted_formula(hs.REFERENCE[row], c) for c in hs.MONTH_COLS}
    return LabTask(tid, title, instruction, list(ref), ref, hints,
                   f"In B{row} type {hs.REFERENCE[row]} then use Fill right to copy it to M{row}.", why)


def _total_task(tid: str, title: str, rows: list[int], instruction: str, hints: list[str], why: str) -> LabTask:
    ref = {f"{hs.TOT}{r}": hs.TOTAL_REFERENCE[r] for r in rows}
    sol = "; ".join(f"{k}: {v}" for k, v in ref.items())
    return LabTask(tid, title, instruction, list(ref), ref, hints, sol, why)


TASKS: list[LabTask] = [
    _row_task("T1", "Available room nights", hs.R_AVAIL,
              "Row 15: available room nights = rooms in the hotel (B4) × days in the month (row 9). "
              "Write it in B15 so it can be filled right to M15.",
              ["Rooms × days. The room count is a single assumption every month uses.",
               "Anchor the room count with $: $B$4. Keep the days reference relative: B9.",
               "B15: =$B$4*B9, then Fill right to M15."],
              "Capacity is the denominator of occupancy and RevPAR, so it must reflect each month's length."),
    _row_task("T2", "Rooms sold", hs.R_SOLD,
              "Row 16: rooms sold = available room nights (row 15) × occupancy (row 10).",
              ["Volume = capacity × occupancy.", "B16: =B15*B10, then Fill right."],
              "Rooms sold is the volume driver for room revenue and for F&B."),
    _row_task("T3", "Room revenue", hs.R_RREV,
              "Row 17: room revenue = rooms sold (row 16) × ADR (row 11).",
              ["Revenue = volume × price.", "B17: =B16*B11, then Fill right."],
              "Room revenue = Rooms Sold × ADR."),
    _row_task("T4", "RevPAR", hs.R_REVPAR,
              "Row 18: RevPAR = room revenue (row 17) / available room nights (row 15). Handle a month with "
              "zero capacity honestly (a plain division is accepted; IF(...=0,NA(),...) is better practice).",
              ["Divide room revenue by AVAILABLE rooms, not rooms sold.",
               "B18: =IF(B15=0,NA(),B17/B15) (or =B17/B15), then Fill right."],
              "RevPAR combines price and occupancy; check row 27 confirms RevPAR = ADR × Occupancy."),
    _row_task("T5", "F&B revenue", hs.R_FBREV,
              "Row 19: F&B revenue = rooms sold (row 16) × F&B spend per occupied room (row 12).",
              ["F&B is driven by occupied rooms.", "B19: =B16*B12, then Fill right."],
              "Driver-based ancillary revenue moves with occupancy."),
    _row_task("T6", "Other operating revenue", hs.R_OREV,
              "Row 20: other revenue = room revenue (row 17) × other-revenue % (row 13).",
              ["A percentage of room revenue.", "B20: =B17*B13, then Fill right."],
              "A simplification: spa, parking and fees scale with room revenue."),
    _row_task("T7", "Total operating revenue", hs.R_TREV,
              "Row 21: total operating revenue = room + F&B + other revenue (rows 17, 19, 20). Do not include "
              "RevPAR (row 18): it is a ratio, not revenue.",
              ["Add the three revenue streams only.", "B21: =B17+B19+B20, then Fill right."],
              "Total revenue must not double count or include KPIs."),
    _total_task("T8", "Full-year totals", [hs.R_AVAIL, hs.R_SOLD, hs.R_RREV, hs.R_FBREV, hs.R_OREV, hs.R_TREV],
                "Column N: full-year totals for rows 15, 16, 17, 19, 20 and 21 (sum of January-December).",
                ["Use SUM over B:M of the same row.", "N15: =SUM(B15:M15); repeat for rows 16, 17, 19, 20, 21."],
                "Volume and revenue lines add across months."),
    _total_task("T9", "Weighted annual KPIs", [hs.R_OCC, hs.R_ADR, hs.R_REVPAR],
                "N10, N11, N18: annual occupancy, ADR and RevPAR, calculated from the annual totals - never "
                "by averaging the monthly percentages.",
                ["Occupancy = total rooms sold / total available: N10 = N16/N15.",
                 "ADR = total room revenue / total rooms sold: N11 = N17/N16. RevPAR: N18 = N17/N15.",
                 "Avoid AVERAGE(B10:M10): months differ in length and volume."],
                "Weighted KPIs respect each month's capacity and volume."),
    LabTask("T10", "Variance against budget",
            "Row 24: room revenue variance vs budget (row 17 - row 23) for each month and the year (B24:N24). "
            "Row 25: variance % of budget (B25:N25).",
            [f"{c}24" for c in hs.MONTH_COLS + [hs.TOT]] + [f"{c}25" for c in hs.MONTH_COLS + [hs.TOT]],
            {**{f"{c}24": hs.shifted_formula(hs.REFERENCE[hs.R_VAR], c) for c in hs.MONTH_COLS},
             f"{hs.TOT}24": hs.TOTAL_REFERENCE[hs.R_VAR],
             **{f"{c}25": hs.shifted_formula(hs.REFERENCE[hs.R_VARPCT], c) for c in hs.MONTH_COLS},
             f"{hs.TOT}25": hs.TOTAL_REFERENCE[hs.R_VARPCT]},
            ["Variance = forecast - budget, so positive is favourable for revenue.",
             "B24: =B17-B23; B25: =IF(B23=0,NA(),B24/B23). Fill right to N."],
            "B24 =B17-B23, B25 =IF(B23=0,NA(),B24/B23), filled right to column N.",
            "Comparing the forecast with budget shows where and why the year is off plan."),
]


def task(tid: str) -> LabTask:
    for t in TASKS:
        if t.id == tid:
            return t
    raise KeyError(tid)


# ----------------------------------------------------------------- checking

INPUT_PERTURBATIONS: list[dict[str, str]] = [
    {"B4": "200"},
    {"C10": "0.5", "H11": "455", "E12": "120", "K13": "0.1"},
    {"B5": "2028", "M10": "0.91", "B11": "301"},
]


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, CellError) or isinstance(b, CellError):
        return isinstance(a, CellError) and isinstance(b, CellError) and a.code == b.code
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    return a == b


def _copy(sheet: Sheet, overrides: dict[str, str] | None) -> Sheet:
    s = Sheet.from_dict(sheet.to_dict())
    if overrides:
        s.set_many(list(overrides.items()), record=False)
    return s


def check_task(sheet: Sheet, t: LabTask) -> Feedback:
    empty = [c for c in t.cells if not sheet.raw(c).strip()]
    if len(empty) == len(t.cells):
        return Feedback(False, "Nothing entered yet", f"Start with {t.cells[0]}. {t.instruction}", "empty")
    if empty:
        listed = ", ".join(empty[:6]) + (" ..." if len(empty) > 6 else "")
        return Feedback(False, "Some cells are still empty",
                        f"Fill these cells too: {listed}. Tip: select the first cell and use Fill right.",
                        "incomplete", 1 - len(empty) / len(t.cells))
    typed = [c for c in t.cells if not sheet.raw(c).startswith("=")]
    if typed:
        return Feedback(False, "Typed numbers instead of formulas",
                        f"{', '.join(typed[:4])} contain typed values. Model cells must be formulas that link to "
                        "the inputs, otherwise they will not update when assumptions change.", "hardcoded_value", 0.2)
    errors = {c: sheet.value(c) for c in t.cells if isinstance(sheet.value(c), CellError)}
    ref_errors = _reference_values(sheet, t, None)
    real_errors = {c: e for c, e in errors.items() if not isinstance(ref_errors.get(c), CellError)}
    if real_errors:
        c, e = next(iter(real_errors.items()))
        return Feedback(False, f"{c} shows {e.code}", f"{e.explanation} Select {c} and use Explain to trace it.",
                        "error_value", 0.2)

    for idx, ov in enumerate([None] + INPUT_PERTURBATIONS):
        learner = _copy(sheet, ov)
        expected = _reference_values(sheet, t, ov)
        wrong = [c for c in t.cells if not _equal(learner.value(c), expected[c])]
        if wrong:
            return _diagnose(sheet, t, wrong, learner, expected, idx, ov)

    notes = []
    inconsistent = _inconsistent_rows(sheet, t)
    if inconsistent:
        notes.append("Formulas in " + ", ".join(inconsistent) + " give the right results but are written "
                     "differently from column B. Professional models keep one formula per row.")
    if t.id == "T9":
        for c in ("N10", "N11", "N18"):
            if "AVERAGE" in sheet.raw(c).upper():
                return Feedback(False, "Do not average the months",
                                f"{c} uses AVERAGE. It happens to be close, but annual ratios must be weighted: "
                                "recompute them from the annual totals.", "average_of_ratios", 0.5)
    return Feedback(True, "Task complete", t.why + " Checked on the original inputs and on three changed "
                    "sets of inputs.", "correct", 1.0, notes)


def _reference_values(sheet: Sheet, t: LabTask, ov) -> dict[str, Any]:
    ref = _copy(sheet, ov)
    ref.set_many(list(t.reference.items()), record=False)
    return {c: ref.value(c) for c in t.cells}


def _inconsistent_rows(sheet: Sheet, t: LabTask) -> list[str]:
    rows: dict[int, list[str]] = {}
    for c in t.cells:
        r, col = a1_to_key(c)
        if hs.FIRST_COL <= col <= hs.LAST_COL:
            rows.setdefault(r, []).append(c)
    bad = []
    for r, cells in rows.items():
        base = None
        for c in cells:
            try:
                node = parse(sheet.raw(c))
            except Exception:
                continue
            norm = to_formula(shift(node, 0, hs.FIRST_COL - a1_to_key(c)[1]))
            if base is None:
                base = norm
            elif norm != base:
                bad.append(f"row {r + 1}")
                break
    return bad


def _diagnose(sheet, t, wrong, learner, expected, idx, ov) -> Feedback:
    from ..core.format import format_value
    c = wrong[0]
    fmt = sheet.get(a1_to_key(c)).fmt
    got, exp = learner.value(c), expected[c]
    shown = f"{c} shows {format_value(got, fmt)} but should be {format_value(exp, fmt)}"
    if idx > 0:
        changed = ", ".join(f"{k} = {v}" for k, v in ov.items())
        raw = sheet.raw(c)
        try:
            literals = [x for x in numeric_literals(parse(raw)) if x not in (0, 1)]
        except Exception:
            literals = []
        if literals:
            return Feedback(False, "A typed number is hiding in the formula",
                            f"With changed inputs ({changed}), {shown}. The formula in {c} contains "
                            f"{', '.join(f'{x:g}' for x in literals[:3])}; replace it with a reference to the "
                            "input cell.", "hardcoded", 0.5)
        if "B4" in raw.replace("$", "") and "$B$4" not in raw and "$B4" not in raw:
            return Feedback(False, "The room count is not anchored",
                            f"After changing inputs ({changed}), {shown}. Anchor the room count as $B$4 so "
                            "every month uses it.", "absolute_ref", 0.5)
        return Feedback(False, "Right today, wrong when inputs change",
                        f"With changed inputs ({changed}), {shown}. Some cells contain typed numbers or link to "
                        "the wrong input. Replace typed values with references.", "hardcoded", 0.5)
    first_month = f"B{a1_to_key(c)[0] + 1}"
    if c != first_month and first_month in t.cells and first_month not in wrong:
        return Feedback(False, "January works, later months do not",
                        f"{shown}. When the formula was copied right, a reference that should stay fixed moved "
                        "(or a cell was edited by hand). Check absolute references ($) and re-fill the row.",
                        "absolute_ref", 0.5)
    if isinstance(got, (int, float)) and isinstance(exp, (int, float)) and exp:
        ratio = got / exp
        if math.isclose(abs(ratio), 100, rel_tol=0.01) or math.isclose(abs(ratio), 0.01, rel_tol=0.01):
            return Feedback(False, "Percentage scale", f"{shown}: 100 times off. Percentages are already decimals.",
                            "percent_scale", 0.3)
        if math.isclose(ratio, -1, rel_tol=1e-6):
            return Feedback(False, "Sign reversed", f"{shown}. Subtract budget from forecast, not the reverse.",
                            "sign", 0.3)
    hint = t.hints[0] if t.hints else ""
    return Feedback(False, "Not the expected result", f"{shown}. {hint}", "wrong",
                    1 - len(wrong) / len(t.cells))


# ------------------------------------------------------- final validation


def assumptions_from_sheet(sheet: Sheet) -> HotelAssumptions:
    def num(a1):
        v = sheet.value(a1)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"{a1} must be a number")
        return float(v)
    months = [MonthInput(num(f"{c}{hs.R_OCC}"), num(f"{c}{hs.R_ADR}"), num(f"{c}{hs.R_FB}"),
                         num(f"{c}{hs.R_OTHER}")) for c in hs.MONTH_COLS]
    return HotelAssumptions(rooms=int(num("B4")), year=int(num("B5")), months=months, scenario="From Lab")


def independent_verification(sheet: Sheet) -> list[tuple[str, bool, str]]:
    """Compare the learner's model with the independent Python implementation."""
    out: list[tuple[str, bool, str]] = []
    try:
        a = assumptions_from_sheet(sheet)
        res = compute(a)
    except ValueError as e:
        return [("Inputs readable", False, str(e))]
    rows = [(hs.R_AVAIL, "available"), (hs.R_SOLD, "rooms_sold"), (hs.R_RREV, "room_revenue"),
            (hs.R_REVPAR, "revpar"), (hs.R_FBREV, "fb_revenue"), (hs.R_OREV, "other_revenue"),
            (hs.R_TREV, "total_revenue")]
    for row, attr in rows:
        bad = []
        for i, c in enumerate(hs.MONTH_COLS):
            v = sheet.value(f"{c}{row}")
            e = getattr(res.months[i], attr)
            if e is None:
                ok = isinstance(v, CellError) and v.code in ("#N/A", "#DIV/0!")
            else:
                ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isclose(
                    v, e, rel_tol=1e-9, abs_tol=1e-6)
            if not ok:
                bad.append(c)
        label = hs.LABELS[row]
        out.append((label, not bad, "Matches the independent calculation for all 12 months." if not bad else
                    "Differs in " + ", ".join(bad[:5])))
    t = res.total
    for a1, e, label in ((f"N{hs.R_OCC}", t.occupancy, "Annual occupancy (weighted)"),
                         (f"N{hs.R_ADR}", t.adr, "Annual ADR (weighted)"),
                         (f"N{hs.R_REVPAR}", t.revpar, "Annual RevPAR"),
                         (f"N{hs.R_TREV}", t.total_revenue, "Annual total revenue")):
        v = sheet.value(a1)
        ok = e is not None and isinstance(v, (int, float)) and math.isclose(v, e, rel_tol=1e-9, abs_tol=1e-6)
        out.append((label, ok, "Matches." if ok else f"{a1} does not match the independent result."))
    return out


def project_status(sheet: Sheet) -> dict:
    results = {t.id: check_task(sheet, t) for t in TASKS}
    verification = independent_verification(sheet) if all(f.correct for f in results.values()) else []
    checks_ok = all(sheet.value(f"{c}{r}") is True for r in (hs.R_CHK1, hs.R_CHK2) for c in hs.MONTH_COLS) \
        and sheet.value(f"{hs.TOT}{hs.R_CHK3}") is True
    no_errors = not sheet.errors()
    validated = bool(verification) and all(ok for _, ok, _ in verification) and checks_ok and no_errors
    return {"tasks": results, "verification": verification, "checks_ok": checks_ok, "no_errors": no_errors,
            "validated": validated,
            "done": sum(1 for f in results.values() if f.correct), "total": len(TASKS)}
