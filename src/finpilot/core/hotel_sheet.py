"""Layout of the 12-month hotel revenue model used in the Modeling Lab.

The same layout drives the guided build project, the Excel export and the
tests, so the row numbers below are the single source of truth.
"""
from __future__ import annotations

from .formula.refs import col_to_letters
from .hotel import MONTHS, HotelAssumptions, compute, default_budget, default_forecast
from .sheet import Sheet

FIRST_COL = 1           # column B = January
LAST_COL = 12           # column M = December
TOTAL_COL = 13          # column N = full year
MONTH_COLS = [col_to_letters(c) for c in range(FIRST_COL, LAST_COL + 1)]   # B..M
TOT = col_to_letters(TOTAL_COL)                                          # N

R_TITLE, R_SUB = 1, 2
R_ROOMS, R_YEAR = 4, 5
R_HEAD = 7
R_MONTHNO, R_DAYS = 8, 9
R_OCC, R_ADR, R_FB, R_OTHER = 10, 11, 12, 13
R_AVAIL, R_SOLD, R_RREV, R_REVPAR, R_FBREV, R_OREV, R_TREV = 15, 16, 17, 18, 19, 20, 21
R_BUDGET, R_VAR, R_VARPCT = 23, 24, 25
R_CHK1, R_CHK2, R_CHK3 = 27, 28, 29

# Reference formulas for column B; other months are the same formula filled right.
REFERENCE = {
    R_DAYS: "=DAY(EOMONTH(DATE($B$5,B8,1),0))",
    R_AVAIL: "=$B$4*B9",
    R_SOLD: "=B15*B10",
    R_RREV: "=B16*B11",
    R_REVPAR: "=IF(B15=0,NA(),B17/B15)",
    R_FBREV: "=B16*B12",
    R_OREV: "=B17*B13",
    R_TREV: "=B17+B19+B20",
    R_VAR: "=B17-B23",
    R_VARPCT: "=IF(B23=0,NA(),B24/B23)",
    R_CHK1: '=IF(COUNT(B18)=0,"not built",ABS(B18-B11*B10)<0.000001)',
    R_CHK2: '=IF(COUNT(B16,B15)<2,"not built",B16<=B15)',
}
TOTAL_REFERENCE = {
    R_DAYS: "=SUM(B9:M9)",
    R_OCC: "=N16/N15",
    R_ADR: "=IF(N16=0,NA(),N17/N16)",
    R_AVAIL: "=SUM(B15:M15)",
    R_SOLD: "=SUM(B16:M16)",
    R_RREV: "=SUM(B17:M17)",
    R_REVPAR: "=N17/N15",
    R_FBREV: "=SUM(B19:M19)",
    R_OREV: "=SUM(B20:M20)",
    R_TREV: "=SUM(B21:M21)",
    R_BUDGET: "=SUM(B23:M23)",
    R_VAR: "=N17-N23",
    R_VARPCT: "=IF(N23=0,NA(),N24/N23)",
    R_CHK3: '=IF(COUNT(N21)=0,"not built",ABS(N21-SUM(B21:M21))<0.01)',
}

LABELS = {
    R_ROOMS: "Rooms in hotel", R_YEAR: "Model year", R_MONTHNO: "Month number",
    R_DAYS: "Days in month", R_OCC: "Occupancy %", R_ADR: "ADR ($)",
    R_FB: "F&B spend per occupied room ($)", R_OTHER: "Other revenue (% of room revenue)",
    R_AVAIL: "Available room nights", R_SOLD: "Rooms sold", R_RREV: "Room revenue ($)",
    R_REVPAR: "RevPAR ($)", R_FBREV: "F&B revenue ($)", R_OREV: "Other operating revenue ($)",
    R_TREV: "Total operating revenue ($)", R_BUDGET: "Budget room revenue ($)",
    R_VAR: "Variance vs budget ($)", R_VARPCT: "Variance vs budget (%)",
    R_CHK1: "Check: RevPAR = ADR x Occupancy", R_CHK2: "Check: rooms sold <= available",
    R_CHK3: "Check: annual total = sum of months",
}
FORMATS = {
    R_OCC: "percent", R_ADR: "currency", R_FB: "currency", R_OTHER: "percent",
    R_AVAIL: "number0", R_SOLD: "number0", R_RREV: "currency0", R_REVPAR: "currency",
    R_FBREV: "currency0", R_OREV: "currency0", R_TREV: "currency0", R_BUDGET: "currency0",
    R_VAR: "currency0", R_VARPCT: "percent", R_DAYS: "number0", R_MONTHNO: "number0",
}
OUTPUT_ROWS = {R_RREV, R_REVPAR, R_TREV, R_VAR, R_VARPCT}
CHECK_ROWS = {R_CHK1, R_CHK2, R_CHK3}


def a1(row: int, col_letter: str) -> str:
    return f"{col_letter}{row}"


def shifted_formula(formula_b: str, col_letter: str) -> str:
    from .formula import parse, shift, to_formula
    from .formula.refs import letters_to_col
    node = parse(formula_b)
    return "=" + to_formula(shift(node, 0, letters_to_col(col_letter) - FIRST_COL))


