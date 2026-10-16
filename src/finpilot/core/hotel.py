"""Hotel revenue model: drivers, KPIs, scenarios, variance and validation.

Definitions (USALI-style, simplified for training):

* Available room nights = rooms x days in the month
* Occupancy  = Rooms Sold / Available Room Nights
* ADR        = Room Revenue / Rooms Sold
* RevPAR     = Room Revenue / Available Room Nights  (= ADR x Occupancy)
* Room Revenue = Rooms Sold x ADR
* F&B revenue  = Rooms Sold x F&B spend per occupied room   (driver-based simplification)
* Other operating revenue = Room Revenue x other-revenue %   (simplification)

Annual (or any multi-month) occupancy, ADR and RevPAR are *weighted*: they are
recomputed from summed rooms sold, revenue and available room nights. Averaging
twelve monthly percentages gives the wrong answer because months have
different lengths and different volumes.

Rooms sold are kept unrounded so that the identities above hold exactly; the
UI displays them rounded. All data shipped with FinPilot is fictional.
"""
from __future__ import annotations

import calendar
import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from .finance import safe_div

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ------------------------------------------------------------------ KPI functions


def available_room_nights(rooms: float, days: int) -> float:
    if rooms < 0 or days < 0:
        raise ValueError("Rooms and days cannot be negative.")
    return rooms * days


def occupancy(rooms_sold: float, available: float) -> Optional[float]:
    """Rooms Sold / Available Rooms. None if no rooms were available."""
    return safe_div(rooms_sold, available)


def adr(room_revenue: float, rooms_sold: float) -> Optional[float]:
    """Room Revenue / Rooms Sold. None (not 0) when no rooms were sold."""
    return safe_div(room_revenue, rooms_sold)


def revpar(room_revenue: float, available: float) -> Optional[float]:
    """Room Revenue / Available Rooms. None if no rooms were available."""
    return safe_div(room_revenue, available)


def room_revenue(rooms_sold: float, adr_value: float) -> float:
    return rooms_sold * adr_value


def revpar_from_adr_occ(adr_value: float, occ: float) -> float:
    return adr_value * occ


# ------------------------------------------------------------------- model input


@dataclass
class MonthInput:
    occupancy: float
    adr: float
    fb_per_occupied_room: float
    other_pct: float  # other operating revenue as % of room revenue


@dataclass
class HotelAssumptions:
    hotel_name: str = "Harbour Crest Hotel (fictional)"
    scenario: str = "Budget"
    rooms: int = 180
    year: int = 2026
    currency: str = "USD"
    months: list[MonthInput] = field(default_factory=list)
    notes: str = ""

    def days(self) -> list[int]:
        return [calendar.monthrange(self.year, m)[1] for m in range(1, 13)]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HotelAssumptions":
        months = [MonthInput(**{k: float(v) for k, v in m.items()}) for m in d.get("months", [])]
        return cls(hotel_name=d.get("hotel_name", "Hotel"), scenario=d.get("scenario", "Scenario"),
                   rooms=int(d.get("rooms", 0)), year=int(d.get("year", 2026)),
                   currency=d.get("currency", "USD"), months=months, notes=d.get("notes", ""))

    def copy(self, **changes) -> "HotelAssumptions":
        c = copy.deepcopy(self)
        for k, v in changes.items():
            setattr(c, k, v)
        return c


# Fictional seasonal profile for a 180-room luxury waterfront hotel.
_BUDGET_OCC = [0.62, 0.66, 0.72, 0.78, 0.82, 0.88, 0.91, 0.92, 0.85, 0.80, 0.68, 0.74]
_BUDGET_ADR = [285, 290, 305, 320, 335, 365, 390, 395, 350, 330, 295, 340]
_FORECAST_OCC = [0.58, 0.63, 0.71, 0.79, 0.84, 0.89, 0.93, 0.93, 0.84, 0.78, 0.66, 0.73]
_FORECAST_ADR = [279, 284, 300, 324, 342, 378, 405, 410, 352, 328, 289, 345]


def default_budget() -> HotelAssumptions:
    return HotelAssumptions(
        scenario="Budget",
        months=[MonthInput(o, a, 95.0, 0.06) for o, a in zip(_BUDGET_OCC, _BUDGET_ADR)],
        notes="Fictional budget prepared in October 2025. Seasonality reflects a waterfront leisure hotel "
              "with summer peak demand and a soft January-February.")


def default_forecast() -> HotelAssumptions:
    return HotelAssumptions(
        scenario="Forecast",
        months=[MonthInput(o, a, 92.0 if i < 3 else 97.0, 0.06)
                for i, (o, a) in enumerate(zip(_FORECAST_OCC, _FORECAST_ADR))],
        notes="Fictional reforecast: weaker winter demand after a competitor opened; stronger summer "
              "rates driven by a city events calendar.")


# Fictional actuals for January-June (rooms sold, room revenue, F&B revenue, other revenue).
DEFAULT_ACTUALS = [
    (3180, 896_760, 291_000, 52_900),
    (3270, 935_220, 302_100, 55_400),
    (3900, 1_181_700, 361_000, 70_100),
    (4310, 1_396_440, 410_200, 83_500),
    (4720, 1_609_520, 455_900, 96_700),
    (4840, 1_819_840, 466_300, 108_000),
]


