"""Core financial calculations, independent of the user interface.

Conventions
-----------
* Percentages are decimals (0.75 = 75%).
* Functions that would divide by zero return ``None`` rather than a misleading
  number; callers show "n/a" and explain why.
* Variances are Actual (or Forecast) minus Budget. Whether a variance is
  favourable depends on the line type: higher revenue is favourable, higher
  cost is unfavourable (see ``is_favourable``).
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator is None or numerator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


# --------------------------------------------------------- profitability


def gross_profit(revenue: float, cost_of_sales: float) -> float:
    return revenue - cost_of_sales


def gross_margin(revenue: float, cost_of_sales: float) -> Optional[float]:
    return safe_div(revenue - cost_of_sales, revenue)


def contribution_per_unit(price: float, variable_cost: float) -> float:
    return price - variable_cost


def contribution_margin_ratio(price: float, variable_cost: float) -> Optional[float]:
    return safe_div(price - variable_cost, price)


def break_even_units(fixed_costs: float, price: float, variable_cost: float) -> Optional[float]:
    """Units needed for zero profit. None when each unit makes no contribution."""
    cm = price - variable_cost
    if cm <= 0:
        return None
    return fixed_costs / cm


def break_even_revenue(fixed_costs: float, price: float, variable_cost: float) -> Optional[float]:
    ratio = contribution_margin_ratio(price, variable_cost)
    if ratio is None or ratio <= 0:
        return None
    return fixed_costs / ratio


def ebitda(revenue: float, operating_expenses_excl_da: float) -> float:
    return revenue - operating_expenses_excl_da


def ebit(ebitda_value: float, depreciation_amortisation: float) -> float:
    return ebitda_value - depreciation_amortisation


def net_income(ebit_value: float, interest: float, tax_rate: float) -> float:
    """Simplified: tax is charged only on positive pre-tax profit (no loss carry-forward)."""
    pretax = ebit_value - interest
    tax = max(pretax, 0.0) * tax_rate
    return pretax - tax


def operating_cash_flow(net_income_value: float, depreciation: float, change_receivables: float,
                        change_inventory: float, change_payables: float) -> float:
    """Indirect method: increases in receivables/inventory use cash; payables provide cash."""
    return net_income_value + depreciation - change_receivables - change_inventory + change_payables


# ----------------------------------------------------------- growth & variance


def growth_rate(current: float, prior: float) -> Optional[float]:
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


def cagr(begin: float, end: float, years: float) -> Optional[float]:
    if begin <= 0 or end < 0 or years <= 0:
        return None
    return (end / begin) ** (1 / years) - 1


def variance(actual: float, budget: float) -> float:
    return actual - budget


def variance_pct(actual: float, budget: float) -> Optional[float]:
    if budget == 0:
        return None
    return (actual - budget) / abs(budget)


def is_favourable(actual: float, budget: float, line_type: str) -> Optional[bool]:
    """line_type: 'revenue' (higher is better) or 'cost' (lower is better)."""
    if math.isclose(actual, budget, abs_tol=1e-9):
        return None
    if line_type == "revenue":
        return actual > budget
    if line_type == "cost":
        return actual < budget
    raise ValueError("line_type must be 'revenue' or 'cost'")


# -------------------------------------------------------- time value of money


def npv_excel(rate: float, cashflows: Sequence[float]) -> float:
    """Excel NPV: first cash flow is discounted one full period."""
    return math.fsum(cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows))


def npv_t0(rate: float, cashflows: Sequence[float]) -> float:
    """NPV where the first cash flow happens today (t = 0)."""
    return math.fsum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))


def irr(cashflows: Sequence[float], guess: float = 0.1) -> Optional[float]:
    """IRR with t=0 for the first cash flow. Newton's method with bisection fallback."""
    cfs = list(cashflows)
    if not (any(c > 0 for c in cfs) and any(c < 0 for c in cfs)):
        return None

    def f(r):
        return math.fsum(c / (1 + r) ** i for i, c in enumerate(cfs))

    r = guess
    for _ in range(100):
        try:
            v = f(r)
            d = math.fsum(-i * c / (1 + r) ** (i + 1) for i, c in enumerate(cfs))
        except (OverflowError, ZeroDivisionError):
            break
        if d == 0:
            break
        nr = r - v / d
        if nr <= -0.999999:
            break
        if abs(nr - r) < 1e-12:
            return nr
        r = nr
    lo, hi = -0.99, 10.0
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        fm = f(mid)
        if abs(fm) < 1e-10:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def future_value(pv: float, rate: float, periods: float) -> float:
    return pv * (1 + rate) ** periods


def present_value(fv: float, rate: float, periods: float) -> float:
    return fv / (1 + rate) ** periods


def mean(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    return sum(vals) / len(vals) if vals else None
