"""Answer grading, curriculum integrity, the guided hotel project checker and practice drills."""
import pytest

from finpilot.core import hotel as H
from finpilot.core import hotel_sheet as hs
from finpilot.curriculum import STEP_SEQUENCE, formula_task, item_refs, validate
from finpilot.curriculum import drills
from finpilot.curriculum import hotel_project as hp
from finpilot.curriculum.grading import FormulaTask, grade_choice, grade_formula, grade_number, grade_written


# ---------------------------------------------------------------- numbers
@pytest.mark.parametrize("typed", ["0.75", "75%", "75", " 75 % "])
def test_percent_answers_accept_common_notations(typed):
    assert grade_number(typed.replace(" ", ""), 0.75, fmt="percent").correct


@pytest.mark.parametrize("typed", ["(20,000)", "-20000", "-$20,000", "$(20,000)", "-20k"])
def test_negative_money_accepts_accounting_notation(typed):
    assert grade_number(typed, -20000, fmt="currency0", tol=0.5).correct


def test_number_diagnoses():
    assert grade_number("abc", 5).diagnosis == "not_a_number"
    fb = grade_number("7500", 75, fmt="general")
    assert not fb.correct and "unit" in fb.title.lower()
    fb = grade_number("20000", -20000)
    assert not fb.correct and fb.diagnosis
    known = grade_number("0.7", 0.72, mistakes=[{"value": 0.7, "message": "simple average"}])
    assert not known.correct and "simple average" in known.message


def test_choice():
    assert grade_choice(1, 1, ["a", "b"]).correct
    assert not grade_choice(0, 1, ["a", "b"]).correct
    assert not grade_choice(None, 1, ["a", "b"]).correct


# ---------------------------------------------------------------- formulas
def _rev_task(**kw):
    return FormulaTask(target="B5", reference="=B3*B4", cells={"A3": "Rooms sold", "B3": "100", "A4": "ADR",
                                                               "B4": "250"},
                       perturb=[{"B3": "120"}, {"B4": "199"}], **kw)


def test_formula_correct_and_equivalent_forms():
    t = _rev_task()
    assert grade_formula(t, "=B3*B4").correct
    assert grade_formula(t, "=B4*B3").correct
    assert grade_formula(t, "b3*b4").correct


def test_formula_hardcoding_is_caught_even_when_value_is_right():
    t = _rev_task()
    for f in ("25000", "=25000", "=100*250", "=B3*250"):
        fb = grade_formula(t, f)
        assert not fb.correct, f
        assert "hardcoded" in fb.diagnosis, (f, fb.diagnosis)


def test_formula_circular_and_syntax():
    t = _rev_task()
    assert grade_formula(t, "=B5*2").diagnosis == "circular"
    assert grade_formula(t, "=B3*(B4").diagnosis == "syntax"
    assert grade_formula(t, "").diagnosis == "empty"


def test_formula_missing_absolute_reference_detected_on_fill():
    t = FormulaTask(target="B3", reference="=$B$1*B2", fill_to="D3",
                    cells={"B1": "180", "B2": "31", "C2": "28", "D2": "31"}, perturb=[{"B1": "200"}])
    assert grade_formula(t, "=$B$1*B2").correct
    fb = grade_formula(t, "=B1*B2")
    assert not fb.correct


def test_required_function_enforced():
    t = FormulaTask(target="B4", reference="=SUM(B1:B3)", cells={"B1": "1", "B2": "2", "B3": "3"},
                    perturb=[{"B2": "5"}], require_functions=["SUM"])
    assert grade_formula(t, "=SUM(B1:B3)").correct
    assert grade_formula(t, "=B1+B2+B3").diagnosis == "missing_function"


def test_written_rubric_is_transparent():
    rubric = [{"criterion": "States a recommendation", "any": ["recommend"]},
              {"criterion": "Quantifies with at least two numbers", "numbers": 2}]
    fb, res = grade_written("I recommend protecting rate: revenue is $17.5m vs $17.4m budget.", rubric)
    assert all(ok for _, ok in res) and fb.correct
    fb, res = grade_written("Looks fine to me overall honestly.", rubric)
    assert not fb.correct and [ok for _, ok in res] == [False, False]


# ---------------------------------------------------------------- curriculum
def test_curriculum_validates(cur):
    assert validate(cur) == []


