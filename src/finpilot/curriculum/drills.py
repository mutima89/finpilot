"""Parameterised formula drills for Formula Practice.

Each generator returns a question dict compatible with ``FormulaQuestion``.
Numbers are randomised (seeded) so learners practise the logic, not the answer.
"""
from __future__ import annotations

import random
from typing import Callable

DRILLS: dict[str, tuple[str, str, Callable[[random.Random], dict]]] = {}


def drill(key: str, topic: str, title: str):
    def deco(fn):
        DRILLS[key] = (topic, title, fn)
        return fn
    return deco


TOPICS = {"kpis": "Hotel KPIs", "refs": "References", "logic": "Logic & errors", "lookups": "Lookups & sums",
          "growth": "Growth & variance", "costs": "Costs & margins"}


@drill("occupancy", "kpis", "Occupancy")
def _occ(r: random.Random) -> dict:
    rooms, days = r.choice([120, 150, 180, 210, 250]), r.choice([28, 30, 31])
    sold = int(rooms * days * r.uniform(0.55, 0.92))
    return {"kind": "formula", "question": f"In <b>B4</b>, calculate occupancy. The hotel has {rooms} rooms "
            f"and the month has {days} days.", "target": "B4", "reference": "=B3/(B1*B2)", "fmt": "percent",
            "cells": {"A1": "Rooms", "B1": str(rooms), "A2": "Days", "B2": str(days), "A3": "Rooms sold",
                      "B3": str(sold), "A4": "Occupancy"},
            "perturb": [{"B3": str(sold - 300)}, {"B1": str(rooms + 20)}, {"B2": "30" if days != 30 else "31"}],
            "hints": ["Occupancy = rooms sold / available room nights.", "Available = rooms × days."],
            "solution": "=B3/(B1*B2)"}


@drill("adr", "kpis", "ADR")
def _adr(r: random.Random) -> dict:
    sold = r.randint(2500, 5200)
    rev = round(sold * r.uniform(180, 420), -2)
    return {"kind": "formula", "question": "In <b>B3</b>, calculate ADR, returning #N/A if no rooms were sold.",
            "target": "B3", "reference": "=IF(B2=0,NA(),B1/B2)", "fmt": "currency",
            "cells": {"A1": "Room revenue ($)", "B1": str(rev), "A2": "Rooms sold", "B2": str(sold), "A3": "ADR ($)"},
            "perturb": [{"B2": "0", "B1": "0"}, {"B1": str(rev + 50000)}],
            "forbid_functions": ["IFERROR"],
            "hints": ["ADR = room revenue / rooms sold.", "Guard the zero case: IF(B2=0,NA(),...)."],
            "solution": "=IF(B2=0,NA(),B1/B2)"}


@drill("revpar", "kpis", "RevPAR from ADR and occupancy")
def _revpar(r: random.Random) -> dict:
    occ, adr = round(r.uniform(0.55, 0.92), 3), r.randint(160, 480)
    return {"kind": "formula", "question": "In <b>B3</b>, calculate RevPAR from ADR (B1) and occupancy (B2).",
            "target": "B3", "reference": "=B1*B2", "fmt": "currency",
            "cells": {"A1": "ADR ($)", "B1": str(adr), "A2": "Occupancy", "B2": str(occ), "A3": "RevPAR ($)"},
            "perturb": [{"B1": str(adr + 25)}, {"B2": "0.5"}],
            "hints": ["RevPAR = ADR × occupancy (as a decimal)."], "solution": "=B1*B2"}


@drill("anchor", "refs", "Anchor an assumption")
def _anchor(r: random.Random) -> dict:
    rate = round(r.uniform(0.01, 0.06), 3)
    base = r.randint(800, 1500) * 1000
    return {"kind": "formula", "question": "Row 3 grows by the monthly rate in B1. In <b>C3</b>, write February's "
            "revenue from January (B3) so it can be copied to F3.",
            "target": "C3", "fill_to": "F3", "reference": "=B3*(1+$B$1)", "fmt": "currency0",
            "cells": {"A1": "Monthly growth", "B1": str(rate), "B2": "Jan", "C2": "Feb", "D2": "Mar", "E2": "Apr",
                      "F2": "May", "A3": "Revenue ($)", "B3": str(base)},
            "perturb": [{"B1": "0.1"}, {"B3": "1000000"}],
            "hints": ["Each month = previous month × (1 + growth).", "Anchor the growth cell: $B$1."],
            "solution": "=B3*(1+$B$1)"}


