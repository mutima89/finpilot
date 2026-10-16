"""Answer checking with specific, explanatory feedback.

Feedback never just says "wrong". It says what went wrong, why it matters
and how to fix it. Formula answers are checked by *behaviour*: the learner's
formula is evaluated on the given inputs and again on perturbed inputs, and
compared with a reference formula. This catches hard-coded numbers that happen
to give the right answer once.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.format import format_value
from ..core.formula import CellError, FormulaSyntaxError, parse
from ..core.formula.parser import Ref, function_names, numeric_literals, references
from ..core.formula.refs import a1_to_key, key_to_a1
from ..core.sheet import Sheet


@dataclass
class Feedback:
    correct: bool
    title: str
    message: str
    diagnosis: str = ""          # machine-readable cause, e.g. "hardcoded", "percent_scale"
    score: float = 0.0           # 0..1
    detail: list[str] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return not self.correct and self.score > 0


def _close(a: float, b: float, tol: float, rel: float) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=tol)


def _num(text: Any) -> Optional[float]:
    """Read a typed number: accepts 1,250  $1,250  -1250  (1,250)  12.5%  1.2k  3.4m."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    if not isinstance(text, str):
        return None
    s = text.strip().replace(",", "").replace("$", "").replace(" ", "").replace("\u2212", "-")
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):  # accounting negative
        neg, s = True, s[1:-1]
    mult = 1.0
    if s.endswith("%"):
        mult, s = 0.01, s[:-1]
    elif s[-1:].lower() in ("k", "m") and len(s) > 1:
        mult, s = (1e3 if s[-1].lower() == "k" else 1e6), s[:-1]
    s = s.replace("$", "")
    try:
        v = float(s) * mult
    except ValueError:
        return None
    return -v if neg else v


# ------------------------------------------------------------------ numbers


def grade_number(answer: Any, expected: float, *, tol: float = 0.01, rel: float = 0.0,
                 fmt: str = "general", mistakes: Optional[list[dict]] = None,
                 explanation: str = "") -> Feedback:
    """Grade a numeric answer.

    ``mistakes`` lists known wrong answers with a targeted explanation, e.g.
    {"value": 0.7, "message": "That is a simple average of the monthly rates..."}.
    Percent answers may be typed as 0.75, 75% or 75 (when fmt is a percent format).
    """
    v = _num(answer)
    shown = format_value(expected, fmt)
    if v is None:
        return Feedback(False, "Enter a number",
                        "Your answer could not be read as a number. Type digits only, for example 1250 "
                        "or 12.5%.", "not_a_number")
    candidates = [v]
    if fmt.startswith("percent") and isinstance(answer, str) and "%" not in answer and abs(v) > 1.5:
        candidates.append(v / 100)  # "75" meaning 75%
    for c in candidates:
        if _close(c, expected, tol, rel):
            return Feedback(True, "Correct", explanation or f"The answer is {shown}.", "correct", 1.0)
    for m in mistakes or []:
        for c in candidates:
            if _close(c, float(m["value"]), m.get("tol", tol), rel):
                return Feedback(False, "Not quite - a common mistake", m["message"], m.get("code", "known"),
                                0.0)
    # generic diagnoses
    if expected != 0:
        ratio = v / expected
        if _close(abs(ratio), 100, 0.5, 0.005) or _close(abs(ratio), 0.01, 1e-4, 0.005):
            return Feedback(False, "Check your units",
                            f"Your answer is 100 times too {'large' if abs(ratio) > 1 else 'small'}. "
                            "This usually means a percentage was entered as a whole number (75 instead of "
                            "0.75) or the other way round. Percentages are decimals in calculations.",
                            "percent_scale")
        if _close(ratio, -1, 1e-6, 1e-6):
            return Feedback(False, "Check the sign",
                            "Your answer has the right size but the wrong sign. Check which value is "
                            "subtracted from which (variance = actual - budget).", "sign")
        if _close(abs(ratio), 1, 0.0, 0.02):
            return Feedback(False, "Very close",
                            "You are within 2% of the answer. Check rounding: keep full precision in "
                            "intermediate steps and round only the final result.", "rounding", 0.5)
        if _close(v * expected, 1, 1e-6, 0.01):
            return Feedback(False, "Upside down",
                            "Your answer is the reciprocal of the right one. The numerator and "
                            "denominator are swapped.", "inverted")
    return Feedback(False, "Not correct yet",
                    "That is not the expected result. Re-read which values the question gives, write "
                    "the formula in words first, then substitute the numbers.", "wrong")


def grade_choice(selected: Optional[int], correct: int, options: list[str],
                 explanations: Optional[list[str]] = None, explanation: str = "") -> Feedback:
    if selected is None:
        return Feedback(False, "Choose an answer", "Select one option first.", "no_answer")
    if selected == correct:
        return Feedback(True, "Correct", explanation or options[correct], "correct", 1.0)
    why = ""
    if explanations and selected < len(explanations) and explanations[selected]:
        why = explanations[selected]
    msg = (why + " " if why else "") + (explanation and f"Key idea: {explanation}" or "")
    return Feedback(False, "Not this one", msg.strip() or "Think again about the definition.", "wrong_choice")


