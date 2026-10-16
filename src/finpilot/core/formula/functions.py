"""Built-in spreadsheet functions supported by FinPilot.

Every function here is Excel-compatible for the arguments FinPilot supports.
Anything not listed returns #NAME? (unknown) or #UNSUPPORTED! (a real Excel
function FinPilot has not implemented), never a silently wrong value.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
from typing import Any

from .errors import CellError, ErrorSignal, err
from .evaluator import (Evaluator, Function, RangeValue, check, compare, scalar, to_bool,
                        to_number, to_text)

FUNCTIONS: dict[str, Function] = {}

# Real Excel functions a learner may try that FinPilot does not implement yet.
KNOWN_UNSUPPORTED = {
    "OFFSET", "INDIRECT", "FILTER", "SORT", "UNIQUE", "SEQUENCE", "LET", "LAMBDA", "TEXT",
    "XIRR", "XNPV", "FORECAST", "TREND", "GROWTH", "LINEST", "RATE", "NPER", "CHOOSE",
    "TEXTJOIN", "NETWORKDAYS", "WORKDAY", "RAND", "RANDBETWEEN", "TODAY", "NOW", "CELL",
    "GETPIVOTDATA", "SUBTOTAL", "AGGREGATE", "MEDIAN", "STDEV", "STDEV.S", "PERCENTILE",
}


def register(name: str, min_args: int, max_args: int | None, summary: str, lazy: bool = False):
    def deco(fn):
        FUNCTIONS[name] = Function(name, fn, min_args, max_args, lazy, summary)
        return fn
    return deco


# ------------------------------------------------------------------ helpers


def _iter_values(args, *, numbers_only_from_ranges: bool = True):
    """Yield numbers from args following Excel SUM rules.

    Direct arguments are coerced (text "5" counts); values inside ranges count
    only if they are numbers (text and blanks are skipped). Errors propagate.
    """
    for a in args:
        if isinstance(a, RangeValue):
            for v in a.flat():
                check(v)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    yield float(v)
        elif a is None:
            continue
        else:
            yield to_number(a)


def _vector(v: Any, what: str = "range") -> list[Any]:
    if isinstance(v, RangeValue):
        if not v.is_vector():
            raise err("#VALUE!", f"The {what} must be a single row or column.")
        return v.flat()
    return [v]


def _as_range(v: Any) -> RangeValue:
    return v if isinstance(v, RangeValue) else RangeValue([[v]])


# ------------------------------------------------------------------ maths


@register("SUM", 1, None, "Adds numbers and ranges. SUM(B2:M2)")
def _sum(*args):
    return math.fsum(_iter_values(args))


@register("AVERAGE", 1, None, "Arithmetic mean of numbers. AVERAGE(B2:M2)")
def _average(*args):
    vals = list(_iter_values(args))
    if not vals:
        raise err("#DIV/0!", "AVERAGE() found no numbers.")
    return math.fsum(vals) / len(vals)


@register("MIN", 1, None, "Smallest number. MIN(B2:M2)")
def _min(*args):
    vals = list(_iter_values(args))
    return min(vals) if vals else 0.0


@register("MAX", 1, None, "Largest number. MAX(B2:M2)")
def _max(*args):
    vals = list(_iter_values(args))
    return max(vals) if vals else 0.0


@register("COUNT", 1, None, "Counts cells that contain numbers.")
def _count(*args):
    n = 0
    for a in args:
        if isinstance(a, RangeValue):
            n += sum(1 for v in a.flat() if isinstance(v, (int, float)) and not isinstance(v, bool))
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            n += 1
    return float(n)


@register("COUNTA", 1, None, "Counts non-blank cells.")
def _counta(*args):
    n = 0
    for a in args:
        if isinstance(a, RangeValue):
            n += sum(1 for v in a.flat() if v is not None and v != "")
        elif a is not None:
            n += 1
    return float(n)


@register("COUNTBLANK", 1, 1, "Counts blank cells in a range.")
def _countblank(rng):
    return float(sum(1 for v in _as_range(rng).flat() if v is None or v == ""))


def _round_half_away(x: float, digits: int) -> float:
    m = 10 ** digits
    # repr-based rounding avoids binary artefacts such as 2.675 -> 2.67
    y = abs(x) * m
    y = float(f"{y:.9f}")
    return math.copysign(math.floor(y + 0.5) / m, x)


@register("ROUND", 2, 2, "Rounds to a number of digits (half away from zero). ROUND(A1,2)")
def _round(x, digits):
    return _round_half_away(to_number(scalar(x)), int(to_number(scalar(digits))))


@register("ROUNDUP", 2, 2, "Rounds away from zero.")
def _roundup(x, digits):
    x, d = to_number(scalar(x)), int(to_number(scalar(digits)))
    m = 10 ** d
    return math.copysign(math.ceil(float(f"{abs(x) * m:.9f}")) / m, x)


@register("ROUNDDOWN", 2, 2, "Rounds towards zero.")
def _rounddown(x, digits):
    x, d = to_number(scalar(x)), int(to_number(scalar(digits)))
    m = 10 ** d
    return math.copysign(math.floor(float(f"{abs(x) * m:.9f}")) / m, x)


@register("ABS", 1, 1, "Absolute value.")
def _abs(x):
    return abs(to_number(scalar(x)))


@register("INT", 1, 1, "Rounds down to the nearest integer.")
def _int(x):
    return float(math.floor(to_number(scalar(x))))


@register("MOD", 2, 2, "Remainder after division (sign of divisor, like Excel).")
def _mod(a, b):
    a, b = to_number(scalar(a)), to_number(scalar(b))
    if b == 0:
        raise err("#DIV/0!")
    return a - b * math.floor(a / b)


@register("POWER", 2, 2, "Raises a number to a power.")
def _power(a, b):
    a, b = to_number(scalar(a)), to_number(scalar(b))
    try:
        r = a ** b
    except (OverflowError, ZeroDivisionError):
        raise err("#NUM!")
    if isinstance(r, complex):
        raise err("#NUM!")
    return float(r)


@register("SQRT", 1, 1, "Square root.")
def _sqrt(x):
    x = to_number(scalar(x))
    if x < 0:
        raise err("#NUM!", "Square root of a negative number.")
    return math.sqrt(x)


@register("SUMPRODUCT", 1, None, "Multiplies matching ranges and adds the products.")
def _sumproduct(*ranges):
    rs = [_as_range(r) for r in ranges]
    h, w = rs[0].height, rs[0].width
    if any(r.height != h or r.width != w for r in rs):
        raise err("#VALUE!", "SUMPRODUCT() ranges must be the same size.")
    total = 0.0
    for i in range(h):
        for j in range(w):
            p = 1.0
            for r in rs:
                v = check(r.rows[i][j])
                p *= float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0
            total += p
    return total


# ------------------------------------------------------------------ logic


@register("IF", 2, 3, "IF(test, value_if_true, value_if_false)", lazy=True)
def _if(ev: Evaluator, nodes):
    cond = to_bool(scalar(ev.eval(nodes[0])))
    if cond:
        return ev.eval(nodes[1])
    if len(nodes) == 3:
        return ev.eval(nodes[2])
    return False


@register("IFERROR", 2, 2, "IFERROR(value, value_if_error). Use with care: it can hide real mistakes.",
          lazy=True)
def _iferror(ev: Evaluator, nodes):
    try:
        v = ev.eval(nodes[0])
        if isinstance(v, RangeValue):
            return v
        check(v)
        return v
    except ErrorSignal:
        return ev.eval(nodes[1])


@register("IFNA", 2, 2, "IFNA(value, value_if_na)", lazy=True)
def _ifna(ev: Evaluator, nodes):
    try:
        return check(ev.eval(nodes[0]))
    except ErrorSignal as e:
        if e.error.code == "#N/A":
            return ev.eval(nodes[1])
        raise


@register("IFS", 2, None, "IFS(test1, value1, test2, value2, ...)", lazy=True)
def _ifs(ev: Evaluator, nodes):
    if len(nodes) % 2:
        raise err("#VALUE!", "IFS() needs pairs of test and value.")
    for i in range(0, len(nodes), 2):
        if to_bool(scalar(ev.eval(nodes[i]))):
            return ev.eval(nodes[i + 1])
    raise err("#N/A", "No IFS() condition was TRUE.")


@register("AND", 1, None, "TRUE if all arguments are TRUE.")
def _and(*args):
    vals = []
    for a in args:
        vals.extend(v for v in (a.flat() if isinstance(a, RangeValue) else [a]) if v is not None)
    return all(to_bool(v) for v in vals)


@register("OR", 1, None, "TRUE if any argument is TRUE.")
def _or(*args):
    vals = []
    for a in args:
        vals.extend(v for v in (a.flat() if isinstance(a, RangeValue) else [a]) if v is not None)
    return any(to_bool(v) for v in vals)


@register("NOT", 1, 1, "Reverses TRUE/FALSE.")
def _not(x):
    return not to_bool(scalar(x))


@register("ISBLANK", 1, 1, "TRUE if the cell is empty.")
def _isblank(x):
    return scalar(x) is None


@register("ISNUMBER", 1, 1, "TRUE if the value is a number.")
def _isnumber(x):
    v = scalar(x)
    return isinstance(v, (int, float)) and not isinstance(v, bool)


@register("ISERROR", 1, 1, "TRUE if the value is any error.", lazy=True)
def _iserror(ev: Evaluator, nodes):
    try:
        check(scalar(ev.eval(nodes[0])))
        return False
    except ErrorSignal:
        return True


@register("NA", 0, 0, "Returns #N/A (marks missing data on purpose).")
def _na():
    raise err("#N/A", "Marked as not available with NA().")


# ------------------------------------------------------------- conditional


_CRIT_RE = re.compile(r"^(<=|>=|<>|=|<|>)?(.*)$", re.S)


def _criterion(crit: Any):
    crit = check(scalar(crit))
    if isinstance(crit, (int, float)) and not isinstance(crit, bool):
        target = float(crit)
        return lambda v: (isinstance(v, (int, float)) and not isinstance(v, bool)
                          and compare(float(v), target, "="))
    if isinstance(crit, bool):
        return lambda v: isinstance(v, bool) and v == crit
    text = "" if crit is None else str(crit)
    op, rest = _CRIT_RE.match(text).groups()
    op = op or "="
    try:
        num = float(rest.replace(",", ""))
        is_num = rest.strip() != ""
    except ValueError:
        num, is_num = None, False
    if is_num:
        def test(v):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return compare(float(v), num, op)
            return op == "<>"
        return test
    if op in ("=", "<>") and any(ch in rest for ch in "*?"):
        pattern = re.compile("^" + re.escape(rest).replace(r"\*", ".*").replace(r"\?", ".") + "$",
                             re.I | re.S)
        hit = lambda v: isinstance(v, str) and bool(pattern.match(v))  # noqa: E731
        return hit if op == "=" else (lambda v: not hit(v))
    if rest == "" and op == "=":
        return lambda v: v is None or v == ""
    if rest == "" and op == "<>":
        return lambda v: v is not None and v != ""

    def test_text(v):
        if v is None:
            v = ""
        if not isinstance(v, str):
            return op == "<>"
        return compare(v, rest, op)
    return test_text


def _pairs(args, start: int):
    pairs = []
    for i in range(start, len(args), 2):
        rng = _as_range(args[i])
        pairs.append((rng, _criterion(args[i + 1])))
    return pairs


def _matching(pairs, h, w):
    for rng, _ in pairs:
        if rng.height != h or rng.width != w:
            raise err("#VALUE!", "All criteria ranges must be the same size as the sum range.")
    for i in range(h):
        for j in range(w):
            if all(test(rng.rows[i][j]) for rng, test in pairs):
                yield i, j


@register("SUMIF", 2, 3, "SUMIF(range, criterion, [sum_range])")
def _sumif(rng, crit, sum_rng=None):
    rng = _as_range(rng)
    target = _as_range(sum_rng) if sum_rng is not None else rng
    test = _criterion(crit)
    total = 0.0
    for i in range(rng.height):
        for j in range(rng.width):
            if test(rng.rows[i][j]):
                v = check(target.rows[i][j]) if i < target.height and j < target.width else None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    total += v
    return total


@register("SUMIFS", 3, None, "SUMIFS(sum_range, criteria_range1, criterion1, ...)")
def _sumifs(sum_rng, *rest):
    if len(rest) % 2:
        raise err("#VALUE!", "SUMIFS() needs pairs of criteria range and criterion.")
    target = _as_range(sum_rng)
    total = 0.0
    for i, j in _matching(_pairs(rest, 0), target.height, target.width):
        v = check(target.rows[i][j])
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += v
    return total


@register("COUNTIF", 2, 2, "COUNTIF(range, criterion)")
def _countif(rng, crit):
    test = _criterion(crit)
    return float(sum(1 for v in _as_range(rng).flat() if test(v)))


@register("COUNTIFS", 2, None, "COUNTIFS(range1, criterion1, ...)")
def _countifs(*args):
    if len(args) % 2:
        raise err("#VALUE!", "COUNTIFS() needs pairs of range and criterion.")
    first = _as_range(args[0])
    return float(sum(1 for _ in _matching(_pairs(args, 0), first.height, first.width)))


@register("AVERAGEIF", 2, 3, "AVERAGEIF(range, criterion, [average_range])")
def _averageif(rng, crit, avg_rng=None):
    rng = _as_range(rng)
    target = _as_range(avg_rng) if avg_rng is not None else rng
    test = _criterion(crit)
    vals = []
    for i in range(rng.height):
        for j in range(rng.width):
            if test(rng.rows[i][j]) and i < target.height and j < target.width:
                v = check(target.rows[i][j])
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append(v)
    if not vals:
        raise err("#DIV/0!", "No cells matched the criterion.")
    return sum(vals) / len(vals)


@register("AVERAGEIFS", 3, None, "AVERAGEIFS(average_range, criteria_range1, criterion1, ...)")
def _averageifs(avg_rng, *rest):
    if len(rest) % 2:
        raise err("#VALUE!", "AVERAGEIFS() needs pairs of criteria range and criterion.")
    target = _as_range(avg_rng)
    vals = []
    for i, j in _matching(_pairs(rest, 0), target.height, target.width):
        v = check(target.rows[i][j])
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(v)
    if not vals:
        raise err("#DIV/0!", "No cells matched the criteria.")
    return sum(vals) / len(vals)


# ------------------------------------------------------------------ lookup


def _match_index(value: Any, vec: list[Any], mode: int) -> int:
    value = check(scalar(value))
    if mode == 0:
        test = _criterion(value) if isinstance(value, str) else None
        for i, v in enumerate(vec):
            if test is not None:
                if isinstance(v, str) and test(v):
                    return i
            elif v is not None and not isinstance(v, str) and compare(v, value, "="):
                return i
        raise err("#N/A", f"{to_text(value)!r} was not found.")
    # approximate match: data must be sorted (ascending for 1, descending for -1)
    best = None
    for i, v in enumerate(vec):
        if v is None or isinstance(v, CellError) or _type_rank_s(v) != _type_rank_s(value):
            continue
        if mode == 1 and compare(v, value, "<="):
            best = i
        elif mode == -1 and compare(v, value, ">="):
            best = i
        else:
            break
    if best is None:
        raise err("#N/A", f"No value close enough to {to_text(value)!r}.")
    return best


def _type_rank_s(v):
    return 1 if isinstance(v, str) else (2 if isinstance(v, bool) else 0)


@register("MATCH", 2, 3, "MATCH(value, range, [match_type]) – position of a value (use 0 for exact).")
def _match(value, rng, mode=1.0):
    mode = 1 if mode is None else int(to_number(scalar(mode)))
    return float(_match_index(value, _vector(rng), mode) + 1)


@register("INDEX", 2, 3, "INDEX(range, row, [column]) – value at a position.")
def _index(rng, row, col=None):
    rng = _as_range(rng)
    r = int(to_number(scalar(row)))
    c = int(to_number(scalar(col))) if col is not None else None
    if c is None:
        if rng.height == 1:  # single row: the number picks a column
            r, c = 1, r
        else:
            c = 1
    if r < 0 or c < 0 or r > rng.height or c > rng.width:
        raise err("#REF!", "INDEX() position is outside the range.")
    if r == 0 or c == 0:
        raise err("#UNSUPPORTED!", "INDEX() with row or column 0 (whole row/column) is not supported.")
    return check(rng.rows[r - 1][c - 1])


@register("XLOOKUP", 3, 5, "XLOOKUP(value, lookup_range, return_range, [if_not_found], [match_mode])",
          lazy=True)
def _xlookup(ev: Evaluator, nodes):
    value = ev.eval(nodes[0])
    look = _vector(ev.eval(nodes[1]), "lookup range")
    ret = _as_range(ev.eval(nodes[2]))
    mode = 0
    if len(nodes) >= 5:
        mode = int(to_number(scalar(ev.eval(nodes[4]))))
        if mode not in (0, -1, 1):
            raise err("#UNSUPPORTED!", "XLOOKUP() supports match_mode 0, -1 or 1 only.")
    ret_vec = ret.flat() if ret.is_vector() else None
    if ret_vec is None or len(ret_vec) != len(look):
        raise err("#VALUE!", "XLOOKUP() lookup and return ranges must be the same length.")
    try:
        if mode == 0:
            idx = _match_index(value, look, 0)
        else:
            idx = _xlookup_nearest(scalar(value), look, mode)
    except ErrorSignal as e:
        if e.error.code == "#N/A" and len(nodes) >= 4 and not _is_empty(nodes[3]):
            return ev.eval(nodes[3])
        raise
    return check(ret_vec[idx])


def _is_empty(node):
    from .parser import Empty
    return isinstance(node, Empty)


def _xlookup_nearest(value, look, mode):
    value = to_number(value)
    best, best_v = None, None
    for i, v in enumerate(look):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if v == value:
            return i
        if mode == -1 and v < value and (best_v is None or v > best_v):
            best, best_v = i, v
        if mode == 1 and v > value and (best_v is None or v < best_v):
            best, best_v = i, v
    if best is None:
        raise err("#N/A")
    return best


@register("VLOOKUP", 3, 4, "VLOOKUP(value, table, column, [approximate]) – use FALSE for exact match.")
def _vlookup(value, table, col, approx=True):
    table = _as_range(table)
    c = int(to_number(scalar(col)))
    if c < 1 or c > table.width:
        raise err("#REF!", "VLOOKUP() column number is outside the table.")
    approx = True if approx is None else to_bool(scalar(approx))
    first = [row[0] for row in table.rows]
    idx = _match_index(value, first, 1 if approx else 0)
    return check(table.rows[idx][c - 1])


@register("HLOOKUP", 3, 4, "HLOOKUP(value, table, row, [approximate])")
def _hlookup(value, table, row, approx=True):
    table = _as_range(table)
    r = int(to_number(scalar(row)))
    if r < 1 or r > table.height:
        raise err("#REF!", "HLOOKUP() row number is outside the table.")
    approx = True if approx is None else to_bool(scalar(approx))
    idx = _match_index(value, table.rows[0], 1 if approx else 0)
    return check(table.rows[r - 1][idx])


# ------------------------------------------------------------------- dates
# Dates are Excel serial numbers (1900 date system). Serial 1 = 1900-01-01.
# Like Excel, FinPilot treats 1900 as a leap year for serials up to 60 so that
# exported workbooks agree; models in FinPilot only use dates after 1900-03-01.

_EPOCH = _dt.date(1899, 12, 30)


def serial_to_date(serial: float) -> _dt.date:
    s = int(math.floor(serial))
    if s < 61:
        raise err("#NUM!", "Dates before 1 March 1900 are not supported.")
    return _EPOCH + _dt.timedelta(days=s)


def date_to_serial(d: _dt.date) -> float:
    return float((d - _EPOCH).days)


@register("DATE", 3, 3, "DATE(year, month, day) – month and day may overflow, as in Excel.")
def _date(y, m, d):
    y, m, d = int(to_number(scalar(y))), int(to_number(scalar(m))), int(to_number(scalar(d)))
    if 0 <= y < 1900:
        y += 1900
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    try:
        base = _dt.date(y, m, 1)
    except ValueError:
        raise err("#NUM!")
    return date_to_serial(base + _dt.timedelta(days=d - 1))


@register("YEAR", 1, 1, "Year of a date.")
def _year(s):
    return float(serial_to_date(to_number(scalar(s))).year)


@register("MONTH", 1, 1, "Month (1-12) of a date.")
def _month(s):
    return float(serial_to_date(to_number(scalar(s))).month)


@register("DAY", 1, 1, "Day of the month of a date.")
def _day(s):
    return float(serial_to_date(to_number(scalar(s))).day)


def _add_months(d: _dt.date, months: int) -> tuple[int, int]:
    total = d.year * 12 + (d.month - 1) + months
    return total // 12, total % 12 + 1


@register("EOMONTH", 2, 2, "EOMONTH(date, months) – last day of the month, months ahead.")
def _eomonth(s, months):
    y, m = _add_months(serial_to_date(to_number(scalar(s))), int(to_number(scalar(months))))
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return date_to_serial(nxt - _dt.timedelta(days=1))


@register("EDATE", 2, 2, "EDATE(date, months) – same day, months ahead.")
def _edate(s, months):
    d = serial_to_date(to_number(scalar(s)))
    y, m = _add_months(d, int(to_number(scalar(months))))
    import calendar
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date_to_serial(_dt.date(y, m, day))


@register("DAYS", 2, 2, "DAYS(end, start) – number of days between two dates.")
def _days(end, start):
    return float(math.floor(to_number(scalar(end))) - math.floor(to_number(scalar(start))))


# --------------------------------------------------------------- financial


@register("PMT", 3, 5, "PMT(rate, nper, pv, [fv], [type]) – loan payment (negative = cash out).")
def _pmt(rate, nper, pv, fv=0.0, typ=0.0):
    r, n, p = to_number(scalar(rate)), to_number(scalar(nper)), to_number(scalar(pv))
    f = to_number(scalar(fv)) if fv is not None else 0.0
    t = 1.0 if (typ is not None and to_number(scalar(typ)) != 0) else 0.0
    if n == 0:
        raise err("#NUM!", "Number of periods cannot be zero.")
    if r == 0:
        return -(p + f) / n
    g = (1 + r) ** n
    return -(r * (p * g + f)) / ((1 + r * t) * (g - 1))


@register("FV", 3, 5, "FV(rate, nper, pmt, [pv], [type]) – future value.")
def _fv(rate, nper, pmt, pv=0.0, typ=0.0):
    r, n, a = to_number(scalar(rate)), to_number(scalar(nper)), to_number(scalar(pmt))
    p = to_number(scalar(pv)) if pv is not None else 0.0
    t = 1.0 if (typ is not None and to_number(scalar(typ)) != 0) else 0.0
    if r == 0:
        return -(p + a * n)
    g = (1 + r) ** n
    return -(p * g + a * (1 + r * t) * (g - 1) / r)


@register("PV", 3, 5, "PV(rate, nper, pmt, [fv], [type]) – present value.")
def _pv(rate, nper, pmt, fv=0.0, typ=0.0):
    r, n, a = to_number(scalar(rate)), to_number(scalar(nper)), to_number(scalar(pmt))
    f = to_number(scalar(fv)) if fv is not None else 0.0
    t = 1.0 if (typ is not None and to_number(scalar(typ)) != 0) else 0.0
    if r == 0:
        return -(f + a * n)
    g = (1 + r) ** n
    return -(f + a * (1 + r * t) * (g - 1) / r) / g


@register("NPV", 2, None, "NPV(rate, values...) – first value is discounted one period, as in Excel.")
def _npv(rate, *values):
    r = to_number(scalar(rate))
    if r == -1:
        raise err("#DIV/0!")
    cfs = list(_iter_values(values))
    return math.fsum(cf / (1 + r) ** (i + 1) for i, cf in enumerate(cfs))


@register("IRR", 1, 2, "IRR(values, [guess]) – internal rate of return.")
def _irr(values, guess=0.1):
    cfs = list(_iter_values([values]))
    if not (any(c > 0 for c in cfs) and any(c < 0 for c in cfs)):
        raise err("#NUM!", "IRR() needs at least one positive and one negative cash flow.")
    from ..finance import irr
    result = irr(cfs, to_number(scalar(guess)) if guess is not None else 0.1)
    if result is None:
        raise err("#NUM!", "IRR() did not converge.")
    return result


# -------------------------------------------------------------------- text


@register("CONCAT", 1, None, "Joins text.")
def _concat(*args):
    out = []
    for a in args:
        vals = a.flat() if isinstance(a, RangeValue) else [a]
        out.extend(to_text(v) for v in vals)
    return "".join(out)


@register("LEN", 1, 1, "Number of characters.")
def _len(x):
    return float(len(to_text(scalar(x))))


@register("UPPER", 1, 1, "Upper-case text.")
def _upper(x):
    return to_text(scalar(x)).upper()


@register("LOWER", 1, 1, "Lower-case text.")
def _lower(x):
    return to_text(scalar(x)).lower()


@register("LEFT", 1, 2, "First characters of text.")
def _left(x, n=1.0):
    return to_text(scalar(x))[: int(to_number(scalar(n))) if n is not None else 1]


@register("RIGHT", 1, 2, "Last characters of text.")
def _right(x, n=1.0):
    k = int(to_number(scalar(n))) if n is not None else 1
    s = to_text(scalar(x))
    return s[-k:] if k else ""