@drill("mixed", "refs", "Rooms × days across months")
def _mixed(r: random.Random) -> dict:
    rooms = r.choice([140, 180, 220])
    return {"kind": "formula", "question": "In <b>B3</b>, calculate available room nights for January so the "
            "formula can be copied to E3.", "target": "B3", "fill_to": "E3", "reference": "=$B$1*B2",
            "fmt": "number0",
            "cells": {"A1": "Rooms", "B1": str(rooms), "A2": "Days", "B2": "31", "C2": "28", "D2": "31", "E2": "30",
                      "A3": "Available"},
            "perturb": [{"B1": str(rooms + 30)}, {"C2": "29"}],
            "hints": ["Anchor the room count; keep days relative."], "solution": "=$B$1*B2"}


@drill("target_flag", "logic", "Target flag with IF")
def _flag(r: random.Random) -> dict:
    tgt = round(r.uniform(0.7, 0.85), 2)
    act = round(tgt + r.choice([-0.05, 0.03]), 2)
    return {"kind": "formula", "question": "In <b>B3</b>, return \"Met\" if actual occupancy (B1) is at least the "
            "target (B2), otherwise \"Missed\".", "target": "B3", "reference": "=IF(B1>=B2,\"Met\",\"Missed\")",
            "cells": {"A1": "Actual", "B1": str(act), "A2": "Target", "B2": str(tgt), "A3": "Result"},
            "perturb": [{"B1": str(tgt)}, {"B1": str(round(tgt - 0.1, 2))}, {"B1": str(round(tgt + 0.1, 2))}],
            "require_functions": ["IF"], "hints": ["IF(test, \"Met\", \"Missed\"); use >=."],
            "solution": "=IF(B1>=B2,\"Met\",\"Missed\")"}


@drill("check", "logic", "Reconciliation check")
def _check(r: random.Random) -> dict:
    a = r.randint(1000, 9000) * 1000
    l = int(a * r.uniform(0.4, 0.7))
    return {"kind": "formula", "question": "In <b>B4</b>, return TRUE if assets (B1) equal liabilities (B2) plus "
            "equity (B3) within 0.01.", "target": "B4", "reference": "=ABS(B1-B2-B3)<0.01",
            "cells": {"A1": "Assets", "B1": str(a), "A2": "Liabilities", "B2": str(l), "A3": "Equity",
                      "B3": str(a - l), "A4": "Check"},
            "perturb": [{"B3": str(a - l - 500)}, {"B1": str(a + 1000), "B3": str(a - l + 1000)}],
            "hints": ["ABS(difference) < tolerance."], "solution": "=ABS(B1-B2-B3)<0.01"}


@drill("sumifs", "lookups", "SUMIFS by segment")
def _sumifs(r: random.Random) -> dict:
    segs = ["Leisure", "Corporate", "Group"]
    cells = {"A1": "Segment", "B1": "Revenue"}
    for i in range(2, 9):
        cells[f"A{i}"] = r.choice(segs)
        cells[f"B{i}"] = str(r.randint(3, 40) * 100)
    pick = cells["A2"]
    cells.update({"D1": "Segment:", "E1": pick})
    other = next(s for s in segs if s != pick)
    return {"kind": "formula", "question": "In <b>F1</b>, sum revenue (B2:B8) for the segment named in E1.",
            "target": "F1", "reference": "=SUMIFS(B2:B8,A2:A8,E1)", "fmt": "currency0", "cells": cells,
            "perturb": [{"E1": other}, {"B2": "9999"}], "require_functions": ["SUMIFS"],
            "hints": ["SUMIFS(sum_range, criteria_range, criterion)."], "solution": "=SUMIFS(B2:B8,A2:A8,E1)"}


