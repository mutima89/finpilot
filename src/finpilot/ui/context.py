"""Application context shared by all screens."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from ..curriculum import Curriculum, load
from ..curriculum import progression as prog
from ..curriculum.grading import Feedback
from ..data.db import Database
from ..data.projects import Project

log = logging.getLogger(__name__)


class Signals(QObject):
    progress_changed = Signal()
    theme_changed = Signal(str)
    project_changed = Signal()
    notify = Signal(str)


class AppContext:
    def __init__(self, db: Optional[Database] = None, curriculum: Optional[Curriculum] = None):
        self.db = db or Database()
        self.cur = curriculum or load()
        self.signals = Signals()
        self.navigate: Callable[..., None] = lambda *a, **k: None
        self.project: Optional[Project] = None
        self.project_dirty = False

    # ------------------------------------------------------------ settings
    def setting(self, key: str):
        return self.db.get_setting(key)

    def set_setting(self, key: str, value) -> None:
        self.db.set_setting(key, value)

    @property
    def gamification(self) -> bool:
        return bool(self.setting("gamification"))

    @property
    def mode(self) -> str:
        return self.setting("practice_mode") or "guided"

    # ------------------------------------------------------------ recording
    def notify(self, text: str) -> None:
        self.signals.notify.emit(text)

    def award(self, rule: str, ref: str) -> int:
        xp = prog.award(self.db, rule, ref)
        if xp and self.gamification:
            self.notify(f"+{xp} XP")
        return xp

    def record_item(self, *, lesson_id: str, item_id: str, step_type: str, fb: Feedback, attempts: int,
                    revealed: bool, skills: list[str], question: str, answer: str, expected: str,
                    weight: float = 1.0) -> float:
        """Record a graded item once it is finished (correct, or revealed)."""
        score = prog.item_score(attempts, fb.correct, revealed)
        self.db.record_step(lesson_id, item_id, step_type, fb.correct and not revealed, score, attempts)
        if skills:
            self.db.add_evidence(skills, f"{step_type}:{lesson_id}/{item_id}", score, weight)
        if fb.correct and not revealed:
            self.award("item_first_try" if attempts == 1 else "item_correct", f"{lesson_id}/{item_id}")
        return score

    def record_mistake(self, *, ref: str, lesson_id: str, skill: str, question: str, answer: str,
                       expected: str, fb: Feedback) -> None:
        try:
            self.db.add_mistake(ref, lesson_id, skill, _strip(question), answer, expected,
                                f"{fb.title}: {_strip(fb.message)}")
        except Exception:  # never let the notebook break a lesson
            log.exception("Could not record mistake")

    def after_progress(self) -> None:
        new = prog.check_badges(self.cur, self.db)
        if new and self.gamification:
            names = ", ".join(prog.BADGES[b][0] for b in new)
            self.notify(f"Achievement unlocked: {names}")
        self.signals.progress_changed.emit()


def _strip(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html or "").replace("&nbsp;", " ").strip()
