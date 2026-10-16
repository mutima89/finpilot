"""Spreadsheet model: recalculation, dependencies, cycles, undo/redo, fill and names."""
from finpilot.core.formula import CellError
from finpilot.core.sheet import Sheet, explain


def test_recalculates_dependents_in_order():
    s = Sheet("t", rows=10, cols=5)
    s.set("A1", "10")
    s.set("A2", "=A1*2")
    s.set("A3", "=A2+A1")
    assert s.value("A3") == 30
    s.set("A1", "1")
    assert s.value("A2") == 2 and s.value("A3") == 3


def test_circular_reference_is_flagged_not_looped():
    s = Sheet("t", rows=10, cols=5)
    s.set("A1", "=A2+1")
    s.set("A2", "=A1+1")
    v = s.value("A1")
    assert isinstance(v, CellError) and v.code == "#CIRC!"


def test_undo_redo():
    s = Sheet("t", rows=10, cols=5)
    s.set("A1", "5")
    s.set("A1", "7")
    assert s.undo() and s.value("A1") == 5
    assert s.redo() and s.value("A1") == 7


def test_fill_right_shifts_relative_references_only():
    s = Sheet("t", rows=20, cols=6)
    s.set("B4", "180")
    for c, d in zip("BCD", (31, 28, 31)):
        s.set(f"{c}9", str(d))
    s.set("B15", "=$B$4*B9")
    s.fill_right((14, 1), 3)
    assert s.raw("C15") == "=$B$4*C9"
    assert s.raw("D15") == "=$B$4*D9"
    assert [s.value(f"{c}15") for c in "BCD"] == [5580, 5040, 5580]


def test_named_range():
    s = Sheet("t", rows=10, cols=5)
    s.set("B4", "180")
    s.define_name("ROOMS", "B4")
    s.set("C1", "=ROOMS*30")
    assert s.value("C1") == 5400


def test_round_trip_dict():
    s = Sheet("t", rows=10, cols=5)
    s.set("A1", "3")
    s.set("A2", "=A1^2", role="calc", fmt="number")
    t = Sheet.from_dict(s.to_dict())
    assert t.value("A2") == 9 and t.raw("A2") == "=A1^2"


def test_explain_mentions_inputs():
    s = Sheet("t", rows=10, cols=5)
    s.set("A1", "3")
    s.set("A2", "=A1*4")
    text = " ".join(explain(s, (1, 0)))
    assert "A2 contains =A1*4" in text and "A1 = 3" in text and "12" in text
