"""Financial and hotel calculations, checked against independent hand calculations."""
import calendar
import math

import pytest

from finpilot.core import finance as F
from finpilot.core import hotel as H
from finpilot.core import revenue_mgmt as RM


# ---------------------------------------------------------------- finance basics
def test_zero_denominators_return_none_not_crash():
    assert F.safe_div(1, 0) is None
    assert F.gross_margin(0, 10) is None
    assert F.break_even_units(1000, 10, 10) is None          # zero contribution
    assert F.growth_rate(100, 0) is None
    assert F.variance_pct(90, 0) is None
    assert H.occupancy(0, 0) is None and H.adr(0, 0) is None and H.revpar(0, 0) is None


def test_core_finance_formulas():
    assert F.gross_margin(1000, 600) == pytest.approx(0.4)
    assert F.break_even_units(12000, 50, 30) == pytest.approx(600)
    assert F.break_even_revenue(12000, 50, 30) == pytest.approx(30000)
    assert F.net_income(1000, 200, 0.25) == pytest.approx(600)
    assert F.cagr(100, 121, 2) == pytest.approx(0.10)
    assert F.variance(110, 100) == 10 and F.variance_pct(110, 100) == pytest.approx(0.10)
    assert F.is_favourable(110, 100, "revenue") is True
    assert F.is_favourable(110, 100, "cost") is False
    assert F.npv_excel(0.1, [100, 100, 100]) == pytest.approx(248.6852, rel=1e-6)
    assert F.irr([-1000, 400, 400, 400]) == pytest.approx(0.09701, abs=1e-5)


def test_profit_is_not_cash():
    # profit 600 but receivables up 900: operating cash flow is negative
    ocf = F.operating_cash_flow(600, 100, 900, 0, 0)
    assert ocf < 0


# ---------------------------------------------------------------- hotel KPIs
def test_kpi_identities():
    rooms, days, occ, adr = 180, 31, 0.58, 279.0
    avail = rooms * days
    sold = avail * occ
    rev = sold * adr
    assert H.available_room_nights(rooms, days) == 5580
    assert H.occupancy(sold, avail) == pytest.approx(occ)
    assert H.adr(rev, sold) == pytest.approx(adr)
    assert H.revpar(rev, avail) == pytest.approx(adr * occ)          # RevPAR = ADR x occupancy
    assert H.revpar_from_adr_occ(adr, occ) == pytest.approx(H.revpar(rev, avail))


def test_default_budget_and_forecast_totals_independently():
    """Recompute the fictional Harbour Crest model by hand (no FinPilot code)."""
    for a, expected in ((H.default_budget(), 17_366_058), (H.default_forecast(), 17_484_066)):
        total = 0.0
        for i, m in enumerate(a.months):
            days = calendar.monthrange(a.year, i + 1)[1]
            total += a.rooms * days * m.occupancy * m.adr
        assert round(total) == expected
        assert round(H.compute(a).total.room_revenue) == expected


def test_annual_kpis_are_weighted_not_simple_averages():
    a = H.default_forecast()
    r = H.compute(a)
    sold = sum(m.rooms_sold for m in r.months)
    avail = sum(m.available for m in r.months)
    assert r.total.occupancy == pytest.approx(sold / avail)
    assert r.total.adr == pytest.approx(r.total.room_revenue / sold)
    simple = sum(m.occupancy for m in a.months) / 12
    assert not math.isclose(r.total.occupancy, simple, abs_tol=1e-6)


def test_leap_year_february():
    a = H.default_forecast().copy(year=2028)
    assert a.days()[1] == 29


def test_zero_rooms_gives_explicit_validation_failure():
    a = H.default_forecast().copy(rooms=0)
    r = H.compute(a)
    assert r.total.occupancy is None
    checks = H.validate(a, r)
    assert any(c.status == "fail" for c in checks)


def test_invalid_occupancy_is_flagged():
    a = H.default_forecast()
    a.months[0].occupancy = 1.2
    checks = H.validate(a)
    assert any(c.status == "fail" and c.category == "input" for c in checks)


def test_compute_requires_twelve_months():
    a = H.default_forecast()
    a.months = a.months[:11]
    with pytest.raises(ValueError):
        H.compute(a)