# ----------------------------------------------------------------- formulas


@dataclass
class FormulaTask:
    """Build a formula in ``target`` that behaves like ``reference``.

    cells:    the given mini-sheet {"A1": "Rooms", "B1": "150", ...}
    perturb:  alternative values for input cells used to detect hard-coding,
              e.g. [{"B1": "200"}, {"B1": "0", "B2": "0.5"}]
    require_functions / forbid_functions: optional structural rules.
    fill_to:  if set (e.g. "M4"), the learner's formula is copied across the row and
              every copy must also match (tests absolute/relative references).
    """
    target: str
    reference: str
    cells: dict[str, str]
    perturb: list[dict[str, str]] = field(default_factory=list)
    require_functions: list[str] = field(default_factory=list)
    forbid_functions: list[str] = field(default_factory=list)
    fill_to: Optional[str] = None
    fmt: str = "general"
    tol: float = 1e-6
    names: dict[str, str] = field(default_factory=dict)

    def sheet(self, overrides: Optional[dict[str, str]] = None) -> Sheet:
        s = Sheet("Task", rows=30, cols=16)
        items = [(k, v) for k, v in {**self.cells, **(overrides or {})}.items()]
        s.set_many(items, record=False)
        for n, t in self.names.items():
            s.names[n.upper()] = t
        s.recalculate()
        return s


def _equal(a: Any, b: Any, tol: float) -> bool:
    if isinstance(a, CellError) or isinstance(b, CellError):
        return isinstance(a, CellError) and isinstance(b, CellError) and a.code == b.code
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=tol)
    if a is None or b is None:
        return (a in (None, 0, 0.0, "")) and (b in (None, 0, 0.0, ""))
    return str(a).strip().lower() == str(b).strip().lower()


def _targets(task: FormulaTask) -> list[str]:
    if not task.fill_to:
        return [task.target]
    r0, c0 = a1_to_key(task.target)
    r1, c1 = a1_to_key(task.fill_to)
    return [key_to_a1((r0, c)) for c in range(c0, c1 + 1)] if r0 == r1 else \
           [key_to_a1((r, c0)) for r in range(r0, r1 + 1)]


def _place(sheet: Sheet, task: FormulaTask, formula: str) -> None:
    sheet.set(task.target, formula)
    if task.fill_to:
        tr = a1_to_key(task.target)
        sheet.fill(tr, [a1_to_key(t) for t in _targets(task)[1:]])


def grade_formula(task: FormulaTask, formula: str) -> Feedback:
    text = (formula or "").strip()
    if not text:
        return Feedback(False, "Enter a formula", "Type a formula starting with '='.", "empty")
    if not text.startswith("="):
        v = _num(text)
        if v is not None:
            return Feedback(False, "That is a typed number, not a formula",
                            "You entered a value. Models must calculate results from their inputs so "
                            "they update when assumptions change. Start with '=' and refer to the input "
                            "cells, for example =B1*B2.", "hardcoded_value")
        text = "=" + text
    try:
        node = parse(text)
    except FormulaSyntaxError as e:
        return Feedback(False, "The formula cannot be read", f"{e} Check brackets and commas.", "syntax")

    target_key = a1_to_key(task.target)
    refs = references(node)
    for r in refs:
        if isinstance(r, Ref) and r.ref.key == target_key:
            return Feedback(False, "Circular reference",
                            f"The formula refers to its own cell ({task.target}). A cell cannot use its own "
                            "result. Refer to the input cells instead.", "circular")
    if not refs:
        return Feedback(False, "No cell references",
                        "The formula only contains numbers, so it will not update when the inputs change. "
                        "Refer to the input cells (for example B2) instead of typing their values.",
                        "hardcoded_value")

    used = function_names(node)
    for fn in task.require_functions:
        if fn.upper() not in used:
            return Feedback(False, f"Use {fn.upper()}()",
                            f"This task practises {fn.upper()}(). Your formula may give a number, but "
                            f"rewrite it using {fn.upper()}().", "missing_function", 0.3)
    for fn in task.forbid_functions:
        if fn.upper() in used:
            return Feedback(False, f"Avoid {fn.upper()}() here",
                            f"{fn.upper()}() is not appropriate for this task. "
                            + ("IFERROR hides every error, including real mistakes. Test the specific "
                               "condition with IF instead." if fn.upper() == "IFERROR" else ""),
                            "forbidden_function", 0.3)

    scenarios = [None] + list(task.perturb)
    targets = _targets(task)
    first_ok = None
    for idx, ov in enumerate(scenarios):
        learner = task.sheet(ov)
        _place(learner, task, text)
        ref = task.sheet(ov)
        _place(ref, task, task.reference)
        mism = [t for t in targets if not _equal(learner.value(t), ref.value(t), task.tol)]
        if idx == 0:
            first_ok = not mism
        if mism:
            got, exp = learner.value(mism[0]), ref.value(mism[0])
            return _formula_mismatch(task, text, node, idx, ov, mism, got, exp, first_ok, targets)
    lits = [x for x in numeric_literals(node) if x not in (0, 1, 100, 12, 2)]
    detail = []
    if lits:
        detail.append("Your formula contains typed numbers (" + ", ".join(f"{x:g}" for x in lits[:3])
                      + "). Constants are fine when they never change; otherwise put them in an input cell.")
    v = task.sheet()
    _place(v, task, text)
    return Feedback(True, "Correct - and it updates with the inputs",
                    f"{task.target} = {format_value(v.value(task.target), task.fmt)}. Your formula gives "
                    "the right answer on the original inputs and on changed inputs, so it is properly linked.",
                    "correct", 1.0, detail)