@drill("lookup", "lookups", "Look up a rate")
def _lookup(r: random.Random) -> dict:
    names = ["Standard", "Deluxe", "Suite", "Family"]
    cells = {}
    for i, n in enumerate(names, start=1):
        cells[f"A{i}"] = n
        cells[f"B{i}"] = str(r.randint(150, 900))
    pick = r.choice(names)
    cells.update({"D1": "Room type:", "E1": pick})
    return {"kind": "formula", "question": "In <b>F1</b>, return the rate for the room type in E1 from A1:B4.",
            "target": "F1", "reference": "=XLOOKUP(E1,A1:A4,B1:B4)", "fmt": "currency0", "cells": cells,
            "perturb": [{"E1": next(n for n in names if n != pick)}, {"B4": "1234"}],
            "hints": ["XLOOKUP(value, lookup_range, return_range) or INDEX/MATCH."],
            "solution": "=XLOOKUP(E1,A1:A4,B1:B4)"}


@drill("growth", "growth", "Growth rate")
def _growth(r: random.Random) -> dict:
    a = r.randint(80, 150) * 100000
    b = int(a * r.uniform(0.85, 1.25))
    return {"kind": "formula", "question": "In <b>B3</b>, calculate growth from last year (B1) to this year (B2).",
            "target": "B3", "reference": "=(B2-B1)/B1", "fmt": "percent",
            "cells": {"A1": "Last year ($)", "B1": str(a), "A2": "This year ($)", "B2": str(b), "A3": "Growth"},
            "perturb": [{"B2": str(a * 2)}, {"B1": str(b)}], "hints": ["(new - old) / old."],
            "solution": "=(B2-B1)/B1"}


@drill("varpct", "growth", "Variance % vs budget")
def _varpct(r: random.Random) -> dict:
    bud = r.randint(500, 2000) * 1000
    act = int(bud * r.uniform(0.85, 1.12))
    return {"kind": "formula", "question": "In <b>B3</b>, calculate the variance of actual (B1) vs budget (B2) as a "
            "% of budget.", "target": "B3", "reference": "=(B1-B2)/B2", "fmt": "percent",
            "cells": {"A1": "Actual ($)", "B1": str(act), "A2": "Budget ($)", "B2": str(bud), "A3": "Variance %"},
            "perturb": [{"B1": str(bud + 77777)}, {"B2": str(bud * 2)}], "hints": ["(actual - budget) / budget."],
            "solution": "=(B1-B2)/B2"}


@drill("breakeven", "costs", "Break-even volume")
def _be(r: random.Random) -> dict:
    p, v, f = r.randint(180, 400), r.randint(25, 80), r.randint(300, 900) * 1000
    return {"kind": "formula", "question": "In <b>B4</b>, calculate break-even room nights.", "target": "B4",
            "reference": "=B3/(B1-B2)", "fmt": "number",
            "cells": {"A1": "Rate ($)", "B1": str(p), "A2": "Variable cost ($)", "B2": str(v), "A3": "Fixed costs ($)",
                      "B3": str(f), "A4": "Break-even"},
            "perturb": [{"B1": str(p + 50)}, {"B3": str(f + 100000)}],
            "hints": ["Fixed costs / (price - variable cost)."], "solution": "=B3/(B1-B2)"}


@drill("margin", "costs", "Gross margin")
def _gm(r: random.Random) -> dict:
    rev = r.randint(500, 3000) * 1000
    cos = int(rev * r.uniform(0.25, 0.45))
    return {"kind": "formula", "question": "In <b>B3</b>, calculate gross margin %.", "target": "B3",
            "reference": "=(B1-B2)/B1", "fmt": "percent",
            "cells": {"A1": "Revenue ($)", "B1": str(rev), "A2": "Cost of sales ($)", "B2": str(cos),
                      "A3": "Gross margin"},
            "perturb": [{"B2": str(int(cos * 1.3))}, {"B1": str(rev + 250000)}],
            "hints": ["(revenue - cost of sales) / revenue."], "solution": "=(B1-B2)/B1"}


def generate(key: str, seed: int) -> dict:
    topic, title, fn = DRILLS[key]
    q = fn(random.Random(seed))
    q.update({"drill": key, "topic": topic, "title": title})
    return q
