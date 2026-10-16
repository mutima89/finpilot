"""Mistakes notebook with spaced repetition review."""
from __future__ import annotations

import datetime as dt
import html
import random

from PySide6.QtWidgets import QVBoxLayout

from ...curriculum import drills, item_refs
from ..context import AppContext
from ..questions import make_question
from ..widgets import Card, Page, button, clear_layout, hbox, label


class MistakesPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Mistakes notebook", "Every first-attempt mistake is saved with its explanation and "
                         "scheduled for review after 1, 3, 7, 14 and 30 days. Three correct reviews in a row "
                         "resolve it.", "Review")
        self.ctx = ctx
        self.content = QVBoxLayout()
        self.content.setSpacing(12)
        self.add(self.content)
        self.add("stretch")
        self.reviewing = False
        ctx.signals.progress_changed.connect(lambda: None if self.reviewing else self.refresh())
        self.refresh()

    def refresh(self):
        self.reviewing = False
        clear_layout(self.content)
        db = self.ctx.db
        due = db.due_reviews()
        all_open = db.mistakes()
        resolved = [m for m in db.mistakes(include_resolved=True) if m["resolved"]]
        head = Card()
        head.add(label(f"{len(due)} due today · {len(all_open)} open · {len(resolved)} resolved", "H3"))
        b = button("Review due items", "Primary", self.start_review)
        b.setEnabled(bool(due))
        head.add(hbox(b, label("" if due else "Nothing is due right now. Open items come back on their review date.",
                               "Muted", wrap=False), stretch_end=True))
        self.content.addWidget(head)
        today = dt.date.today().isoformat()
        for m in all_open:
            c = Card("Card", 16, 4)
            when = "due now" if m["next_review"] <= today else f"next review {m['next_review']}"
            c.add(label(f"{html.escape(m['lesson_id'] or '')} · {when} · reviewed {m['reviews']}×", "Eyebrow"))
            c.add(label(html.escape(m["question"]), "Body", rich=True))
            c.add(label(f"<b>Your answer:</b> {html.escape(m['your_answer'] or '—')}  &nbsp; "
                        f"<b>Expected:</b> {html.escape(m['expected'] or '—')}", "Muted", rich=True))
            c.add(label(html.escape(m["explanation"] or ""), "Muted", rich=True))
            self.content.addWidget(c)
        if not all_open:
            self.content.addWidget(label("Your notebook is empty. Mistakes are part of learning: when you miss "
                                         "something, it is recorded here with the explanation.", "Muted"))

    def _question_for(self, m):
        ref = m["ref"]
        if ref.startswith("drill/"):
            key = ref.split("/", 1)[1]
            if key in drills.DRILLS:
                return drills.generate(key, random.randrange(1_000_000))
            return None
        if ref.startswith("P3/"):
            return None
        reg = item_refs(self.ctx.cur)
        if ref in reg:
            return reg[ref][1]
        return None

    def start_review(self):
        due = self.ctx.db.due_reviews()
        if not due:
            return
        self.reviewing = True
        clear_layout(self.content)
        for m in due[:10]:
            q = self._question_for(m)
            c = Card("Card", 18, 8)
            c.add(label(f"REVIEW · {html.escape(m['lesson_id'] or '')}", "Eyebrow"))
            if q is None:
                c.add(label(html.escape(m["question"]), "Body", rich=True),
                      label("This was a model-building task. Revisit it in the Modeling Lab, then mark how it went.",
                            "Muted"))
                c.add(hbox(button("I can do it now", "Primary", lambda _=False, mid=m["id"], c=c: self._mark(mid, True, c)),
                           button("Still unsure", "", lambda _=False, mid=m["id"], c=c: self._mark(mid, False, c)),
                           stretch_end=True))
            else:
                w = make_question(q, self.ctx.mode)
                w.finished.connect(lambda fb, w=w, mid=m["id"]: self._reviewed(mid, w, fb))
                c.add(w)
            self.content.addWidget(c)
        self.content.addLayout(hbox(button("Back to notebook", "", self.refresh), stretch_end=True))

    def _reviewed(self, mid, w, fb):
        ok = fb.correct and w.attempts == 1 and not w.revealed
        row = self.ctx.db.review_mistake(mid, ok)
        if ok:
            self.ctx.award("review_correct", f"review/{mid}/{row['reviews']}")
        msg = ("Resolved: three correct reviews in a row." if row["resolved"] else
               f"Next review on {row['next_review']}.")
        w.feedback.extra.setText(msg)
        w.feedback.extra.show()
        self.ctx.after_progress()

    def _mark(self, mid, ok, card):
        row = self.ctx.db.review_mistake(mid, ok)
        card.add(label("Resolved." if row["resolved"] else f"Next review on {row['next_review']}.", "Muted"))
        self.ctx.after_progress()