def _formula_mismatch(task, text, node, idx, ov, mism, got, exp, first_ok, targets) -> Feedback:
    shown_got = format_value(got, task.fmt)
    shown_exp = format_value(exp, task.fmt)
    if isinstance(got, CellError):
        return Feedback(False, f"The formula returns {got.code}", got.explanation +
                        (f" (in {mism[0]})" if len(targets) > 1 else ""), "error_value")
    if idx > 0 and first_ok:
        changed = ", ".join(f"{k} = {v}" for k, v in (ov or {}).items())
        return Feedback(False, "Right answer, but not linked to the inputs",
                        f"Your formula gives the right number for the original inputs but the wrong one "
                        f"when the inputs change ({changed}): it returned {shown_got} instead of {shown_exp}. "
                        "This usually means a value was typed into the formula instead of referencing its "
                        "cell. Replace typed numbers with cell references.", "hardcoded", 0.4)
    if len(targets) > 1 and mism[0] != targets[0] and _equal_first(task, text):
        return Feedback(False, "Works in the first column only",
                        f"The first month is right, but the copy in {mism[0]} is wrong ({shown_got} instead of "
                        f"{shown_exp}). When the formula is copied across, a reference that should stay fixed "
                        "(like the room count) moved too. Anchor it with $ signs, for example $B$4.",
                        "absolute_ref", 0.5)
    if isinstance(got, (int, float)) and isinstance(exp, (int, float)) and exp != 0 and not isinstance(got, bool):
        ratio = got / exp
        if math.isclose(abs(ratio), 100, rel_tol=0.01) or math.isclose(abs(ratio), 0.01, rel_tol=0.01):
            return Feedback(False, "Check the percentage scale",
                            f"Result {shown_got} is 100 times off from {shown_exp}. Percent inputs are "
                            "already decimals (75% = 0.75); do not multiply or divide by 100 again.",
                            "percent_scale", 0.3)
        if math.isclose(ratio, -1, rel_tol=1e-6):
            return Feedback(False, "Wrong sign",
                            f"You got {shown_got}; expected {shown_exp}. The subtraction is the wrong way "
                            "round.", "sign", 0.3)
        if math.isclose(got * exp, 1, rel_tol=1e-6):
            return Feedback(False, "Upside down", "The division is inverted: swap numerator and denominator.",
                            "inverted", 0.2)
    return Feedback(False, "Not the expected result",
                    f"{mism[0]} shows {shown_got} but should show {shown_exp}. Say the calculation in words, "
                    "then check that each reference points at the right input.", "wrong")


def _equal_first(task: FormulaTask, text: str) -> bool:
    learner = task.sheet()
    learner.set(task.target, text)
    ref = task.sheet()
    ref.set(task.target, task.reference)
    return _equal(learner.value(task.target), ref.value(task.target), task.tol)


# ------------------------------------------------------------ free text


def grade_written(text: str, rubric: list[dict]) -> tuple[Feedback, list[tuple[str, bool]]]:
    """Transparent rubric check for written recommendations.

    Each rubric item: {"criterion": "...", "any": ["keyword", ...]} or {"criterion": "...", "numbers": 2}.
    This only detects *presence* of required elements; it cannot judge quality,
    so the learner also self-assesses (the UI says this plainly).
    """
    import re
    lowered = (text or "").lower()
    results = []
    for item in rubric:
        ok = True
        if "any" in item:
            ok = any(k.lower() in lowered for k in item["any"])
        if "numbers" in item:
            ok = ok and len(re.findall(r"\d[\d,.]*%?", lowered)) >= int(item["numbers"])
        if "min_words" in item:
            ok = ok and len(lowered.split()) >= int(item["min_words"])
        results.append((item["criterion"], ok))
    met = sum(1 for _, ok in results if ok)
    score = met / len(results) if results else 0.0
    fb = Feedback(score >= 0.75, f"{met} of {len(results)} rubric elements found",
                  "FinPilot checks that the recommendation contains the required elements. It cannot "
                  "judge the quality of your argument, so compare your answer with the model answer.",
                  "rubric", score)
    return fb, results