# ------------------------------------------------------------------ model result


@dataclass
class MonthResult:
    month: str
    days: int
    available: float
    rooms_sold: float
    occupancy: Optional[float]
    adr: Optional[float]
    room_revenue: float
    revpar: Optional[float]
    fb_revenue: float
    other_revenue: float
    total_revenue: float
    trevpar: Optional[float]


@dataclass
class ModelResult:
    assumptions: HotelAssumptions
    months: list[MonthResult]
    total: MonthResult


def _aggregate(label: str, rows: list[MonthResult]) -> MonthResult:
    avail = math.fsum(r.available for r in rows)
    sold = math.fsum(r.rooms_sold for r in rows)
    rr = math.fsum(r.room_revenue for r in rows)
    fb = math.fsum(r.fb_revenue for r in rows)
    other = math.fsum(r.other_revenue for r in rows)
    total = rr + fb + other
    return MonthResult(label, sum(r.days for r in rows), avail, sold, occupancy(sold, avail),
                       adr(rr, sold), rr, revpar(rr, avail), fb, other, total, safe_div(total, avail))


def compute(a: HotelAssumptions) -> ModelResult:
    if len(a.months) != 12:
        raise ValueError(f"The model needs 12 months of assumptions, got {len(a.months)}.")
    rows = []
    for name, days, m in zip(MONTHS, a.days(), a.months):
        avail = available_room_nights(a.rooms, days)
        sold = avail * m.occupancy
        rr = room_revenue(sold, m.adr)
        fb = sold * m.fb_per_occupied_room
        other = rr * m.other_pct
        total = rr + fb + other
        rows.append(MonthResult(name, days, avail, sold, occupancy(sold, avail), adr(rr, sold), rr,
                                revpar(rr, avail), fb, other, total, safe_div(total, avail)))
    return ModelResult(a, rows, _aggregate("Total", rows))


def actuals_result(rooms: int, year: int, actuals=DEFAULT_ACTUALS) -> list[MonthResult]:
    rows = []
    days = [calendar.monthrange(year, m)[1] for m in range(1, 13)]
    for i, (sold, rr, fb, other) in enumerate(actuals):
        avail = available_room_nights(rooms, days[i])
        total = rr + fb + other
        rows.append(MonthResult(MONTHS[i], days[i], avail, sold, occupancy(sold, avail), adr(rr, sold),
                                rr, revpar(rr, avail), fb, other, total, safe_div(total, avail)))
    return rows


# --------------------------------------------------------------- scenarios


def apply_scenario(a: HotelAssumptions, occ_points: float = 0.0, adr_pct: float = 0.0,
                   fb_pct: float = 0.0, rooms: Optional[int] = None, name: Optional[str] = None,
                   cap_occupancy: bool = True) -> HotelAssumptions:
    """Shift every month: occupancy by percentage points (0.02 = +2 pts), ADR and F&B by %."""
    out = a.copy()
    out.scenario = name or f"{a.scenario} (adjusted)"
    if rooms is not None:
        out.rooms = rooms
    new = []
    for m in a.months:
        occ = m.occupancy + occ_points
        if cap_occupancy:
            occ = min(max(occ, 0.0), 1.0)
        new.append(MonthInput(occ, m.adr * (1 + adr_pct), m.fb_per_occupied_room * (1 + fb_pct), m.other_pct))
    out.months = new
    return out


def seasonal_occupancy(annual_target: float, indices: list[float], days: list[int]) -> list[float]:
    """Spread an annual occupancy target over months using seasonal indices.

    Indices are scaled so that the *day-weighted* annual occupancy equals the
    target. Months that would exceed 100% are capped and the excess is NOT
    redistributed (the function reports the shortfall through the result).
    """
    if len(indices) != 12 or len(days) != 12:
        raise ValueError("Need 12 indices and 12 month lengths.")
    weighted = sum(i * d for i, d in zip(indices, days)) / sum(days)
    if weighted <= 0:
        raise ValueError("Seasonal indices must be positive.")
    return [min(annual_target * i / weighted, 1.0) for i in indices]


def sensitivity_grid(a: HotelAssumptions, occ_steps: list[float], adr_steps: list[float],
                     metric: str = "room_revenue") -> list[list[float]]:
    """Annual metric for each (occupancy shift, ADR % shift) pair. Rows = occupancy."""
    grid = []
    for o in occ_steps:
        row = []
        for p in adr_steps:
            t = compute(apply_scenario(a, o, p)).total
            row.append(getattr(t, metric))
        grid.append(row)
    return grid


# ---------------------------------------------------------------- variance


@dataclass
class RevenueBridge:
    month: str
    base_revenue: float
    compare_revenue: float
    volume_effect: float   # (sold_c - sold_b) x ADR_b
    rate_effect: float     # (ADR_c - ADR_b) x sold_c
    total_variance: float

    @property
    def reconciles(self) -> bool:
        return math.isclose(self.volume_effect + self.rate_effect, self.total_variance,
                            rel_tol=1e-9, abs_tol=1e-6)


