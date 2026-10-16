"""Challenge Arena: the V1 final practical assessment."""
from __future__ import annotations

import html

from PySide6.QtWidgets import QMessageBox, QVBoxLayout

from ...curriculum import progression as prog
from ..context import AppContext
from ..questions import QuestionWidget, make_question
from ..widgets import Card, Feedback, Page, button, clear_layout, hbox, label


class ChallengePage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Challenge arena", "Realistic tasks with limited guidance. Hints unlock after two "
                         "attempts and worked solutions after three.", "Assess")
        self.ctx = ctx
        self.widgets: list[tuple[dict, QuestionWidget]] = []
        self.content = QVBoxLayout()
        self.content.setSpacing(14)
        self.add(self.content)
        self.add("stretch")
        ctx.signals.progress_changed.connect(lambda: None if self.widgets else self.refresh())
        self.refresh()

    def refresh(self):
        if self.widgets:
            return
        clear_layout(self.content)
        a = self.ctx.cur.assessment
        intro = Card("Card", 22, 10)
        intro.add(label(a["title"], "H2"), label(a["intro"], "Body"))
        sections = []
        for it in a["items"]:
            if it["section"] not in sections:
                sections.append(it["section"])
        intro.add(label("<b>Sections:</b> " + ", ".join(html.escape(s) for s in sections), "Body", rich=True))
        intro.add(label(f"<b>Pass criteria:</b> at least {a['pass_overall']:.0%} overall and at least "
                        f"{a['pass_section']:.0%} in every section. First-try answers score 100%, second tries 60%, "
                        "later tries 30%; revealed solutions score zero. The written recommendation is scored by "
                        "its rubric. The V1 competency badge also requires a validated hotel model.", "Body",
                        rich=True))
        unlocked = prog.final_assessment_unlocked(self.ctx.cur, self.ctx.db)
        validated = any(p["validated"] for p in self.ctx.db.projects())
        intro.add(label(("✓ Your 12-month hotel model is validated." if validated else
                         "Your 12-month hotel model is not validated yet. You can take the assessment, but the "
                         "competency report will show modeling as outstanding."), "Muted"))
        start = button("Start assessment", "Primary", self.start)
        start.setEnabled(unlocked)
        intro.add(hbox(start, label("" if unlocked else "Complete all Level 1-3 lessons to unlock (or enable "
                                    "'Unlock all' in Settings).", "Muted", wrap=False), stretch_end=True))
        self.content.addWidget(intro)
        hist = self.ctx.db.assessments("final")
        if hist:
            h = Card()
            h.add(label("Previous attempts", "H3"))
            for i, r in enumerate(hist, 1):
                h.add(label(f"Attempt {i} · {r['ts'][:16].replace('T', ' ')} · {r['score']:.0%} · "
                            f"{'passed' if r['passed'] else 'not yet passed'}", "Body"))
            self.content.addWidget(h)

    def start(self):
        clear_layout(self.content)
        self.widgets = []
        current = None
        card = None
        for n, q in enumerate(self.ctx.cur.assessment["items"], 1):
            if q["section"] != current:
                current = q["section"]
                card = Card("Card", 20, 12)
                card.add(label(current.upper(), "Eyebrow"))
                self.content.addWidget(card)
            w = make_question({**q, "question": f"{n}. {q['question']}"}, "challenge")
            card.add(w)
            self.widgets.append((q, w))
        self.submit_fb = Feedback()
        self.content.addWidget(self.submit_fb)
        self.content.addLayout(hbox(button("Submit assessment", "Primary", self.submit),
                                    button("Abandon", "Ghost", self.abandon), stretch_end=True))

    def abandon(self):
        if QMessageBox.question(self, "Abandon assessment?", "Leave without recording a result?") == QMessageBox.Yes:
            self.widgets = []
            self.refresh()

    def _item_score(self, q, w) -> float:
        if not w.done:
            return 0.0
        if w.revealed:
            return 0.0
        fb = w.final_feedback
        if q["kind"] == "written":
            return fb.score
        return prog.item_score(w.attempts, fb.correct)

    def submit(self):
        unanswered = sum(1 for _, w in self.widgets if not w.done and w.attempts == 0)
        if unanswered and QMessageBox.question(
                self, "Submit now?", f"{unanswered} item(s) have not been answered and will score zero. "
                "Submit anyway?") != QMessageBox.Yes:
            return
        a = self.ctx.cur.assessment
        sections: dict[str, dict] = {}
        items = {}
        for q, w in self.widgets:
            s = self._item_score(q, w)
            # a written answer checked but not finished still earns its rubric share
            if q["kind"] == "written" and not w.done and w.attempts:
                s = getattr(w, "rubric_result", None) and sum(ok for _, ok in w.rubric_result) / len(w.rubric_result) or 0
            items[q["id"]] = s
            sec = sections.setdefault(q["section"], {"total": 0.0, "items": 0})
            sec["total"] += s
            sec["items"] += 1
            self.ctx.db.add_evidence(q.get("skills", []), f"final:{q['id']}", s, 2.0)
            if not w.done or s < 1:
                if w.attempts:
                    self.ctx.record_mistake(ref=f"final/{q['id']}", lesson_id="final",
                                            skill=(q.get("skills") or [""])[0], question=q["question"],
                                            answer=w.answer_text(), expected=w.expected_text(),
                                            fb=getattr(w, "final_feedback", None) or _fb())
        for sec in sections.values():
            sec["score"] = sec["total"] / sec["items"]
        overall = sum(items.values()) / len(items)
        passed = overall >= a["pass_overall"] and all(s["score"] >= a["pass_section"] for s in sections.values())
        validated = any(p["validated"] for p in self.ctx.db.projects())
        prev = self.ctx.db.assessments("final")
        self.ctx.db.record_assessment("final", "V1", overall, passed,
                                      {"sections": {k: {"score": v["score"], "items": v["items"]}
                                                    for k, v in sections.items()},
                                       "items": items, "model_validated": validated})
        if passed:
            self.ctx.award("final_passed", "V1")
        self.ctx.after_progress()
        self.widgets = []
        self._show_result(overall, passed, sections, validated, prev)

    def _show_result(self, overall, passed, sections, validated, prev):
        clear_layout(self.content)
        c = Card("Card", 22, 10)
        c.add(label("ASSESSMENT RESULT", "Eyebrow"),
              label(f"{overall:.0%} — {'Passed' if passed else 'Not yet passed'}", "H1"))
        if prev:
            best = max(p["score"] for p in prev)
            c.add(label(f"Previous best: {best:.0%}" + ("  ·  New personal best!" if overall > best else ""),
                        "Muted"))
        for name, s in sections.items():
            flag = "✓" if s["score"] >= self.ctx.cur.assessment["pass_section"] else "✗"
            c.add(label(f"{flag} {html.escape(name)}: {s['score']:.0%} ({s['items']} items)", "Body"))
        c.add(label("Modeling competence: " + ("validated 12-month model on record." if validated else
                                               "not demonstrated yet. Build and validate the hotel model in the "
                                               "Modeling Lab (Level 3 project)."), "Body"))
        c.add(label("Missed items were added to your mistakes notebook for spaced review.", "Muted"))
        c.add(hbox(button("Competency report", "Primary", lambda: self.ctx.navigate("progress")),
                   button("Retry assessment", "", self.start),
                   button("Mistakes notebook", "", lambda: self.ctx.navigate("mistakes")), stretch_end=True))
        self.content.addWidget(c)


def _fb():
    from ...curriculum.grading import Feedback as FB
    return FB(False, "Not answered", "This item was not completed.", "unanswered")
