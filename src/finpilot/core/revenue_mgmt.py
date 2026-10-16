"""Group booking displacement analysis (Level 4 preview in V1).

Question: should the hotel accept a lower-rate group block, or protect the
rooms for potentially higher-rate individual (transient) guests?

The model compares the *expected contribution* of both options over the stay:

* Transient demand is uncertain: ``transient_demand`` rooms per night would like
  to book, and each converts with probability ``booking_probability``.
  Expected transient rooms = min(demand x probability, rooms left).
  (A simplification: a full model would use the whole demand distribution.)
* Contribution = room revenue - distribution costs - variable cost per occupied
  room + ancillary (F&B) profit.

Higher occupancy does not automatically mean higher profit: the group may fill
the hotel at a rate that, after commissions and lost transient business,
contributes less than leaving rooms for transient guests.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GroupInputs:
    rooms_available: int = 180          # sellable rooms per night
    nights: int = 3
    group_rooms: int = 60               # rooms per night requested by the group
    group_rate: float = 240.0
    group_commission: float = 0.0       # % of group room revenue (e.g. agency)
    group_fb_per_room: float = 85.0     # banquet/F&B spend per group room night
    transient_demand: float = 150.0     # rooms per night transient guests would like to book
    booking_probability: float = 0.85   # share of that demand expected to materialise
    transient_rate: float = 365.0
    transient_distribution_cost: float = 0.15  # OTA/channel cost % of transient revenue
    transient_fb_per_room: float = 40.0
    fb_margin: float = 0.30             # profit share of F&B revenue
    variable_cost_per_room: float = 42.0  # housekeeping, amenities, laundry per occupied room


@dataclass
class OptionResult:
    label: str
    group_rooms: float
    transient_rooms: float
    occupancy: float
    room_revenue: float
    distribution_cost: float
    variable_cost: float
    fb_profit: float
    contribution: float

    @property
    def occupied(self) -> float:
        return self.group_rooms + self.transient_rooms


@dataclass
class DisplacementResult:
    accept: OptionResult
    decline: OptionResult
    displaced_transient_rooms: float  # transient room nights lost by accepting
    incremental_contribution: float   # accept - decline
    breakeven_group_rate: float | None
    recommendation: str
    explanation: list[str]


def validate_inputs(i: GroupInputs) -> list[str]:
    problems = []
    if i.rooms_available <= 0:
        problems.append("Rooms available must be more than zero.")
    if i.nights <= 0:
        problems.append("The stay must be at least one night.")
    if i.group_rooms < 0 or i.transient_demand < 0:
        problems.append("Room counts cannot be negative.")
    if i.group_rooms > i.rooms_available:
        problems.append("The group wants more rooms than the hotel has available.")
    for name in ("booking_probability", "group_commission", "transient_distribution_cost", "fb_margin"):
        v = getattr(i, name)
        if not 0 <= v <= 1:
            problems.append(f"{name.replace('_', ' ').capitalize()} must be between 0% and 100%.")
    if i.group_rate < 0 or i.transient_rate < 0:
        problems.append("Rates cannot be negative.")
    return problems


def _option(i: GroupInputs, label: str, group_rooms: float) -> OptionResult:
    left = i.rooms_available - group_rooms
    transient = min(i.transient_demand * i.booking_probability, left)
    n = i.nights
    g_rev = group_rooms * i.group_rate * n
    t_rev = transient * i.transient_rate * n
    dist = g_rev * i.group_commission + t_rev * i.transient_distribution_cost
    var = (group_rooms + transient) * i.variable_cost_per_room * n
    fb = (group_rooms * i.group_fb_per_room + transient * i.transient_fb_per_room) * n * i.fb_margin
    contribution = g_rev + t_rev - dist - var + fb
    return OptionResult(label, group_rooms * n, transient * n, (group_rooms + transient) / i.rooms_available,
                        g_rev + t_rev, dist, var, fb, contribution)


def analyse(i: GroupInputs) -> DisplacementResult:
    problems = validate_inputs(i)
    if problems:
        raise ValueError(" ".join(problems))
    acc = _option(i, "Accept group", i.group_rooms)
    dec = _option(i, "Decline group", 0)
    displaced = dec.transient_rooms - acc.transient_rooms
    inc = acc.contribution - dec.contribution

    # Group rate at which both options contribute the same (contribution is linear in the rate).
    per_rate = i.group_rooms * i.nights * (1 - i.group_commission)
    be = None
    if per_rate > 0:
        be = i.group_rate - inc / per_rate
        be = max(be, 0.0)

    expl = [
        f"Accepting fills {acc.occupancy:.0%} of rooms versus {dec.occupancy:.0%} if declined.",
        f"Accepting displaces about {displaced:,.0f} transient room nights that would have paid "
        f"${i.transient_rate:,.0f} before {i.transient_distribution_cost:.0%} channel costs.",
        f"Net contribution: accept ${acc.contribution:,.0f} versus decline ${dec.contribution:,.0f} "
        f"(difference ${inc:,.0f}).",
    ]
    if be is not None:
        expl.append(f"The group rate would need to be at least ${be:,.2f} for accepting to break even "
                    "against declining, with all other assumptions unchanged.")
    if acc.occupancy > dec.occupancy and inc < 0:
        expl.append("Higher occupancy is not the same as higher profit: here the fuller hotel earns less.")
    if displaced == 0:
        expl.append("No transient demand is displaced, so the group is incremental business.")
    expl.append("This is an expected-value estimate from assumptions, not a guaranteed outcome. Test the "
                "booking probability: the decision often flips when demand is uncertain.")

    if abs(inc) < 1e-6:
        rec = "Indifferent: both options contribute the same. Consider non-financial factors."
    elif inc > 0:
        rec = "Accept the group: it adds expected contribution after displacement."
    else:
        rec = "Decline (or counter-offer a higher rate): the group reduces expected contribution."
    return DisplacementResult(acc, dec, displaced, inc, be, rec, expl)