def room_revenue_bridge(base: MonthResult, comp: MonthResult) -> RevenueBridge:
    """Split a room revenue variance into volume (rooms sold) and rate (ADR) effects.

    Volume is valued at the base ADR and rate at the comparison volume, so the
    two effects add up exactly to the total variance (no unexplained residual).
    """
    base_adr = base.adr or 0.0
    comp_adr = comp.adr or 0.0
    volume = (comp.rooms_sold - base.rooms_sold) * base_adr
    rate = (comp_adr - base_adr) * comp.rooms_sold
    return RevenueBridge(comp.month, base.room_revenue, comp.room_revenue, volume, rate,
                         comp.room_revenue - base.room_revenue)


# --------------------------------------------------------------- validation


@dataclass
class Check:
    name: str
    status: str      # "pass", "warn", "fail"
    category: str    # "input", "formula", "missing", "reasonableness", "reconciliation"
    message: str


def validate(a: HotelAssumptions, result: Optional[ModelResult] = None) -> list[Check]:
    checks: list[Check] = []
    if a.rooms <= 0:
        checks.append(Check("Room count", "fail", "input",
                            "The hotel needs at least one room. With zero rooms, occupancy, ADR and RevPAR "
                            "are undefined (shown as n/a)."))
    else:
        checks.append(Check("Room count", "pass", "input", f"{a.rooms} rooms."))
    if len(a.months) != 12:
        checks.append(Check("12 monthly periods", "fail", "missing",
                            f"Found {len(a.months)} months of assumptions; the model needs 12."))
        return checks
    checks.append(Check("12 monthly periods", "pass", "missing", "All 12 months have assumptions."))

    bad_occ = [MONTHS[i] for i, m in enumerate(a.months) if not (0 <= m.occupancy <= 1)]
    if bad_occ:
        checks.append(Check("Occupancy between 0% and 100%", "fail", "input",
                            "Occupancy cannot be below 0% or above 100% (you cannot sell more rooms than "
                            "exist): " + ", ".join(bad_occ) + "."))
    else:
        checks.append(Check("Occupancy between 0% and 100%", "pass", "input", "All months are in range."))
    high = [MONTHS[i] for i, m in enumerate(a.months) if 0.97 < m.occupancy <= 1]
    if high:
        checks.append(Check("Occupancy realism", "warn", "reasonableness",
                            "Occupancy above 97% is possible on peak nights but rare across a whole month: "
                            + ", ".join(high) + ". Check the assumption."))
    neg_adr = [MONTHS[i] for i, m in enumerate(a.months) if m.adr < 0]
    if neg_adr:
        checks.append(Check("ADR not negative", "fail", "input", "ADR cannot be negative: " + ", ".join(neg_adr)))
    odd_adr = [MONTHS[i] for i, m in enumerate(a.months) if 0 <= m.adr < 100 or m.adr > 2500]
    if odd_adr:
        checks.append(Check("ADR realism for a luxury hotel", "warn", "reasonableness",
                            "The maths works, but an ADR below $100 or above $2,500 is unusual for this "
                            "luxury hotel: " + ", ".join(odd_adr) + "."))
    if any(m.fb_per_occupied_room < 0 or m.other_pct < 0 for m in a.months):
        checks.append(Check("Ancillary drivers not negative", "fail", "input",
                            "F&B spend per occupied room and other revenue % cannot be negative."))

    if result is None and not any(c.status == "fail" for c in checks):
        result = compute(a)
    if result is not None:
        ok = all(r.revpar is None or r.occupancy is None or
                 math.isclose(r.revpar, r.adr * r.occupancy if r.adr is not None else 0.0,
                              rel_tol=1e-9, abs_tol=1e-9)
                 for r in result.months)
        checks.append(Check("RevPAR = ADR x Occupancy", "pass" if ok else "fail", "formula",
                            "RevPAR reconciles to ADR x Occupancy in every month." if ok else
                            "RevPAR does not equal ADR x Occupancy. A formula is inconsistent."))
        t = result.total
        comp_ok = math.isclose(t.total_revenue, t.room_revenue + t.fb_revenue + t.other_revenue,
                               rel_tol=1e-12, abs_tol=1e-6)
        sum_ok = math.isclose(t.total_revenue, math.fsum(r.total_revenue for r in result.months),
                              rel_tol=1e-12, abs_tol=1e-6)
        checks.append(Check("Total revenue reconciles", "pass" if comp_ok and sum_ok else "fail",
                            "reconciliation",
                            "Annual total equals the sum of months and of revenue streams."
                            if comp_ok and sum_ok else "Annual total does not reconcile."))
        simple_avg = sum(r.occupancy or 0 for r in result.months) / 12
        if t.occupancy is not None and abs(simple_avg - t.occupancy) > 1e-9:
            checks.append(Check("Annual occupancy is weighted", "pass", "formula",
                                f"Annual occupancy is {t.occupancy:.2%} (rooms sold / available). A simple "
                                f"average of the monthly rates would give {simple_avg:.2%}, which is wrong "
                                "because months differ in length."))
    return checks