# ---------------------------------------------------------------- variance & bridge
def test_revenue_bridge_reconciles_exactly_every_month_and_year():
    b, f = H.compute(H.default_budget()), H.compute(H.default_forecast())
    for bm, fm in zip(b.months + [b.total], f.months + [f.total]):
        br = H.room_revenue_bridge(bm, fm)
        assert br.reconciles
        # independent: volume at budget ADR, rate at forecast volume
        vol = (fm.rooms_sold - bm.rooms_sold) * bm.adr
        rate = (fm.adr - bm.adr) * fm.rooms_sold
        assert br.volume_effect == pytest.approx(vol)
        assert br.rate_effect == pytest.approx(rate)
        assert vol + rate == pytest.approx(fm.room_revenue - bm.room_revenue)


def test_forecast_vs_budget_variance():
    b, f = H.compute(H.default_budget()), H.compute(H.default_forecast())
    var = f.total.room_revenue - b.total.room_revenue
    assert round(var) == 118_008
    assert var / b.total.room_revenue == pytest.approx(0.0068, abs=5e-5)


# ---------------------------------------------------------------- scenarios & sensitivity
def test_scenario_caps_occupancy_and_matches_lesson_figures():
    a = H.default_forecast()
    down = H.compute(H.apply_scenario(a, occ_points=-0.04, adr_pct=-0.03))
    assert down.total.room_revenue / 1e6 == pytest.approx(16.10, abs=0.005)   # final assessment S1
    up = H.apply_scenario(a, occ_points=0.50)
    assert max(m.occupancy for m in up.months) <= 1.0


def test_sensitivity_grid_matches_lesson_3_6():
    a = H.default_forecast()
    grid = H.sensitivity_grid(a, [-0.03, 0.0, 0.03], [-0.05, 0.0, 0.05])
    values = [[round(v / 1e6, 2) for v in row] for row in grid]
    assert values == [[15.98, 16.82, 17.66], [16.61, 17.48, 18.36], [17.24, 18.15, 19.06]]


def test_seasonal_occupancy_hits_weighted_annual_target():
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    idx = [0.8, 0.85, 0.95, 1.0, 1.05, 1.15, 1.2, 1.2, 1.05, 1.0, 0.9, 0.85]
    occ = H.seasonal_occupancy(0.75, idx, days)
    assert sum(o * d for o, d in zip(occ, days)) / sum(days) == pytest.approx(0.75, abs=1e-9)


# ---------------------------------------------------------------- group displacement
def test_group_displacement_hand_calculation():
    i = RM.GroupInputs()
    r = RM.analyse(i)
    # Independent calculation of the decline option
    transient = min(i.transient_demand * i.booking_probability, i.rooms_available) * i.nights
    dec_contrib = (transient * i.transient_rate * (1 - i.transient_distribution_cost)
                   - transient * i.variable_cost_per_room
                   + transient * i.transient_fb_per_room * i.fb_margin)
    assert r.decline.contribution == pytest.approx(dec_contrib)
    # Accept: group takes its rooms, transient gets what is left
    t_acc = min(i.transient_demand * i.booking_probability, i.rooms_available - i.group_rooms) * i.nights
    g = i.group_rooms * i.nights
    acc = (g * i.group_rate * (1 - i.group_commission) + t_acc * i.transient_rate * (1 - i.transient_distribution_cost)
           - (g + t_acc) * i.variable_cost_per_room
           + (g * i.group_fb_per_room + t_acc * i.transient_fb_per_room) * i.fb_margin)
    assert r.accept.contribution == pytest.approx(acc)
    assert r.incremental_contribution == pytest.approx(acc - dec_contrib)
    assert r.recommendation


def test_group_breakeven_rate_makes_difference_zero():
    i = RM.GroupInputs()
    r = RM.analyse(i)
    assert r.breakeven_group_rate is not None
    j = RM.GroupInputs(**{**i.__dict__, "group_rate": r.breakeven_group_rate})
    assert RM.analyse(j).incremental_contribution == pytest.approx(0, abs=1e-6)


def test_group_invalid_inputs_reported():
    assert RM.validate_inputs(RM.GroupInputs(group_rooms=500))
    assert RM.validate_inputs(RM.GroupInputs(booking_probability=1.5))
