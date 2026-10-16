"""Curriculum loading, validation and lesson models.

Curriculum content lives in JSON files under ``curriculum/content``. Every
lesson follows FinPilot's ten-step sequence::

    understand -> see -> build -> predict -> test -> explain -> apply -> recall -> review -> progress

The tenth step (progress) is generated at runtime from the learner's results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..config import resource_path

STEP_SEQUENCE = ["understand", "see", "build", "predict", "test", "explain", "apply", "recall", "review"]
STEP_TITLES = {
    "understand": "Understand", "see": "See", "build": "Build", "predict": "Predict", "test": "Test",
    "explain": "Explain", "apply": "Apply", "recall": "Recall", "review": "Review", "progress": "Progress", "written": "Write",
}


@dataclass
class Lesson:
    id: str
    level: int
    title: str
    summary: str
    minutes: int
    skills: list[str]
    prereqs: list[str]
    steps: list[dict]
    kind: str = "lesson"   # lesson | project | assessment

    def step(self, kind: str) -> Optional[dict]:
        for s in self.steps:
            if s["type"] == kind:
                return s
        return None


@dataclass
class Level:
    number: int
    title: str
    summary: str
    status: str            # available | preview | planned
    topics: list[str]
    lessons: list[Lesson] = field(default_factory=list)
    project: Optional[dict] = None


@dataclass
class Curriculum:
    levels: list[Level]
    skills: dict[str, dict]
    assessment: dict

    @property
    def lessons(self) -> list[Lesson]:
        return [l for lv in self.levels for l in lv.lessons]

    def lesson(self, lesson_id: str) -> Optional[Lesson]:
        for l in self.lessons:
            if l.id == lesson_id:
                return l
        return None

    def level(self, n: int) -> Optional[Level]:
        for lv in self.levels:
            if lv.number == n:
                return lv
        return None


class CurriculumError(ValueError):
    pass


def content_dir() -> Path:
    return resource_path("curriculum", "content")


def _read(name: str) -> Any:
    path = content_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CurriculumError(f"Curriculum file missing: {path}")
    except json.JSONDecodeError as e:
        raise CurriculumError(f"Curriculum file {name} is not valid JSON: {e}")


@lru_cache(maxsize=1)
def load() -> Curriculum:
    meta = _read("levels.json")
    skills = {s["id"]: s for s in _read("skills.json")["skills"]}
    levels: list[Level] = []
    for lm in meta["levels"]:
        lv = Level(lm["number"], lm["title"], lm["summary"], lm["status"], lm.get("topics", []))
        if lm.get("file"):
            data = _read(lm["file"])
            for ld in data["lessons"]:
                lv.lessons.append(Lesson(
                    id=ld["id"], level=lv.number, title=ld["title"], summary=ld.get("summary", ""),
                    minutes=int(ld.get("minutes", 10)), skills=ld.get("skills", []),
                    prereqs=ld.get("prereqs", []), steps=ld["steps"], kind=ld.get("kind", "lesson")))
            lv.project = data.get("project")
        levels.append(lv)
    assessment = _read("final_assessment.json")
    cur = Curriculum(levels, skills, assessment)
    problems = validate(cur)
    if problems:
        raise CurriculumError("Curriculum validation failed:\n" + "\n".join(problems))
    return cur


def validate(cur: Curriculum) -> list[str]:
    """Structural and calculation checks for all content (also run by the test suite)."""
    from ..core.formula import CellError, evaluate
    from .grading import grade_formula

    problems: list[str] = []
    ids = set()
    for lesson in cur.lessons:
        where = f"{lesson.id} '{lesson.title}'"
        if lesson.id in ids:
            problems.append(f"{where}: duplicate id")
        ids.add(lesson.id)
        types = [s["type"] for s in lesson.steps]
        if lesson.kind == "lesson" and types != STEP_SEQUENCE:
            problems.append(f"{where}: steps must be {STEP_SEQUENCE}, got {types}")
        for sk in lesson.skills:
            if sk not in cur.skills:
                problems.append(f"{where}: unknown skill {sk}")
        for p in lesson.prereqs:
            if p not in ids:
                problems.append(f"{where}: prerequisite {p} must appear earlier")
        for s in lesson.steps:
            t = s["type"]
            if t == "build":
                for task in s.get("tasks", [s]):
                    if task.get("mode", "formula") == "formula":
                        ft = formula_task(task)
                        fb = grade_formula(ft, ft.reference)
                        if not fb.correct:
                            problems.append(f"{where}: build reference fails its own check: {fb.message}")
                        for alt in task.get("also_correct", []):
                            if not grade_formula(ft, alt).correct:
                                problems.append(f"{where}: alternative answer {alt} not accepted")
                    elif "answer" not in task:
                        problems.append(f"{where}: numeric build task needs an answer")
            if t == "test":
                vals = {i["name"]: i["value"] for i in s["inputs"]}
                for o in s["outputs"]:
                    v = evaluate(o["formula"], names=vals)
                    if isinstance(v, CellError):
                        problems.append(f"{where}: test output {o['label']} -> {v.code} {v.detail}")
            if t == "predict":
                if not 0 <= s["correct"] < len(s["options"]):
                    problems.append(f"{where}: predict correct index out of range")
            if t in ("apply", "recall"):
                for q in s.get("questions", [s] if t == "apply" else []):
                    problems.extend(_check_question(where, q))
    for q in cur.assessment.get("items", []):
        problems.extend(_check_question("final assessment", q))
    return problems


def _check_question(where: str, q: dict) -> list[str]:
    from ..core.formula import CellError, evaluate
    from .grading import grade_formula
    out = []
    kind = q.get("kind", "choice")
    if kind == "choice":
        if not 0 <= q["correct"] < len(q["options"]):
            out.append(f"{where}: question '{q['question'][:40]}' correct index out of range")
    elif kind == "number":
        if "answer_formula" in q:
            v = evaluate(q["answer_formula"], names=q.get("given", {}))
            if isinstance(v, CellError) or abs(v - q["answer"]) > max(q.get("tol", 0.01), 1e-9):
                out.append(f"{where}: '{q['question'][:40]}' answer {q['answer']} != formula result {v}")
    elif kind == "formula":
        ft = formula_task(q)
        if not grade_formula(ft, ft.reference).correct:
            out.append(f"{where}: formula question reference fails")
    elif kind == "written":
        if not q.get("rubric"):
            out.append(f"{where}: written question needs a rubric")
    return out


def formula_task(d: dict):
    from .grading import FormulaTask
    return FormulaTask(target=d["target"], reference=d["reference"], cells=d["cells"],
                       perturb=d.get("perturb", []), require_functions=d.get("require_functions", []),
                       forbid_functions=d.get("forbid_functions", []), fill_to=d.get("fill_to"),
                       fmt=d.get("fmt", "general"), names=d.get("names", {}))


def item_refs(cur: Curriculum) -> dict[str, tuple[str, dict, list[str]]]:
    """Every gradable item by reference -> (lesson id, question dict, skills).

    References are stable and used by the mistakes notebook and step results:
    ``L1.1/build``, ``L1.1/apply``, ``P1/apply2-0``, ``L1.1/recall-1``, ``final/K1``.
    """
    out: dict[str, tuple[str, dict, list[str]]] = {}
    for lesson in cur.lessons:
        for si, step in enumerate(lesson.steps):
            t = step["type"]
            if t == "build":
                out[f"{lesson.id}/build"] = (lesson.id, step, lesson.skills)
            elif t == "apply":
                if "questions" in step:
                    for i, q in enumerate(step["questions"]):
                        out[f"{lesson.id}/apply{si}-{i}"] = (lesson.id, q, lesson.skills)
                else:
                    out[f"{lesson.id}/apply"] = (lesson.id, step, lesson.skills)
            elif t == "recall":
                for i, q in enumerate(step["questions"]):
                    out[f"{lesson.id}/recall-{i}"] = (lesson.id, q, lesson.skills)
            elif t == "written":
                out[f"{lesson.id}/written{si}"] = (lesson.id, step, lesson.skills)
    for q in cur.assessment.get("items", []):
        out[f"final/{q['id']}"] = ("final", q, q.get("skills", []))
    return out
