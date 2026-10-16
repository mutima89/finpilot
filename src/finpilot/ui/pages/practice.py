"""Formula Practice: randomised drills with immediate feedback."""
from __future__ import annotations

import datetime as dt
import random


from ...curriculum import drills
from ..context import AppContext
from ..questions import FormulaQuestion
from ..widgets import Card, ChipGroup, Page, button, clear_layout, hbox, label

SKILL_FOR_TOPIC = {"kpis": ["hotel_kpis"], "refs": ["references"], "logic": ["logic_functions", "auditing"],
                   "lookups": ["lookups"], "growth": ["growth_ratios", "variance"], "costs": ["cost_behaviour",
                                                                                               "profit_measures"]}


class PracticePage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Formula practice", "Short drills with fresh numbers each time. Formulas are checked with "
                         "changed inputs, so they must be properly linked.", "Practise")
        self.ctx = ctx
        self.session = {"tried": 0, "first_try": 0}
        self.topic = ChipGroup([("all", "All topics")] + list(drills.TOPICS.items()), "all")
        self.topic.changed.connect(lambda _: self.new())
        self.add(self.topic)
        self.stats = label("", "Muted")
        self.add(hbox(self.stats, "stretch", button("New exercise", "Primary", self.new)))
        self.card = Card("Card", 22, 10)
        self.add(self.card)
        self.add("stretch")
        self.new()

    def new(self):
        keys = [k for k, (t, _, _) in drills.DRILLS.items() if self.topic.value in ("all", t)]
        key = random.choice(keys)
        q = drills.generate(key, random.randrange(1_000_000))
        clear_layout(self.card.lay)
        self.card.add(label(drills.TOPICS[q["topic"]].upper(), "Eyebrow"), label(q["title"], "H2"))
        w = FormulaQuestion(q, self.ctx.mode)
        self.card.add(w)
        w.finished.connect(lambda fb, w=w, q=q: self._done(fb, w, q))
        w.attempted.connect(lambda fb, w=w, q=q: self._attempt(fb, w, q))
        self._update_stats()

    def _attempt(self, fb, w, q):
        if w.attempts == 1 and not fb.correct:
            ref = f"drill/{q['drill']}"
            self.ctx.record_mistake(ref=ref, lesson_id="practice", skill=SKILL_FOR_TOPIC[q["topic"]][0],
                                    question=f"[{q['title']}] " + q["question"], answer=w.answer_text(),
                                    expected=q["reference"], fb=fb)

    def _done(self, fb, w, q):
        self.session["tried"] += 1
        first = fb.correct and w.attempts == 1 and not w.revealed
        if first:
            self.session["first_try"] += 1
        from ...curriculum import progression as prog
        score = prog.item_score(w.attempts, fb.correct, w.revealed)
        self.ctx.db.add_evidence(SKILL_FOR_TOPIC[q["topic"]], f"drill:{q['drill']}", score, 0.5)
        if fb.correct and not w.revealed:
            # at most five rewarded drills per topic per day: practice is for learning, not XP farming
            today = dt.date.today().isoformat()
            for n in range(5):
                if self.ctx.db.award_xp(prog.XP_RULES["item_correct"], "drill", f"{today}/{q['topic']}/{n}"):
                    if self.ctx.gamification:
                        self.ctx.notify(f"+{prog.XP_RULES['item_correct']} XP")
                    break
        best = self.ctx.setting("practice_best_session") or 0
        if self.session["first_try"] > best:
            self.ctx.set_setting("practice_best_session", self.session["first_try"])
        self._update_stats()
        self.card.add(hbox(button("Next exercise →", "Primary", self.new), stretch_end=True))
        self.ctx.after_progress()

    def _update_stats(self):
        best = self.ctx.setting("practice_best_session") or 0
        t, f = self.session["tried"], self.session["first_try"]
        self.stats.setText(f"This session: {f} of {t} right first time · personal best in a session: {best}")
