"""Learning progression: unlocking, recommendations, XP, badges and competency.

Design rules from the FinPilot brief:
* Reward correct reasoning and validated models, not screen visits.
* XP is awarded once per item (no farming by repeating).
* A quiz alone never proves modeling competence: model-building skills need
  evidence from a validated model.
* No streak penalties, no timers.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from . import Curriculum, Lesson
from ..data.db import Database

# Score for a gradable item by number of attempts (solution revealed = 0).
ATTEMPT_SCORES = {1: 1.0, 2: 0.6}
LATER_ATTEMPT_SCORE = 0.3
MASTERY_THRESHOLD = 0.8

XP_RULES = {
    "item_first_try": 10,
    "item_correct": 5,
    "lesson_complete": 20,
    "lesson_mastered": 30,
    "project_task": 25,
    "project_validated": 150,
    "final_passed": 200,
    "review_correct": 5,
}

BADGES = {
    "first_link": ("First linked formula", "Built a formula that updates with its inputs."),
    "foundations": ("Foundations complete", "Completed every Level 1 lesson."),
    "spreadsheet_pro": ("Formula fluent", "Completed every Level 2 lesson."),
    "revenue_analyst": ("Revenue analyst", "Completed every Level 3 lesson."),
    "cash_detective": ("Cash detective", "Completed the profit-versus-cash project."),
    "model_builder": ("Model builder", "Built and validated the 12-month hotel model."),
    "certified_v1": ("V1 competency", "Passed the final practical assessment with a validated model."),
    "mistake_hunter": ("Mistake hunter", "Resolved five mistakes through spaced review."),
    "personal_best": ("Personal best", "Improved a previous final assessment score."),
    "mastery_10": ("Ten mastered", "Mastered ten lessons (80%+)."),
}


def item_score(attempts: int, correct: bool, revealed: bool = False) -> float:
    if revealed or not correct:
        return 0.0
    return ATTEMPT_SCORES.get(attempts, LATER_ATTEMPT_SCORE)


# ------------------------------------------------------------------ status


def level_unlocked(cur: Curriculum, db: Database, n: int) -> bool:
    if db.get_setting("unlock_all"):
        return True
    lv = cur.level(n)
    if lv is None or lv.status == "planned":
        return False
    if n == 1:
        return True
    prev = cur.level(n - 1)
    if prev is None or prev.status != "available":
        return True
    progress = db.all_progress()
    return all(progress.get(l.id, {}).get("status") == "completed" for l in prev.lessons if l.kind == "lesson")


def lesson_status(cur: Curriculum, db: Database, lesson: Lesson, progress: Optional[dict] = None) -> str:
    progress = progress if progress is not None else db.all_progress()
    p = progress.get(lesson.id)
    if p and p["status"] == "completed":
        return "mastered" if (p.get("best_score") or 0) >= MASTERY_THRESHOLD else "completed"
    if not level_unlocked(cur, db, lesson.level):
        return "locked"
    if not db.get_setting("unlock_all"):
        for pre in lesson.prereqs:
            if progress.get(pre, {}).get("status") != "completed":
                return "locked"
    if p:
        return "in_progress"
    return "available"


def missing_prereqs(cur: Curriculum, db: Database, lesson: Lesson) -> list[str]:
    progress = db.all_progress()
    out = [cur.lesson(p).title for p in lesson.prereqs
           if progress.get(p, {}).get("status") != "completed" and cur.lesson(p)]
    if not level_unlocked(cur, db, lesson.level):
        out.insert(0, f"All Level {lesson.level - 1} lessons")
    return out


def final_assessment_unlocked(cur: Curriculum, db: Database) -> bool:
    if db.get_setting("unlock_all"):
        return True
    progress = db.all_progress()
    return all(progress.get(l.id, {}).get("status") == "completed"
               for lv in cur.levels if lv.status == "available" for l in lv.lessons if l.kind == "lesson")


def overall_progress(cur: Curriculum, db: Database) -> float:
    items = [l for l in cur.lessons]
    if not items:
        return 0.0
    progress = db.all_progress()
    done = sum(1 for l in items if progress.get(l.id, {}).get("status") == "completed")
    final = 1 if any(a["passed"] for a in db.assessments("final")) else 0
    return (done + final) / (len(items) + 1)


def current_level(cur: Curriculum, db: Database) -> int:
    progress = db.all_progress()
    for lv in cur.levels:
        if lv.status != "available":
            continue
        if any(progress.get(l.id, {}).get("status") != "completed" for l in lv.lessons):
            return lv.number
    return max(lv.number for lv in cur.levels if lv.status == "available")


@dataclass
class Recommendation:
    kind: str       # lesson | project | review | assessment | lab
    ref: str
    title: str
    reason: str


def next_recommendation(cur: Curriculum, db: Database, today: Optional[dt.date] = None) -> Recommendation:
    progress = db.all_progress()
    due = db.due_reviews(today)
    if len(due) >= 3:
        return Recommendation("review", "mistakes", f"Review {len(due)} concepts",
                              "Spaced review of earlier mistakes keeps them from coming back.")
    for l in cur.lessons:
        if progress.get(l.id, {}).get("status") == "in_progress":
            return Recommendation("project" if l.kind != "lesson" else "lesson", l.id, l.title,
                                  "Pick up where you left off.")
    # weakest completed lesson below mastery gets a revisit suggestion after its level is done
    for l in cur.lessons:
        st = lesson_status(cur, db, l, progress)
        if st == "available":
            reason = "Next step on your learning path."
            if l.kind == "project":
                reason = "Apply this level's lessons to a realistic case."
            if l.kind == "lab_project":
                reason = "Build the full 12-month model in the Modeling Lab."
            return Recommendation("project" if l.kind != "lesson" else "lesson", l.id, l.title, reason)
    if final_assessment_unlocked(cur, db) and not any(a["passed"] for a in db.assessments("final")):
        return Recommendation("assessment", "final", "Final practical assessment",
                              "You have completed the V1 learning path. Demonstrate your skills.")
    weak = [l for l in cur.lessons if l.kind == "lesson" and lesson_status(cur, db, l, progress) == "completed"]
    if weak:
        return Recommendation("lesson", weak[0].id, weak[0].title,
                              "Raise this lesson to mastery (80%+) to strengthen the skill.")
    if due:
        return Recommendation("review", "mistakes", f"Review {len(due)} concepts", "Keep earlier mistakes fixed.")
    return Recommendation("lab", "lab", "Experiment in the Modeling Lab",
                          "Try new scenarios on your hotel model. More levels arrive in future releases.")


# --------------------------------------------------------------- XP/badges


def award(db: Database, rule: str, ref: str) -> int:
    amount = XP_RULES[rule]
    return amount if db.award_xp(amount, rule, ref) else 0


def check_badges(cur: Curriculum, db: Database) -> list[str]:
    """Award any newly earned badges. Returns their ids."""
    new = []
    progress = db.all_progress()

    def done(ids):
        return all(progress.get(i, {}).get("status") == "completed" for i in ids)

    conditions = {
        "first_link": any(r["step_type"] == "build" and r["correct"] for l in progress for r in db.step_results(l)),
        "foundations": done([l.id for l in cur.level(1).lessons if l.kind == "lesson"]),
        "spreadsheet_pro": done([l.id for l in cur.level(2).lessons if l.kind == "lesson"]),
        "revenue_analyst": done([l.id for l in cur.level(3).lessons if l.kind == "lesson"]),
        "cash_detective": done(["P1"]),
        "model_builder": any(p["validated"] for p in db.projects()),
        "certified_v1": any(a["passed"] and a["details"].get("model_validated") for a in db.assessments("final")),
        "mistake_hunter": sum(1 for m in db.mistakes(include_resolved=True) if m["resolved"]) >= 5,
        "personal_best": _improved(db.assessments("final")),
        "mastery_10": sum(1 for p in progress.values() if (p.get("best_score") or 0) >= MASTERY_THRESHOLD) >= 10,
    }
    for bid, ok in conditions.items():
        if ok and db.award_badge(bid):
            new.append(bid)
    return new


def _improved(results: list[dict]) -> bool:
    best = None
    for r in results:
        if best is not None and r["score"] > best + 1e-9:
            return True
        best = r["score"] if best is None else max(best, r["score"])
    return False


def skill_level(xp: int) -> tuple[int, int, int]:
    """Return (level, xp into level, xp needed for next level). Levels every 250 XP."""
    return xp // 250 + 1, xp % 250, 250


# -------------------------------------------------------------- competency

MODEL_SKILLS = {"hotel_model"}


@dataclass
class SkillStatus:
    skill_id: str
    name: str
    area: str
    status: str      # demonstrated | developing | needs_practice | not_assessed
    score: Optional[float]
    evidence: int
    note: str = ""


def competencies(cur: Curriculum, db: Database) -> list[SkillStatus]:
    out = []
    for sid, sk in cur.skills.items():
        ev = db.evidence(sid)[-12:]  # recent evidence matters most
        if not ev:
            out.append(SkillStatus(sid, sk["name"], sk["area"], "not_assessed", None, 0))
            continue
        w = sum(e["weight"] for e in ev)
        score = sum(e["score"] * e["weight"] for e in ev) / w if w else 0.0
        has_model = any(e["source"].startswith("model:") for e in ev)
        note = ""
        if score >= MASTERY_THRESHOLD and w >= 3:
            status = "demonstrated"
            if sid in MODEL_SKILLS and not has_model:
                status, note = "developing", "Needs a validated model, not only quiz answers."
        elif score >= 0.5:
            status = "developing"
        else:
            status = "needs_practice"
        if w < 3 and status != "needs_practice":
            note = note or "Limited evidence so far."
            status = "developing"
        out.append(SkillStatus(sid, sk["name"], sk["area"], status, score, len(ev), note))
    return out


def competency_report(cur: Curriculum, db: Database) -> dict:
    comps = competencies(cur, db)
    finals = db.assessments("final")
    progress = db.all_progress()
    projects = db.projects()
    outstanding = [l.title for l in cur.lessons if progress.get(l.id, {}).get("status") != "completed"]
    rec = next_recommendation(cur, db)
    return {
        "learner": db.get_setting("learner_name") or "Learner",
        "generated": dt.datetime.now().strftime("%d %B %Y %H:%M"),
        "demonstrated": [c for c in comps if c.status == "demonstrated"],
        "developing": [c for c in comps if c.status == "developing"],
        "needs_practice": [c for c in comps if c.status == "needs_practice"],
        "not_assessed": [c for c in comps if c.status == "not_assessed"],
        "assessments": finals,
        "projects": projects,
        "model_validated": any(p["validated"] for p in projects),
        "completed_lessons": [l.title for l in cur.lessons if progress.get(l.id, {}).get("status") == "completed"],
        "outstanding": outstanding,
        "next_step": rec,
        "xp": db.total_xp(),
        "criteria": [
            "Demonstrated: weighted score of at least 80% across recent evidence with enough evidence (weight 3+).",
            "Model-building skills also require a model that passes FinPilot's independent validation.",
            "Developing: 50-79%, or limited evidence. Needs practice: below 50%.",
            "Evidence weights: lesson items 1, final assessment items 2, validated models 3.",
        ],
    }