def build_sheet(a: HotelAssumptions | None = None, budget: HotelAssumptions | None = None,
                include_calcs: bool = False, upto_row: int | None = None) -> Sheet:
    """Create the hotel model sheet.

    include_calcs=False leaves calculation rows empty for the learner to build
    (days in month and checks are pre-filled so the structure is visible).
    """
    a = a or default_forecast()
    budget = budget or default_budget()
    budget_res = compute(budget)
    s = Sheet("Hotel Revenue Model", rows=32, cols=15)
    items = [
        ("A1", f"{a.hotel_name} - 12-month revenue model ({a.scenario})", "label", None, None),
        ("A2", f"All figures fictional. Currency: {a.currency}. Inputs are blue cells; calculations black.",
         "label", None, None),
        ("A4", LABELS[R_ROOMS], "label", None, None),
        ("B4", str(a.rooms), "input", "number0", "Room count from the property fact sheet (fictional)."),
        ("A5", LABELS[R_YEAR], "label", None, None),
        ("B5", str(a.year), "input", "general", "Calendar year being modelled."),
        ("A7", "Line item", "label", None, None),
        (a1(R_HEAD, TOT), "Full year", "label", None, None),
    ]
    for i, col in enumerate(MONTH_COLS):
        m = a.months[i]
        items += [
            (a1(R_HEAD, col), MONTHS[i], "label", None, None),
            (a1(R_MONTHNO, col), str(i + 1), "input", "number0", None),
            (a1(R_DAYS, col), shifted_formula(REFERENCE[R_DAYS], col), "calc", "number0", None),
            (a1(R_OCC, col), repr(round(m.occupancy, 6)), "input", "percent", None),
            (a1(R_ADR, col), repr(round(m.adr, 4)), "input", "currency", None),
            (a1(R_FB, col), repr(round(m.fb_per_occupied_room, 4)), "input", "currency", None),
            (a1(R_OTHER, col), repr(round(m.other_pct, 6)), "input", "percent", None),
            (a1(R_BUDGET, col), repr(round(budget_res.months[i].room_revenue, 2)), "input", "currency0", None),
        ]
    for r, lab in LABELS.items():
        if r not in (R_ROOMS, R_YEAR):
            items.append((f"A{r}", lab, "label", None, None))
    items.append(("A14", "Calculations", "label", None, None))
    items.append(("A22", "Budget comparison", "label", None, None))
    items.append(("A26", "Model checks", "label", None, None))
    items.append(("O4", "Notes", "label", None, None))
    items.append(("O5", "Annual occupancy, ADR and RevPAR are weighted (from totals), never averaged.",
                  "label", None, None))
    # Notes and source documentation on the input rows
    notes = {R_OCC: "Forecast occupancy by month (fictional seasonal profile).",
             R_ADR: "Forecast average daily rate by month (fictional).",
             R_FB: "Average food & beverage spend per occupied room night (fictional).",
             R_OTHER: "Spa, parking, resort fees etc. as % of room revenue (simplified).",
             R_BUDGET: "Approved budget room revenue (fictional)."}
    for r, n in notes.items():
        items.append((a1(r, "B"), None, None, None, n))

    rows_to_fill = [R_CHK1, R_CHK2]
    if include_calcs:
        rows_to_fill = [r for r in REFERENCE if r != R_DAYS]
    for r in rows_to_fill:
        if upto_row is not None and r > upto_row and r not in CHECK_ROWS:
            continue
        for col in MONTH_COLS:
            role = "check" if r in CHECK_ROWS else ("output" if r in OUTPUT_ROWS else "calc")
            items.append((a1(r, col), shifted_formula(REFERENCE[r], col), role, FORMATS.get(r, "general"), None))
    total_rows = list(TOTAL_REFERENCE) if include_calcs else [R_DAYS, R_BUDGET, R_CHK3]
    for r in total_rows:
        role = "check" if r in CHECK_ROWS else ("output" if r in OUTPUT_ROWS else "calc")
        items.append((a1(r, TOT), TOTAL_REFERENCE[r], role, FORMATS.get(r, "general"), None))
    # Cells the learner still has to build get their role and number format up front, so a
    # formula typed there displays like the finished model (e.g. $902,956 rather than 902955.6).
    filled = {it[0] for it in items}
    for r in list(REFERENCE) + list(TOTAL_REFERENCE):
        cols = list(MONTH_COLS) if r in REFERENCE else []
        if r in TOTAL_REFERENCE:
            cols.append(TOT)
        for col in cols:
            if a1(r, col) not in filled:
                role = "check" if r in CHECK_ROWS else ("output" if r in OUTPUT_ROWS else "calc")
                items.append((a1(r, col), None, role, FORMATS.get(r, "general"), None))
    s.set_many(items, record=False)
    s.names["ROOMS"] = "B4"
    s.recalculate()
    return s


def write_assumptions(sheet: Sheet, a: HotelAssumptions, record: bool = True) -> None:
    """Push assumption values into the model sheet's input rows (keeps formulas intact)."""
    items = [("B4", str(a.rooms)), ("B5", str(a.year))]
    for i, col in enumerate(MONTH_COLS):
        m = a.months[i]
        items += [(a1(R_OCC, col), repr(round(m.occupancy, 6))), (a1(R_ADR, col), repr(round(m.adr, 4))),
                  (a1(R_FB, col), repr(round(m.fb_per_occupied_room, 4))),
                  (a1(R_OTHER, col), repr(round(m.other_pct, 6)))]
    sheet.set_many(items, record=record)


def write_budget(sheet: Sheet, budget: HotelAssumptions, record: bool = True) -> None:
    res = compute(budget)
    sheet.set_many([(a1(R_BUDGET, col), repr(round(res.months[i].room_revenue, 2)))
                    for i, col in enumerate(MONTH_COLS)], record=record)
