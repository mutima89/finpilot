"""Interactive question widgets shared by lessons, the Challenge Arena,
Formula Practice and the Mistakes Notebook.

Every widget follows the same contract: the learner answers, presses Check,
gets specific feedback, may retry, may take progressive hints, and may reveal
the worked solution (after an attempt, or explicitly - which scores zero).
The widget emits ``finished`` once the item is correct or revealed.
"""
from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QHeaderView)

from ..core.format import format_value
from ..core.formula import FUNCTIONS
from ..core.formula.refs import a1_to_key, key_to_a1, col_to_letters
from ..curriculum import formula_task
from ..curriculum.grading import Feedback as FB
from ..curriculum.grading import grade_choice, grade_formula, grade_number, grade_written
from .theme import palette
from .widgets import Feedback, button, hbox, label

# Hints and worked solutions unlock only after attempts, in every mode (failed attempts needed).
HINT_GATE = {"guided": 1, "practice": 1, "challenge": 2}
SOLUTION_GATE = {"guided": 1, "practice": 2, "challenge": 3}


def _after(n: int) -> str:
    return f"in {n} {'tries' if n > 1 else 'try'}"


class QuestionWidget(QFrame):
    finished = Signal(object)   # Feedback (final)
    attempted = Signal(object)  # Feedback (each check)

    def __init__(self, q: dict, mode: str = "guided", show_question: bool = True):
        super().__init__()
        self.q = q
        self.mode = mode
        self.attempts = 0
        self.failed = 0
        self.hints_shown = 0
        self.revealed = False
        self.done = False
        self.last_answer = ""
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)
        if q.get("scenario"):
            sc = QFrame()
            sc.setObjectName("Callout")
            sl = QVBoxLayout(sc)
            sl.setContentsMargins(14, 10, 14, 10)
            sl.addWidget(label(q["scenario"], "Body", rich=True))
            self.lay.addWidget(sc)
        if show_question and q.get("question"):
            self.lay.addWidget(label(q["question"], "H3", rich=True))
        self.body = QVBoxLayout()
        self.lay.addLayout(self.body)
        self.check_btn = button("Check answer", "Primary", self.check)
        self.hint_btn = button("Hint", "", self.hint)
        self.solution_btn = button("Show solution", "Ghost", self.reveal)
        self.reset_btn = button("Reset", "Ghost", self.reset)
        self.lay.addLayout(hbox(self.check_btn, self.hint_btn, self.reset_btn, "stretch", self.solution_btn))
        self.hint_lbl = label("", "Muted", rich=True)
        self.hint_lbl.hide()
        self.lay.addWidget(self.hint_lbl)
        self.feedback = Feedback()
        self.lay.addWidget(self.feedback)
        self.solution_lbl = label("", "Body", rich=True)
        self.solution_lbl.hide()
        self.lay.addWidget(self.solution_lbl)
        self._update_hint_button()

    # subclasses implement
    def grade(self) -> FB:
        raise NotImplementedError

    def answer_text(self) -> str:
        return ""

    def expected_text(self) -> str:
        return ""

    def solution_text(self) -> str:
        return html.escape(self.q.get("solution", "")) or self.expected_text()

    def clear_input(self) -> None:
        pass

    def hints(self) -> list[str]:
        return list(self.q.get("hints", []))

    # behaviour
    def check(self):
        if self.done:
            return
        fb = self.grade()
        if fb.diagnosis in ("not_a_number", "empty", "no_answer"):
            self.feedback.show_result(None, fb.title, fb.message)
            return
        self.attempts += 1
        self.last_answer = self.answer_text()
        extra = "<br>".join(html.escape(d) for d in fb.detail)
        if fb.correct:
            self.feedback.show_result(True, fb.title, html.escape(fb.message), extra)
            self._finish(fb)
        else:
            self.failed += 1
            tip = " Try again, or take a hint." if self.hints() else " Try again."
            self.feedback.show_result(False, fb.title, html.escape(fb.message) + tip, extra)
        self.attempted.emit(fb)
        self._update_hint_button()

    def _finish(self, fb: FB):
        self.done = True
        self.final_feedback = fb
        self.check_btn.setEnabled(False)
        self.hint_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        if self.solution_text():
            self.solution_btn.setText("Show explanation")
            self.solution_btn.setEnabled(True)
        self.finished.emit(fb)

    def hint(self):
        hs = self.hints()
        if not hs:
            return
        self.hints_shown = min(self.hints_shown + 1, len(hs))
        self.hint_lbl.setText("<br>".join(f"<b>Hint {i + 1}:</b> {html.escape(h)}" for i, h in
                                          enumerate(hs[: self.hints_shown])))
        self.hint_lbl.show()
        self._update_hint_button()

    def _update_hint_button(self):
        hs = self.hints()
        gate = HINT_GATE.get(self.mode, 0)
        available = bool(hs) and not self.done and self.failed >= gate and self.hints_shown < len(hs)
        self.hint_btn.setEnabled(available)
        self.hint_btn.setVisible(bool(hs))
        if hs:
            if self.failed < gate and not self.done:
                self.hint_btn.setText(f"Hint {_after(gate - self.failed)}")
            else:
                self.hint_btn.setText(f"Hint {min(self.hints_shown + 1, len(hs))}/{len(hs)}")
        if not self.done:
            sgate = SOLUTION_GATE.get(self.mode, 1)
            self.solution_btn.setEnabled(self.failed >= sgate)
            self.solution_btn.setText("Show worked solution" if self.failed >= sgate
                                      else f"Solution {_after(sgate - self.failed)}")

    def reveal(self):
        if self.done:
            self.solution_lbl.setText("<b>Explanation:</b> " + self.solution_text())
            self.solution_lbl.show()
            return
        if self.failed < SOLUTION_GATE.get(self.mode, 1):
            return  # solutions unlock only after attempts (the button is disabled until then)
        self.revealed = True
        self.solution_lbl.setText("<b>Worked solution:</b> " + self.solution_text())
        self.solution_lbl.show()
        fb = FB(False, "Solution shown", "Review the worked solution, then try a similar item later.", "revealed")
        self._finish(fb)

    def reset(self):
        self.clear_input()
        self.feedback.hide()


