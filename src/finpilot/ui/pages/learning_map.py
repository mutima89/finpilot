"""Learning map: ten levels, lessons, status and prerequisites."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout

from ...curriculum import progression as prog
from ..context import AppContext
from ..theme import palette
from ..widgets import Card, Page, button, clear_layout, hbox, label, status_dot

STATUS_TEXT = {"mastered": "Mastered", "completed": "Completed", "in_progress": "In progress",
               "available": "Ready", "locked": "Locked"}


class LearningMapPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Learning map", "Ten levels from financial foundations to professional capstones. "
                         "You can see where you are, what you have mastered and what comes next.", "Your path")
        self.ctx = ctx
        self.content = QVBoxLayout()
        self.content.setSpacing(14)
        self.add(self.content)
        self.add("stretch")
        ctx.signals.progress_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        clear_layout(self.content)
        cur, db = self.ctx.cur, self.ctx.db
        progress = db.all_progress()
        rec = prog.next_recommendation(cur, db)
        p = palette()
        for lv in cur.levels:
            card = Card("Card", 18, 8)
            unlocked = prog.level_unlocked(cur, db, lv.number)
            tag = {"available": "Course available", "preview": "Preview in V1", "planned": "Planned"}[lv.status]
            done = sum(1 for l in lv.lessons if progress.get(l.id, {}).get("status") == "completed")
            head = QHBoxLayout()
            head.addWidget(label(f"LEVEL {lv.number}", "Eyebrow", wrap=False))
            head.addWidget(label(lv.title, "H2"), 1)
            head.addWidget(label(f"{tag}" + (f" · {done}/{len(lv.lessons)} complete" if lv.lessons else ""),
                                 "Muted", wrap=False))
            card.add(head, label(lv.summary, "Muted"))
            if lv.lessons:
                g = QGridLayout()
                g.setSpacing(8)
                buttons = []
                for l in lv.lessons:
                    st = prog.lesson_status(cur, db, l, progress)
                    pr = progress.get(l.id, {})
                    score = f" · best {pr['best_score']:.0%}" if pr.get("best_score") is not None else ""
                    kind = {"project": "Project", "lab_project": "Lab project"}.get(l.kind, "Lesson")
                    b = QPushButton()
                    b.setObjectName("Choice")
                    b.setCursor(Qt.PointingHandCursor if st != "locked" else Qt.ForbiddenCursor)
                    star = "  ← next" if rec.ref == l.id else ""
                    b.setText(f"{'●' if st != 'locked' else '🔒'}  {l.title}{star}\n"
                              f"     {kind} · {l.minutes} min · {STATUS_TEXT[st]}{score}".replace("&", "&&"))
                    b.setStyleSheet(f"QPushButton {{ color: {status_dot(st) if st != 'available' else p.text}; "
                                    f"text-align:left; padding:10px 12px; }}")
                    if st == "locked":
                        b.setToolTip("Requires: " + ", ".join(prog.missing_prereqs(cur, db, l)))
                    else:
                        b.setToolTip(l.summary)
                    b.clicked.connect(lambda _=False, lid=l.id, k=l.kind: self.ctx.navigate(
                        "project" if k != "lesson" else "lesson", lid))
                    buttons.append(b)
                cols = self._columns(max(b.minimumSizeHint().width() for b in buttons))
                for i, b in enumerate(buttons):
                    g.addWidget(b, i // cols, i % cols)
                card.add(g)
                if lv.number == 3:
                    fa = prog.final_assessment_unlocked(cur, db)
                    card.add(hbox(button("Final practical assessment →", "Primary" if fa else "",
                                         lambda: self.ctx.navigate("assessment", "final")),
                                  label("Unlocks after all Level 1-3 lessons." if not fa else
                                        "Ready when you are.", "Muted"), stretch_end=True))
            else:
                topics = " · ".join(html.escape(t) for t in lv.topics)
                card.add(label(f"Topics: {topics}", "Muted", rich=True))
                if lv.number == 4:
                    card.add(hbox(button("Open group displacement simulator →", "",
                                         lambda: self.ctx.navigate("simulation")), stretch_end=True))
            if not unlocked and lv.status != "planned":
                card.add(label(f"Complete Level {lv.number - 1} to unlock (or enable 'Unlock all' in Settings).",
                               "Muted"))
            self.content.addWidget(card)

    def _columns(self, button_width: int) -> int:
        """As many lesson columns (1-3) as fit the page; font metrics differ between systems."""
        room = self.width() - 140  # page and card margins
        for cols in (3, 2):
            if cols * button_width + (cols - 1) * 8 <= room and (cols < 3 or self.width() >= 1150):
                return cols
        return 1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_last_width", None) is None or abs(self.width() - self._last_width) >= 40:
            self._last_width = self.width()
            self.refresh()
