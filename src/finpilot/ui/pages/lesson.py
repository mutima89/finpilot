"""Lesson workspace: the ten-step Understand → Progress sequence."""
from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDoubleSpinBox, QFrame, QGridLayout, QHeaderView, QMessageBox, QSlider, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...core.format import format_value
from ...core.formula import CellError, evaluate
from ...curriculum import STEP_TITLES, Lesson
from ...curriculum import progression as prog
from ..context import AppContext
from ..questions import ChoiceQuestion, QuestionWidget, make_question
from ..widgets import (Card, ChipGroup, Feedback, Page, StepTrack, button, clear_layout, hbox, label)

MODES = [("guided", "Guided"), ("practice", "Practice"), ("challenge", "Challenge")]
MODE_HELP = {"guided": "Full support: hints and the worked solution unlock after your first attempt.",
             "practice": "Hints unlock after one attempt, the worked solution after two.",
             "challenge": "Limited guidance: hints after two attempts, the solution after three."}


class TestPanel(QWidget):
    """Interactive 'Test' step: inputs drive live outputs through the formula engine."""

    def __init__(self, step: dict):
        super().__init__()
        self.step = step
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        self.inputs = {}
        for r, spec in enumerate(step["inputs"]):
            name = spec["name"]
            lo, hi, st = float(spec["min"]), float(spec["max"]), float(spec["step"])
            n = max(1, round((hi - lo) / st))
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, n)
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(st)
            decimals = 0 if float(st).is_integer() else min(4, len(f"{st:.6f}".rstrip('0').split('.')[1]))
            sb.setDecimals(decimals)
            sb.setValue(float(spec["value"]))
            sl.setValue(round((float(spec["value"]) - lo) / st))
            sb.setMinimumWidth(120)
            shown = label(format_value(spec["value"], spec.get("fmt", "general")), "Muted", wrap=False)
            sl.valueChanged.connect(lambda v, sb=sb, lo=lo, st=st: sb.setValue(lo + v * st))
            sb.valueChanged.connect(lambda v, sl=sl, lo=lo, st=st: (sl.blockSignals(True),
                                                                    sl.setValue(round((v - lo) / st)),
                                                                    sl.blockSignals(False), self.update_outputs()))
            g.addWidget(label(spec["label"], wrap=False), r, 0)
            g.addWidget(sl, r, 1)
            g.addWidget(sb, r, 2)
            g.addWidget(shown, r, 3)
            g.setColumnStretch(1, 1)
            self.inputs[name] = (sb, spec, shown)
        lay.addLayout(g)
        out_card = Card("Card", 14, 6)
        self.outputs = []
        og = QGridLayout()
        for r, o in enumerate(step["outputs"]):
            v = label("", "H2", wrap=False)
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            og.addWidget(label(o["label"], wrap=True), r, 0)
            og.addWidget(v, r, 1)
            self.outputs.append((o, v))
        og.setColumnStretch(0, 1)
        out_card.add(og)
        lay.addWidget(out_card)
        self.update_outputs()

    def values(self) -> dict:
        return {n: sb.value() for n, (sb, _, _) in self.inputs.items()}

    def update_outputs(self):
        vals = self.values()
        for n, (sb, spec, shown) in self.inputs.items():
            shown.setText(format_value(sb.value(), spec.get("fmt", "general")))
        for o, lab in self.outputs:
            v = evaluate(o["formula"], names=vals)
            if isinstance(v, CellError):
                lab.setText(v.code)
                lab.setToolTip(v.explanation)
            else:
                lab.setText(format_value(v, o.get("fmt", "general")))
                lab.setToolTip("")


class LessonPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Lesson", "", "Lesson workspace", scroll=True)
        self.ctx = ctx
        self.lesson: Optional[Lesson] = None
        self.steps: list[dict] = []
        self.index = 0
        self.reached = 0
        self.item_scores: dict[str, float] = {}
        self.pending: set[str] = set()
        self.prediction: Optional[int] = None
        top = QFrame()
        top_l = hbox()
        top.setLayout(top_l)
        self.mode_chips = ChipGroup(MODES, ctx.mode)
        self.mode_chips.changed.connect(self._mode_changed)
        self.mode_help = label(MODE_HELP[ctx.mode], "Muted")
        self.bookmark_btn = button("☆ Bookmark", "Ghost", self._toggle_bookmark)
        self.restart_btn = button("Restart lesson", "Ghost", self._restart)
        top_l.addWidget(label("Mode:", "Muted", wrap=False))
        top_l.addWidget(self.mode_chips)
        top_l.addWidget(self.mode_help, 1)
        top_l.addWidget(self.bookmark_btn)
        top_l.addWidget(self.restart_btn)
        self.add(top)
        self.track = StepTrack([STEP_TITLES[s] for s in
                                ["understand", "see", "build", "predict", "test", "explain", "apply", "recall",
                                 "review", "progress"]])
        self.track.clicked.connect(self.go)
        self.add(self.track)
        self.card = Card("Card", 24, 12)
        self.card.setMinimumHeight(360)
        self.add(self.card)
        self.back_btn = button("← Back", "", lambda: self.go(self.index - 1))
        self.next_btn = button("Continue →", "Primary", self._next)
        self.status = label("", "Muted", wrap=False)
        self.add(hbox(self.back_btn, "stretch", self.status, self.next_btn))
        self.add("stretch")

    # ------------------------------------------------------------ loading
    def open(self, lesson_id: str):
        lesson = self.ctx.cur.lesson(lesson_id)
        if lesson is None:
            return
        st = prog.lesson_status(self.ctx.cur, self.ctx.db, lesson)
        if st == "locked":
            missing = prog.missing_prereqs(self.ctx.cur, self.ctx.db, lesson)
            QMessageBox.information(self, "Lesson locked",
                                    "Complete these first: " + ", ".join(missing) +
                                    ".\n\nYou can unlock everything in Settings if you prefer to explore.")
            return False
        self.lesson = lesson
        self.steps = list(lesson.steps)
        if lesson.kind == "lesson" or lesson.kind == "project":
            self.steps.append({"type": "progress"})
        p = self.ctx.db.start_lesson(lesson.id, self.ctx.mode)
        self.index = min(p["step_index"], len(self.steps) - 1) if p["status"] != "completed" else 0
        self.reached = self.index
        self.item_scores = {}
        for r in self.ctx.db.step_results(lesson.id):
            self.item_scores[r["item_id"]] = r["score"]
        self.prediction = None
        self.eyebrow.setText(f"LEVEL {lesson.level} · {'PROJECT' if lesson.kind != 'lesson' else 'LESSON'} "
                             f"· ABOUT {lesson.minutes} MIN")
        self.title.setText(lesson.title)
        self.subtitle.setText(lesson.summary)
        self.subtitle.setVisible(True)
        self.eyebrow.setVisible(True)
        names = ["Task" if lesson.kind != "lesson" and s["type"] in ("apply", "written")
                 else STEP_TITLES.get(s["type"], s["type"].title()) for s in self.steps]
        self.track.names = names
        self._update_bookmark()
        self.go(self.index)
        return True

    def _mode_changed(self, mode: str):
        self.ctx.set_setting("practice_mode", mode)
        self.mode_help.setText(MODE_HELP[mode])
        if self.lesson:
            self.go(self.index)

    def _toggle_bookmark(self):
        if not self.lesson:
            return
        db = self.ctx.db
        if db.is_bookmarked("lesson", self.lesson.id):
            db.remove_bookmark("lesson", self.lesson.id)
        else:
            db.add_bookmark("lesson", self.lesson.id, self.lesson.title)
        self._update_bookmark()
        self.ctx.signals.progress_changed.emit()

    def _update_bookmark(self):
        on = self.lesson and self.ctx.db.is_bookmarked("lesson", self.lesson.id)
        self.bookmark_btn.setText("★ Bookmarked" if on else "☆ Bookmark")

    def _restart(self):
        if not self.lesson:
            return
        if QMessageBox.question(self, "Restart lesson?", "Start this lesson again from step 1? Your best score "
                                "is kept.") != QMessageBox.Yes:
            return
        self.ctx.db.reset_lesson(self.lesson.id)
        self.item_scores = {}
        self.index = self.reached = 0
        self.go(0)

    # ------------------------------------------------------------ steps
    def go(self, i: int):
        if not self.lesson or i < 0 or i >= len(self.steps):
            return
        self.index = i
        self.reached = max(self.reached, i)
        self.track.set(i, self.reached)
        self.ctx.db.save_step(self.lesson.id, i)
        clear_layout(self.card.lay)
        self.pending = set()
        step = self.steps[i]
        builder = getattr(self, f"_step_{step['type']}", None)
        self.card.add(label(f"STEP {i + 1} OF {len(self.steps)} · {STEP_TITLES.get(step['type'], step['type']).upper()}",
                            "Eyebrow"))
        if builder:
            builder(step, i)
        self.back_btn.setEnabled(i > 0)
        self.next_btn.setVisible(step["type"] != "progress")
        self._refresh_next()

    def _refresh_next(self):
        blocked = bool(self.pending)
        self.next_btn.setEnabled(not blocked)
        self.status.setText("Complete this step to continue." if blocked else "")
        last_content = self.index == len(self.steps) - 2
        self.next_btn.setText("Finish lesson →" if last_content else "Continue →")

    def _next(self):
        if self.index == len(self.steps) - 2:
            self._complete()
        self.go(self.index + 1)

    def _title(self, text: str):
        self.card.add(label(text, "H2"))

    def _step_understand(self, s, i):
        self._title(s.get("title", ""))
        self.card.add(label(s["body"], "Body", rich=True))
        if s.get("deeper"):
            deeper = label(s["deeper"], "Body", rich=True)
            box = Card("FeedbackInfo", 14, 6)
            box.add(deeper)
            box.hide()
            btn = button("Go deeper ▾", "Ghost")
            btn.clicked.connect(lambda: (box.setVisible(not box.isVisible()),
                                         btn.setText("Hide detail ▴" if box.isVisible() else "Go deeper ▾")))
            self.card.add(btn, box)
        self.card.add("stretch")

    def _step_see(self, s, i):
        self._title(s.get("title", "Worked example"))
        if s.get("body"):
            self.card.add(label(s["body"], "Body", rich=True))
        t = s.get("table")
        if t:
            tw = QTableWidget(len(t["rows"]), len(t["headers"]))
            tw.setHorizontalHeaderLabels(t["headers"])
            tw.verticalHeader().hide()
            tw.setEditTriggers(QTableWidget.NoEditTriggers)
            for r, row in enumerate(t["rows"]):
                for c, v in enumerate(row):
                    it = QTableWidgetItem(str(v))
                    if c > 0 and any(ch.isdigit() for ch in str(v)):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    tw.setItem(r, c, it)
            tw.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tw.setMinimumHeight(34 + 30 * len(t["rows"]))
            tw.setMaximumHeight(40 + 30 * len(t["rows"]))
            self.card.add(tw)
        if s.get("note"):
            self.card.add(label("💡 " + s["note"], "Muted", rich=True))
        self.card.add("stretch")

    def _question(self, q: dict, item_id: str, step_type: str, show_question=True) -> QuestionWidget:
        w = make_question(q, self.ctx.mode, show_question)
        lesson = self.lesson
        if item_id in self.item_scores:
            w.feedback.show_result(None, "Already answered",
                                   "You answered this earlier in this lesson. You can answer again for practice.")
        else:
            self.pending.add(item_id)
        first = {"wrong": False}

        def on_attempt(fb):
            if not fb.correct and not first["wrong"] and w.attempts == 1:
                first["wrong"] = True
                self.ctx.record_mistake(ref=f"{lesson.id}/{item_id}", lesson_id=lesson.id,
                                        skill=(lesson.skills or [""])[0],
                                        question=q.get("question") or q.get("prompt", ""),
                                        answer=w.answer_text(), expected=w.expected_text(), fb=fb)

        def on_finish(fb):
            if item_id not in self.item_scores or item_id in self.pending:
                score = self.ctx.record_item(lesson_id=lesson.id, item_id=item_id, step_type=step_type, fb=fb,
                                             attempts=w.attempts, revealed=w.revealed, skills=lesson.skills,
                                             question=q.get("question", ""), answer=w.answer_text(),
                                             expected=w.expected_text())
                self.item_scores[item_id] = score
            self.pending.discard(item_id)
            self._refresh_next()

        w.attempted.connect(on_attempt)
        w.finished.connect(on_finish)
        return w

    def _step_build(self, s, i):
        self._title(s.get("title", "Build"))
        self.card.add(self._question(s, "build", "build"))

    def _step_predict(self, s, i):
        self._title("Predict before you test")
        self.card.add(label(s["question"], "H3", rich=True))
        w = ChoiceQuestion({"question": "", "options": s["options"], "correct": s["correct"]}, "guided", False)
        w.check_btn.setText("Lock in my prediction")
        w.hint_btn.hide()
        w.solution_btn.hide()
        w.reset_btn.hide()
        self.pending.add("predict")

        def locked():
            sel = w.group.checkedId()
            if sel < 0:
                w.feedback.show_result(None, "Choose a prediction", "Pick the option you think is right.")
                return
            self.prediction = sel
            right = sel == s["correct"]
            w.feedback.show_result(right, "Prediction recorded",
                                   "Now test it in the next step." if not right else
                                   "Good reasoning. Now test it in the next step to see why.")
            w.check_btn.setEnabled(False)
            for b in w.group.buttons():
                b.setEnabled(False)
            self.ctx.db.add_evidence(self.lesson.skills, f"predict:{self.lesson.id}", 1.0 if right else 0.0, 0.5)
            self.pending.discard("predict")
            self._refresh_next()

        w.check_btn.clicked.disconnect()
        w.check_btn.clicked.connect(locked)
        self.card.add(w)
        self.card.add("stretch")

    def _step_test(self, s, i):
        self._title(s.get("title", "Test it"))
        self.card.add(label(s.get("prompt", ""), "Body", rich=True))
        self.card.add(TestPanel(s))
        if s.get("observe"):
            c = Card("Callout", 12, 4)
            c.add(label("<b>Try this:</b> " + html.escape(s["observe"]), "Body", rich=True))
            self.card.add(c)

    def _step_explain(self, s, i):
        self._title(s.get("title", "What happened and why"))
        pred = self._find("predict")
        if pred and self.prediction is not None:
            ok = self.prediction == pred["correct"]
            fb = Feedback()
            fb.show_result(ok, "Your prediction was right" if ok else "Your prediction differed",
                           html.escape(pred.get("reveal", "")))
            self.card.add(fb)
        elif pred:
            self.card.add(label("<b>Answer to the prediction:</b> " + html.escape(pred.get("reveal", "")),
                                "Body", rich=True))
        self.card.add(label(s["body"], "Body", rich=True))
        if s.get("misconception"):
            c = Card("Callout", 12, 4)
            c.add(label("<b>Common misconception</b>", "Body", rich=True),
                  label(s["misconception"], "Body", rich=True))
            self.card.add(c)
        self.card.add("stretch")

    def _find(self, t):
        for s in self.steps:
            if s["type"] == t:
                return s
        return None

    def _step_apply(self, s, i):
        self._title(s.get("title", "Apply it"))
        if "questions" in s:
            for k, q in enumerate(s["questions"]):
                self.card.add(self._question(q, f"apply{i}-{k}", "apply"))
        else:
            self.card.add(self._question(s, "apply", "apply"))

    def _step_recall(self, s, i):
        self._title("Recall")
        self.card.add(label("Answer from memory. These questions return later in your review queue if you "
                            "miss them.", "Muted"))
        for k, q in enumerate(s["questions"]):
            self.card.add(self._question(q, f"recall-{k}", "recall"))

    def _step_written(self, s, i):
        self._title(s.get("title", "Written recommendation"))
        w = self._question(s, f"written{i}", "written")
        self.card.add(w)

    def _step_review(self, s, i):
        self._title("Review")
        pts = "".join(f"<li style='margin-bottom:4px'>{html.escape(p)}</li>" for p in s.get("points", []))
        self.card.add(label(f"<ul>{pts}</ul>", "Body", rich=True))
        if s.get("formulas"):
            self.card.add(label("Key formulas", "H3"))
            for f in s["formulas"]:
                self.card.add(label(f, "Formula"))
        self.card.add("stretch")

    def _score(self) -> float:
        ids = [k for k in self.item_scores]
        return sum(self.item_scores.values()) / len(ids) if ids else 1.0

    def _complete(self):
        score = self._score()
        prev = self.ctx.db.lesson_progress(self.lesson.id)
        self.ctx.db.complete_lesson(self.lesson.id, score)
        self.ctx.award("lesson_complete", self.lesson.id)
        if score >= prog.MASTERY_THRESHOLD:
            self.ctx.award("lesson_mastered", self.lesson.id)
        self._prev_best = (prev or {}).get("best_score")
        self.ctx.after_progress()

    def _step_progress(self, s, i):
        score = self._score()
        mastered = score >= prog.MASTERY_THRESHOLD
        self._title("Lesson complete" if mastered else "Lesson finished")
        msg = (f"Your score: <b>{score:.0%}</b> (first-try answers count most; revealed solutions count zero). "
               + ("You have <b>mastered</b> this lesson." if mastered else
                  "Aim for 80% to master it: retry the lesson, or review your mistakes."))
        if getattr(self, "_prev_best", None) is not None and score > (self._prev_best or 0):
            msg += f" Personal best (previous {self._prev_best:.0%})."
        self.card.add(label(msg, "Body", rich=True))
        rec = prog.next_recommendation(self.ctx.cur, self.ctx.db)
        c = Card("FeedbackInfo", 14, 6)
        c.add(label("RECOMMENDED NEXT", "Eyebrow"), label(rec.title, "H3"), label(rec.reason, "Muted"))
        go = button("Start →", "Primary", lambda: self.ctx.navigate(rec.kind, rec.ref))
        c.add(hbox(go, stretch_end=True))
        self.card.add(c)
        self.card.add(hbox(button("Retry this lesson", "", self._retry),
                           button("Learning map", "", lambda: self.ctx.navigate("map")),
                           button("Mistakes notebook", "", lambda: self.ctx.navigate("mistakes")),
                           stretch_end=True))
        self.card.add("stretch")

    def _retry(self):
        self.ctx.db.start_lesson(self.lesson.id, self.ctx.mode)
        self.item_scores = {}
        self.index = self.reached = 0
        self.go(0)