# --------------------------------------------------------------------- choice


class ChoiceQuestion(QuestionWidget):
    def __init__(self, q: dict, mode: str = "guided", show_question: bool = True):
        super().__init__(q, mode, show_question)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, opt in enumerate(q["options"]):
            b = QPushButton(f"{chr(65 + i)}.  {opt}".replace("&", "&&"))
            b.setObjectName("Choice")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            self.body.addWidget(b)

    def grade(self) -> FB:
        sel = self.group.checkedId()
        return grade_choice(None if sel < 0 else sel, self.q["correct"], self.q["options"],
                            self.q.get("explanations"), self.q.get("explanation", ""))

    def answer_text(self):
        sel = self.group.checkedId()
        return self.q["options"][sel] if sel >= 0 else ""

    def expected_text(self):
        return self.q["options"][self.q["correct"]]

    def solution_text(self):
        return (f"<b>{html.escape(self.expected_text())}</b>. " + html.escape(self.q.get("explanation", "")))

    def clear_input(self):
        self.group.setExclusive(False)
        for b in self.group.buttons():
            b.setChecked(False)
        self.group.setExclusive(True)

    def _finish(self, fb):
        super()._finish(fb)
        p = palette()
        for i, b in enumerate(self.group.buttons()):
            b.setEnabled(False)
            if i == self.q["correct"]:
                b.setStyleSheet(f"border: 2px solid {p.success};")


# --------------------------------------------------------------------- number


class NumberQuestion(QuestionWidget):
    def __init__(self, q: dict, mode: str = "guided", show_question: bool = True):
        super().__init__(q, mode, show_question)
        self.edit = QLineEdit()
        fmt = q.get("fmt", "general")
        self.edit.setPlaceholderText("e.g. 12.5%" if fmt.startswith("percent") else "Type a number")
        self.edit.setMaximumWidth(260)
        self.edit.returnPressed.connect(self.check)
        unit = {"currency": "$", "currency0": "$", "percent": "%", "percent0": "%"}.get(fmt, "")
        self.body.addLayout(hbox(label("Your answer:", "Muted", wrap=False), self.edit,
                                 label(unit, "Muted", wrap=False), stretch_end=True))

    def grade(self) -> FB:
        return grade_number(self.edit.text(), float(self.q["answer"]), tol=float(self.q.get("tol", 0.01)),
                            fmt=self.q.get("fmt", "general"), mistakes=self.q.get("mistakes"),
                            explanation=self.q.get("solution", ""))

    def answer_text(self):
        return self.edit.text()

    def expected_text(self):
        return format_value(float(self.q["answer"]), self.q.get("fmt", "general"))

    def solution_text(self):
        s = self.q.get("solution")
        return html.escape(s) if s else f"The answer is <b>{self.expected_text()}</b>."

    def clear_input(self):
        self.edit.clear()

    def _finish(self, fb):
        super()._finish(fb)
        self.edit.setReadOnly(True)


# -------------------------------------------------------------------- formula