def test_curriculum_shape(cur):
    assert len(cur.levels) == 10
    avail = [lv for lv in cur.levels if lv.status == "available"]
    assert [lv.number for lv in avail] == [1, 2, 3]
    lessons = [l for l in cur.lessons if l.kind == "lesson"]
    assert len(lessons) == 18
    for l in lessons:
        assert [s["type"] for s in l.steps] == STEP_SEQUENCE
        assert l.skills, l.id
    assert cur.lesson("P1") is not None and cur.lesson("P3").kind == "lab_project"


def test_every_formula_item_reference_passes_its_own_grader(cur):
    n = 0
    for ref, (lesson_id, q, skills) in item_refs(cur).items():
        if q.get("kind") == "formula" or "reference" in q:
            t = formula_task(q)
            assert grade_formula(t, t.reference).correct, ref
            n += 1
    assert n >= 20


def test_all_fictional_data_is_labelled(cur):
    from finpilot.config import resource_path
    text = " ".join(p.read_text(encoding="utf-8") for p in resource_path("curriculum", "content").glob("*.json"))
    assert "fictional" in text.lower()


def test_final_assessment_definition(cur):
    a = cur.assessment
    assert a["pass_overall"] == 0.7 and a["pass_section"] == 0.5
    assert len({it["section"] for it in a["items"]}) == 6
    assert any(it["kind"] == "written" for it in a["items"])


# ---------------------------------------------------------------- hotel project checker
def _guided_sheet():
    return hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=False)


def test_reference_model_validates_and_matches_python():
    s = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
    st = hp.project_status(s)
    assert st["done"] == 10 and st["validated"] and st["checks_ok"]
    assert round(s.value(f"{hs.TOT}{hs.R_RREV}")) == 17_484_066


def test_guided_sheet_starts_empty_with_honest_checks():
    s = _guided_sheet()
    st = hp.project_status(s)
    assert st["done"] == 0 and not st["validated"]
    assert s.value(f"B{hs.R_CHK1}") == "not built"


def test_task_checker_catches_typed_values():
    s = _guided_sheet()
    t = hp.TASKS[0]
    ref_vals = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
    for c in t.cells:
        s.set(c, str(ref_vals.value(c)))       # right numbers, typed in
    fb = hp.check_task(s, t)
    assert not fb.correct and fb.diagnosis in ("typed", "hardcoded", "hardcoded_value")


def test_task_checker_catches_missing_anchor():
    s = _guided_sheet()
    t = hp.TASKS[0]                      # available room nights = $B$4 * days
    s.set(t.cells[0], "=B4*B9")
    s.fill((hs.R_AVAIL - 1, 1), [(hs.R_AVAIL - 1, c) for c in range(2, 13)])
    fb = hp.check_task(s, t)
    assert not fb.correct


def test_task_checker_accepts_reference_and_named_range():
    s = _guided_sheet()
    t = hp.TASKS[0]
    for c in t.cells:
        s.set(c, t.reference[c])
    assert hp.check_task(s, t).correct
    s2 = _guided_sheet()
    s2.set(t.cells[0], "=ROOMS*B9")
    s2.fill((hs.R_AVAIL - 1, 1), [(hs.R_AVAIL - 1, c) for c in range(2, 13)])
    assert hp.check_task(s2, t).correct


def test_weighted_annual_kpi_task_rejects_average():
    s = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
    t9 = hp.task("T9")
    occ_cell = next(c for c in t9.cells if c.endswith(str(hs.R_OCC)))
    s.set(occ_cell, f"=AVERAGE(B{hs.R_OCC}:M{hs.R_OCC})")
    assert not hp.check_task(s, t9).correct


# ---------------------------------------------------------------- drills
@pytest.mark.parametrize("key", sorted(drills.DRILLS))
def test_every_drill_reference_is_correct_for_many_seeds(key):
    for seed in range(15):
        q = drills.generate(key, seed)
        t = formula_task(q)
        assert grade_formula(t, t.reference).correct, (key, seed)


def test_guided_sheet_provides_budget_total_and_formats():
    s = _guided_sheet()
    assert round(s.value(f"{hs.TOT}{hs.R_BUDGET}")) == 17_366_058
    assert s.get((hs.R_RREV - 1, 1)).fmt == "currency0"          # B17 formatted before it is built
    assert not s.errors()


def test_model_with_an_error_cell_is_not_validated():
    s = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
    s.set("P40", "=1/0")
    assert not hp.project_status(s)["validated"]