class FormulaBuilder(QDialog):
    """Guided formula-building blocks: functions, operators and references."""

    def __init__(self, parent, insert):
        super().__init__(parent)
        self.setWindowTitle("FinPilot formula blocks")
        self.insert = insert
        lay = QVBoxLayout(self)
        lay.addWidget(label("Click a block to insert it at the cursor. Click cells in the grid to insert their "
                            "reference. Press F4-style buttons to anchor with $.", "Muted"))
        ops = QHBoxLayout()
        for o in ["=", "+", "-", "*", "/", "^", "(", ")", ",", "$", "<", ">", "<>", ">=", "<=", "&"]:
            b = button(o, "Chip", lambda _=False, t=o: self.insert(t))
            ops.addWidget(b)
        lay.addLayout(ops)
        self.lst = QListWidget()
        for name in sorted(FUNCTIONS):
            it = QListWidgetItem(f"{name} — {FUNCTIONS[name].summary}")
            it.setData(Qt.UserRole, name)
            self.lst.addItem(it)
        self.lst.itemDoubleClicked.connect(lambda it: (self.insert(it.data(Qt.UserRole) + "("), self.accept()))
        lay.addWidget(self.lst)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        ins = button("Insert function", "Primary", lambda: self.lst.currentItem() and (
            self.insert(self.lst.currentItem().data(Qt.UserRole) + "("), self.accept()))
        lay.addLayout(hbox(ins, "stretch", bb))
        self.resize(560, 460)


class MiniGrid(QTableWidget):
    def __init__(self, cells: dict[str, str], target: str, fill_to: Optional[str] = None):
        keys = [a1_to_key(k) for k in cells] + [a1_to_key(target)] + ([a1_to_key(fill_to)] if fill_to else [])
        rows = max(k[0] for k in keys) + 1
        cols = max(k[1] for k in keys) + 1
        super().__init__(rows, cols)
        self.target = a1_to_key(target)
        self.fill_to = a1_to_key(fill_to) if fill_to else None
        self.setHorizontalHeaderLabels([col_to_letters(c) for c in range(cols)])
        self.setVerticalHeaderLabels([str(r + 1) for r in range(rows)])
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.horizontalHeader().setMinimumSectionSize(70)
        self.verticalHeader().setDefaultSectionSize(26)
        self.setMaximumHeight(36 + 27 * rows)
        self.setMinimumHeight(36 + 27 * rows)

    def show_sheet(self, sheet, fmt: str, targets: list[str]):
        p = palette()
        tset = {a1_to_key(t) for t in targets}
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                key = (r, c)
                cell = sheet.get(key)
                v = sheet.value(key) if cell.raw else None
                f = fmt if key in tset else "general"
                text = format_value(v, f) if cell.raw else ""
                if cell.raw.startswith("=") and key not in tset:
                    text = format_value(v, "general")
                it = QTableWidgetItem(text)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if key in tset:
                    from PySide6.QtGui import QBrush, QColor
                    it.setBackground(QBrush(QColor(p.amber_soft if not cell.raw else p.output_bg)))
                    if not cell.raw:
                        it.setText("?" if key == self.target else "")
                if cell.raw.startswith("="):
                    it.setToolTip(cell.raw)
                self.setItem(r, c, it)


class FormulaQuestion(QuestionWidget):
    def __init__(self, q: dict, mode: str = "guided", show_question: bool = True):
        super().__init__(q, mode, show_question and not q.get("prompt"))
        if q.get("prompt"):
            self.lay.insertWidget(0, label(q["prompt"], "H3", rich=True))
        self.task = formula_task(q)
        self.grid = MiniGrid(self.task.cells, self.task.target, self.task.fill_to)
        self.targets = self._targets()
        self.grid.show_sheet(self.task.sheet(), self.task.fmt, self.targets)
        self.grid.cellClicked.connect(self._cell_clicked)
        self.body.addWidget(self.grid)
        self.edit = QLineEdit()
        self.edit.setObjectName("FormulaBar")
        self.edit.setPlaceholderText(f"Formula for {self.task.target}, e.g. =B1*B2")
        self.edit.returnPressed.connect(self.check)
        blocks = button("Formula blocks…", "", self._blocks, "Insert functions and operators from a list")
        self.body.addLayout(hbox(label(f"{self.task.target} =", "H3", wrap=False), self.edit, blocks))
        tip = "Tip: click a cell in the grid to insert its reference."
        if self.task.fill_to:
            tip += f" Your formula will be copied from {self.task.target} to {self.task.fill_to}."
        self.body.addWidget(label(tip, "Muted"))

    def _targets(self):
        if not self.task.fill_to:
            return [self.task.target]
        r0, c0 = a1_to_key(self.task.target)
        r1, c1 = a1_to_key(self.task.fill_to)
        return [key_to_a1((r0, c)) for c in range(c0, c1 + 1)]

    def _insert(self, text: str):
        if text == "$":
            self._anchor()
            return
        if not self.edit.text() and text != "=":
            self.edit.setText("=")
        self.edit.insert(text)
        self.edit.setFocus()

    def _anchor(self):
        import re
        t = self.edit.text()
        pos = self.edit.cursorPosition()
        for m in re.finditer(r"\$?[A-Z]{1,3}\$?\d+", t):
            if m.start() <= pos <= m.end():
                ref = m.group().replace("$", "")
                col = re.match(r"[A-Z]+", ref).group()
                row = ref[len(col):]
                cur = m.group()
                cycle = [ref, f"${col}${row}", f"{col}${row}", f"${col}{row}"]
                nxt = cycle[(cycle.index(cur) + 1) % 4] if cur in cycle else cycle[1]
                self.edit.setText(t[:m.start()] + nxt + t[m.end():])
                self.edit.setCursorPosition(m.start() + len(nxt))
                return

    def _cell_clicked(self, r, c):
        if self.done:
            return
        self._insert(key_to_a1((r, c)))

    def _blocks(self):
        FormulaBuilder(self, self._insert).exec()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F4:
            self._anchor()
            return
        super().keyPressEvent(e)

    def grade(self) -> FB:
        fb = grade_formula(self.task, self.edit.text())
        text = self.edit.text().strip()
        if text:
            s = self.task.sheet()
            if not text.startswith("="):
                text = "=" + text
            try:
                s.set(self.task.target, text)
                if self.task.fill_to:
                    s.fill(a1_to_key(self.task.target), [a1_to_key(t) for t in self.targets[1:]])
                self.grid.show_sheet(s, self.task.fmt, self.targets)
            except Exception:
                pass
        return fb

    def answer_text(self):
        return self.edit.text()

    def expected_text(self):
        return self.task.reference

    def solution_text(self):
        s = self.q.get("solution")
        return (html.escape(s) if s else f"<code>{html.escape(self.task.reference)}</code>")

    def clear_input(self):
        self.edit.clear()
        self.grid.show_sheet(self.task.sheet(), self.task.fmt, self.targets)

    def _finish(self, fb):
        super()._finish(fb)
        self.edit.setReadOnly(True)


# -------------------------------------------------------------------- written


class WrittenQuestion(QuestionWidget):
    def __init__(self, q: dict, mode: str = "guided", show_question: bool = True):
        super().__init__({**q, "question": q.get("prompt") or q.get("question", "")}, mode, show_question)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Write your recommendation here…")
        self.edit.setMinimumHeight(150)
        self.body.addWidget(self.edit)
        crit = "".join(f"<li>{html.escape(r['criterion'])}</li>" for r in q.get("rubric", []))
        self.body.addWidget(label(f"<b>Rubric (transparent):</b><ul style='margin:2px'>{crit}</ul>"
                                  "FinPilot checks that these elements are present. It cannot judge the quality "
                                  "of your reasoning, so compare with the model answer afterwards.", "Muted",
                                  rich=True))
        self.check_btn.setText("Check against rubric")
        self.rubric_result: list = []

    def grade(self) -> FB:
        if len(self.edit.toPlainText().split()) < 5:
            return FB(False, "Write a little more", "Write at least a few sentences first.", "empty")
        fb, results = grade_written(self.edit.toPlainText(), self.q.get("rubric", []))
        self.rubric_result = results
        items = "<br>".join(("✓ " if ok else "✗ ") + html.escape(c) for c, ok in results)
        fb.detail = []
        fb.message = fb.message + "\n"
        self._rubric_html = items
        return fb

    def check(self):
        super().check()
        if getattr(self, "_rubric_html", ""):
            self.feedback.extra.setText(self._rubric_html)
            self.feedback.extra.show()

    def answer_text(self):
        return self.edit.toPlainText()

    def solution_text(self):
        return "<b>Model answer:</b> " + html.escape(self.q.get("model_answer", ""))

    def clear_input(self):
        self.edit.clear()


def make_question(q: dict, mode: str = "guided", show_question: bool = True) -> QuestionWidget:
    kind = q.get("kind") or q.get("mode") or "choice"
    if q.get("type") == "build":
        kind = q.get("mode", "formula")
    if q.get("type") == "written":
        kind = "written"
    return {"choice": ChoiceQuestion, "number": NumberQuestion, "formula": FormulaQuestion,
            "written": WrittenQuestion}[kind](q, mode, show_question)
