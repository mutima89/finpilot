"""FinPilot Modeling Lab: spreadsheet workspace with guided model building."""
from __future__ import annotations

import html
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

from ...config import autosave_dir, projects_dir
from ...core import hotel_sheet as hs
from ...core.formula import CellError
from ...core.formula.refs import key_to_a1
from ...core.sheet import FORMATS, explain
from ...curriculum import hotel_project as hp
from ...data import projects as pj
from ..charts import Chart
from ..context import AppContext
from ..grid import SheetView
from ..questions import HINT_GATE, SOLUTION_GATE, FormulaBuilder
from ..theme import palette
from ..widgets import Card, Feedback, FlowLayout, button, clear_layout, label

log = logging.getLogger(__name__)

ROLE_OPTIONS = [("", "No role"), ("input", "Input"), ("calc", "Calculation"), ("output", "Output"),
                ("label", "Label"), ("check", "Check")]
FORMAT_LABELS = {"general": "General", "number": "Number 0.00", "number0": "Number 0", "currency": "Currency $0.00",
                 "currency0": "Currency $0", "percent": "Percent 0.0%", "percent0": "Percent 0%", "date": "Date",
                 "text": "Text"}


class LabPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.setObjectName("Page")
        self.ctx = ctx
        self.task_index = 0
        self.task_attempts: dict[str, int] = {}
        self.hints_shown: dict[str, int] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 14)
        outer.setSpacing(10)

        head = QHBoxLayout()
        self.title = label("Modeling Lab", "H1", wrap=False)
        self.project_lbl = label("", "Muted", wrap=False)
        head.addWidget(self.title)
        head.addWidget(self.project_lbl)
        head.addStretch(1)
        menu_btn = QToolButton()
        menu_btn.setText("Project ▾")
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(menu_btn)
        for text, fn in (("New guided hotel model", self.new_guided), ("New blank sheet", self.new_blank),
                         ("Open…", self.open_dialog), ("Save as…", self.save_as),
                         ("Export to Excel…", self.export_excel)):
            menu.addAction(text, fn)
        menu_btn.setMenu(menu)
        head.addWidget(menu_btn)
        head.addWidget(button("Save", "Primary", self.save, "Save the project (Ctrl+S)"))
        self.title.setMinimumWidth(self.title.sizeHint().width())
        self.project_lbl.setMinimumWidth(40)
        outer.addLayout(head)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.undo_btn = button("↶ Undo", "", lambda: self._do(self.view.undo), "Ctrl+Z")
        self.redo_btn = button("↷ Redo", "", lambda: self._do(self.view.redo), "Ctrl+Y")
        tools.addWidget(self.undo_btn)
        tools.addWidget(self.redo_btn)
        tools.addWidget(button("Fill right →", "", self.fill_right,
                               "Copy the first selected cell's formula across the selected row (Ctrl+R)"))
        tools.addWidget(button("Explain", "", self.explain_current, "Show how the selected cell is calculated"))
        tools.addWidget(button("Trace", "", self.trace_current, "Highlight the cells this formula uses"))
        tools.addWidget(button("Name…", "", self.define_name, "Create a named assumption, e.g. ROOMS = B4"))
        tools.addWidget(button("Blocks…", "", self.blocks, "Build a formula from blocks"))
        tools.addStretch(1)
        outer.addLayout(tools)

        fbar = QHBoxLayout()
        self.cell_lbl = label("A1", "H3", wrap=False)
        self.cell_lbl.setMinimumWidth(48)
        self.formula = QLineEdit()
        self.formula.setObjectName("FormulaBar")
        self.formula.setPlaceholderText("Select a cell, then type a value or a formula starting with =")
        self.formula.returnPressed.connect(self.commit_formula)
        self.value_lbl = label("", "Muted", wrap=False)
        fbar.addWidget(self.cell_lbl)
        fbar.addWidget(label("ƒx", "Muted", wrap=False))
        fbar.addWidget(self.formula, 1)
        fbar.addWidget(self.value_lbl)
        fbar.addWidget(label("Role:", "Muted", wrap=False))
        self.role_box = QComboBox()
        for k, t in ROLE_OPTIONS:
            self.role_box.addItem(t, k)
        self.role_box.activated.connect(self.apply_role)
        fbar.addWidget(self.role_box)
        fbar.addWidget(label("Format:", "Muted", wrap=False))
        self.fmt_box = QComboBox()
        for k in FORMATS:
            self.fmt_box.addItem(FORMAT_LABELS[k], k)
        self.fmt_box.activated.connect(self.apply_format)
        fbar.addWidget(self.fmt_box)
        outer.addLayout(fbar)

        split = QSplitter(Qt.Horizontal)
        if ctx.project is None:
            ctx.project = self._recover_or_new()
        self.view = SheetView(ctx.project.sheet)
        self.view.cell_selected.connect(self.on_select)
        self.view.edited.connect(self.on_edit)
        split.addWidget(self.view)
        self.side = QTabWidget()
        self.side.setMinimumWidth(330)
        self.side.addTab(self._guided_tab(), "Build")
        self.side.addTab(self._inspect_tab(), "Inspect")
        self.side.addTab(self._checks_tab(), "Checks")
        self.side.addTab(self._chart_tab(), "Chart")
        split.addWidget(self.side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([640, 400])
        outer.addWidget(split, 1)
        self.err_lbl = label("", "Muted", wrap=False)
        outer.addWidget(self.err_lbl)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(2500)
        self.autosave_timer.timeout.connect(self.autosave)
        self._load_project_state()
        self.view.setCurrentIndex(self.view.model().index(hs.R_AVAIL - 1, 1))
        self.view.horizontalScrollBar().setValue(0)

    # ---------------------------------------------------------- project
    def _recover_or_new(self) -> pj.Project:
        auto = autosave_dir() / "current.finpilot"
        if auto.exists():
            try:
                p = pj.load(auto)
                p.path = Path(p.state.get("saved_path")) if p.state.get("saved_path") else None
                return p
            except pj.ProjectError:
                log.warning("Autosave unreadable; starting a new model")
        return pj.new_hotel_project()

    def set_project(self, p: pj.Project):
        self.ctx.project = p
        self.ctx.project_dirty = False
        self.view.set_sheet(p.sheet)
        self._load_project_state()
        self.ctx.signals.project_changed.emit()

    def _load_project_state(self):
        p = self.ctx.project
        self.project_lbl.setText(f"  ·  {p.name}" + (f"  ({p.path.name})" if p.path else "  (not saved yet)"))
        guided = p.kind == "hotel_model" and p.state.get("guided", False)
        self.side.setTabEnabled(0, guided)
        if not guided and self.side.currentIndex() == 0:
            self.side.setCurrentIndex(1)
        done = set(p.state.get("tasks_done", []))
        self.task_index = next((i for i, t in enumerate(hp.TASKS) if t.id not in done), len(hp.TASKS) - 1)
        self.refresh_tasks()
        self.refresh_checks()
        self._highlight_task()

    def new_guided(self):
        if not self._confirm_discard():
            return
        self.set_project(pj.new_hotel_project())
        self.ctx.notify("New guided hotel model created from fictional Harbour Crest data.")

    def new_blank(self):
        if not self._confirm_discard():
            return
        from ...core.sheet import Sheet
        self.set_project(pj.Project(name="Blank model", kind="lab", sheet=Sheet("Model", rows=40, cols=14)))

    def _confirm_discard(self) -> bool:
        if not self.ctx.project_dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save the current model first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save()
        return True

    def open_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open FinPilot project", str(projects_dir()),
                                              "FinPilot projects (*.finpilot)")
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> bool:
        try:
            p = pj.load(path)
        except pj.ProjectError as e:
            QMessageBox.warning(self, "Cannot open project", str(e))
            return False
        if p.checksum_warning:
            QMessageBox.information(self, "File was changed outside FinPilot",
                                    "This project's checksum does not match its contents, so it was edited outside "
                                    "FinPilot or partly damaged. It opened successfully; please review the model "
                                    "checks before relying on it.")
        self.set_project(p)
        self._register()
        return True

    def save(self) -> bool:
        p = self.ctx.project
        if p.path is None:
            return self.save_as()
        return self._write(p.path)

    def save_as(self) -> bool:
        p = self.ctx.project
        default = projects_dir() / (p.name.replace("/", "-") + pj.EXTENSION)
        path, _ = QFileDialog.getSaveFileName(self, "Save FinPilot project", str(default),
                                              "FinPilot projects (*.finpilot)")
        if not path:
            return False
        return self._write(Path(path))

    def _write(self, path: Path) -> bool:
        p = self.ctx.project
        try:
            p.state["saved_path"] = str(path.with_suffix(pj.EXTENSION))
            out = pj.save(p, path)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", f"FinPilot could not save the file: {e}")
            return False
        self.ctx.project_dirty = False
        self._register()
        self.autosave()
        self._load_project_state()
        self.ctx.notify(f"Saved {out.name}")
        return True

    def _register(self):
        p = self.ctx.project
        if p.path is None:
            return
        st = hp.project_status(p.sheet) if p.kind == "hotel_model" else None
        validated = bool(st and st["validated"])
        progress = (st["done"] / st["total"]) if st else 0.0
        self.ctx.db.upsert_project(p.name, str(p.path), p.kind, validated, progress)
        self.ctx.signals.progress_changed.emit()

    def autosave(self):
        if not self.ctx.setting("autosave"):
            return
        try:
            pj.save(self.ctx.project, autosave_dir() / "current.finpilot")
        except OSError:
            log.exception("Autosave failed")

    # ------------------------------------------------------------ editing
    def _do(self, fn):
        fn()
        self.on_edit()
        self.on_select(*(self.view.current_key() or (0, 0)))

    def on_select(self, r, c):
        key = (r, c)
        cell = self.view.sheet.get(key)
        self.cell_lbl.setText(key_to_a1(key))
        self.formula.setText(cell.raw)
        v = self.view.sheet.value(key) if cell.raw else None
        from ...core.format import format_value
        if isinstance(v, CellError):
            self.value_lbl.setText(f"{v.code}  ({v.category} problem)")
            self.value_lbl.setToolTip(v.explanation)
        else:
            self.value_lbl.setText(("= " + format_value(v, cell.fmt)) if cell.is_formula else "")
            self.value_lbl.setToolTip("")
        i = self.role_box.findData(cell.role)
        self.role_box.setCurrentIndex(max(0, i))
        j = self.fmt_box.findData(cell.fmt)
        self.fmt_box.setCurrentIndex(max(0, j))
        if self.side.currentIndex() == 1:
            self.explain_current()
        if self.side.currentIndex() == 3:
            self.refresh_chart()

    def commit_formula(self):
        key = self.view.current_key()
        if key is None:
            return
        idx = self.view.model().index(*key)
        self.view.model().setData(idx, self.formula.text())
        self.view.setFocus()
        nxt = self.view.model().index(key[0], min(key[1] + 1, self.view.model().columnCount() - 1))
        self.view.setCurrentIndex(nxt)

    def on_edit(self):
        self.ctx.project_dirty = True
        self.undo_btn.setEnabled(self.view.sheet.can_undo)
        self.redo_btn.setEnabled(self.view.sheet.can_redo)
        errs = self.view.sheet.errors()
        if errs:
            cats = {}
            for e in errs.values():
                cats[e.category] = cats.get(e.category, 0) + 1
            self.err_lbl.setText("Cells with errors: " + ", ".join(f"{n} {c}" for c, n in cats.items()) +
                                 ". Select a red cell and choose Explain cell.")
        else:
            self.err_lbl.setText("No error values in the sheet.")
        self.refresh_checks()
        self.autosave_timer.start()

    def fill_right(self):
        if not self.view.fill_right():
            QMessageBox.information(self, "Fill right", "Select a row range first: the first cell holds the "
                                    "formula, the rest receive copies (e.g. select B15:M15).")
        self.on_edit()

    def apply_role(self):
        keys = self.view.selected_keys()
        role = self.role_box.currentData()
        self.view.sheet.set_many([(k, None, role) for k in keys])
        self.view.model_.refresh()
        self.on_edit()

    def apply_format(self):
        keys = self.view.selected_keys()
        fmt = self.fmt_box.currentData()
        self.view.sheet.set_many([(k, None, None, fmt) for k in keys])
        self.view.model_.refresh()
        self.on_edit()

    def define_name(self):
        key = self.view.current_key()
        default_target = key_to_a1(key) if key else "B4"
        name, ok = QInputDialog.getText(self, "Named assumption", "Name (letters, digits, _):", text="ROOMS")
        if not ok or not name:
            return
        target, ok = QInputDialog.getText(self, "Named assumption", "Refers to cell or range:", text=default_target)
        if not ok:
            return
        try:
            self.view.sheet.define_name(name, target)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid name", str(e))
            return
        self.view.model_.refresh()
        self.ctx.notify(f"{name.upper()} now refers to {target.upper()}. Use it in formulas, e.g. ={name.upper()}*B9")

    def blocks(self):
        def ins(t):
            if not self.formula.text() and t != "=":
                self.formula.setText("=")
            self.formula.insert(t)
            self.formula.setFocus()
        FormulaBuilder(self, ins).exec()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_R and e.modifiers() & Qt.ControlModifier:
            self.fill_right()
            return
        if e.key() == Qt.Key_S and e.modifiers() & Qt.ControlModifier:
            self.save()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ inspect
    def _inspect_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Select a cell to see its formula, the cells it reads (precedents), the cells that "
                            "use it (dependents) and where any error comes from.", "Muted"))
        self.explain_box = QPlainTextEdit()
        self.explain_box.setReadOnly(True)
        lay.addWidget(self.explain_box, 1)
        self.names_lbl = label("", "Muted", rich=True)
        lay.addWidget(self.names_lbl)
        return w

    def explain_current(self):
        key = self.view.current_key()
        if key is None:
            return
        self.explain_box.setPlainText("\n\n".join(explain(self.view.sheet, key)))
        names = self.view.sheet.names
        self.names_lbl.setText("<b>Named assumptions:</b> " + (", ".join(f"{n} = {t}" for n, t in names.items())
                                                              if names else "none"))
        self.side.setCurrentIndex(1)

    def trace_current(self):
        key = self.view.current_key()
        if key is None:
            return
        self.view.model_.trace = self.view.sheet.precedents(key)
        self.view.model_.refresh()
        QTimer.singleShot(4000, lambda: (setattr(self.view.model_, "trace", set()), self.view.model_.refresh()))
        self.explain_current()

    # ------------------------------------------------------------ guided
    def _guided_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)
        lay.addWidget(label("Build Harbour Crest's 12-month model one row at a time. Each task is checked on your "
                            "inputs and on changed inputs, so typed numbers and broken references are caught.",
                            "Muted"))
        self.task_list = QListWidget()
        self.task_list.setMaximumHeight(210)
        self.task_list.currentRowChanged.connect(self.select_task)
        lay.addWidget(self.task_list)
        self.task_card = Card("Card", 14, 8)
        lay.addWidget(self.task_card, 1)
        # Scrolls when hints and the worked solution are open on a small screen.
        w.setObjectName("PageInner")
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setWidget(w)
        return sa

    def refresh_tasks(self):
        done = set(self.ctx.project.state.get("tasks_done", []))
        self.task_list.blockSignals(True)
        self.task_list.clear()
        for t in hp.TASKS:
            mark = "✓" if t.id in done else "○"
            self.task_list.addItem(QListWidgetItem(f"{mark}  {t.id[1:]}. {t.title}"))
        self.task_list.setCurrentRow(self.task_index)
        self.task_list.blockSignals(False)
        self.select_task(self.task_index)

    def select_task(self, i: int):
        if i < 0:
            return
        self.task_index = i
        t = hp.TASKS[i]
        clear_layout(self.task_card.lay)
        mode = self.ctx.mode
        self.task_card.add(label(f"TASK {i + 1} OF {len(hp.TASKS)}", "Eyebrow"), label(t.title, "H2"))
        instr = t.instruction if mode != "challenge" else t.instruction.split(".")[0] + "."
        self.task_card.add(label(instr, "Body"))
        self.task_fb = Feedback()
        self.hint_lbl = label("", "Muted", rich=True)
        self.sol_lbl = label("", "Body", rich=True)
        self.sol_lbl.hide()
        check = button("Check task", "Primary", self.check_task)
        hint = button("Hint", "", self.task_hint)
        sol = button("Show solution", "Ghost", self.task_solution)
        goto = button("Go to cells", "Ghost", self._highlight_task)
        row = QWidget()
        fl = FlowLayout(row)
        for b in (check, hint, goto, sol):
            fl.addWidget(b)
        self.task_card.add(row, self.task_fb, self.hint_lbl, self.sol_lbl)
        self.task_card.add("stretch")
        self._hint_btn = hint
        self._sol_btn = sol
        self._update_hint()
        self._highlight_task()

    def _gate(self) -> int:
        return HINT_GATE.get(self.ctx.mode, 1)

    def _solution_gate(self) -> int:
        return SOLUTION_GATE.get(self.ctx.mode, 1)

    def _update_hint(self):
        t = hp.TASKS[self.task_index]
        shown = self.hints_shown.get(t.id, 0)
        fails = self.task_attempts.get(t.id, 0)
        self._hint_btn.setEnabled(fails >= self._gate() and shown < len(t.hints))
        self._hint_btn.setText(f"Hint {min(shown + 1, len(t.hints))}/{len(t.hints)}" if fails >= self._gate()
                               else f"Hint in {self._gate() - fails} {'tries' if self._gate() - fails > 1 else 'try'}")
        sg = self._solution_gate()
        self._sol_btn.setEnabled(fails >= sg)
        self._sol_btn.setText("Show solution" if fails >= sg
                              else f"Solution in {sg - fails} {'tries' if sg - fails > 1 else 'try'}")
        if shown:
            self.hint_lbl.setText("<br>".join(f"<b>Hint {k + 1}:</b> {html.escape(h)}"
                                              for k, h in enumerate(t.hints[:shown])))

    def task_hint(self):
        t = hp.TASKS[self.task_index]
        self.hints_shown[t.id] = self.hints_shown.get(t.id, 0) + 1
        self._update_hint()

    def task_solution(self):
        t = hp.TASKS[self.task_index]
        if self.task_attempts.get(t.id, 0) < self._solution_gate():
            return  # unlocks only after attempts (the button is disabled until then)
        self.ctx.project.state.setdefault("revealed", [])
        if t.id not in self.ctx.project.state["revealed"]:
            self.ctx.project.state["revealed"].append(t.id)
        self.sol_lbl.setText("<b>Solution:</b> " + html.escape(t.solution))
        self.sol_lbl.show()

    def _highlight_task(self):
        if not self.ctx.project or self.ctx.project.kind != "hotel_model" or not self.ctx.project.state.get("guided"):
            self.view.model_.highlight = set()
            self.view.model_.refresh()
            return
        t = hp.TASKS[self.task_index]
        from ...core.formula.refs import a1_to_key
        keys = {a1_to_key(c) for c in t.cells}
        self.view.model_.highlight = keys
        self.view.model_.refresh()
        first = min(keys)
        self.view.scrollTo(self.view.model().index(*first))

    def check_task(self):
        t = hp.TASKS[self.task_index]
        fb = hp.check_task(self.view.sheet, t)
        self.task_attempts[t.id] = self.task_attempts.get(t.id, 0) + (0 if fb.diagnosis in ("empty",) else 1)
        extra = "<br>".join(html.escape(d) for d in fb.detail)
        self.task_fb.show_result(fb.correct, fb.title, html.escape(fb.message), extra)
        st = self.ctx.project.state
        if fb.correct:
            done = st.setdefault("tasks_done", [])
            if t.id not in done:
                done.append(t.id)
                revealed = t.id in st.get("revealed", [])
                attempts = self.task_attempts.get(t.id, 1)
                from ...curriculum import progression as prog
                score = prog.item_score(attempts, True, revealed)
                self.ctx.db.add_evidence(["hotel_model", "references"], f"task:P3/{t.id}", score, 1.0)
                if not revealed:
                    self.ctx.award("project_task", f"P3/{t.id}")
            self.ctx.db.start_lesson("P3", self.ctx.mode)
            self.refresh_tasks_marks()
            self._maybe_validate()
        elif fb.diagnosis not in ("empty",):
            self.ctx.record_mistake(ref=f"P3/{t.id}", lesson_id="P3", skill="hotel_model",
                                    question=f"Lab task: {t.title} - {t.instruction}", answer="(see model)",
                                    expected=t.solution, fb=fb)
        self._update_hint()
        self.on_edit()

    def refresh_tasks_marks(self):
        done = set(self.ctx.project.state.get("tasks_done", []))
        for i, t in enumerate(hp.TASKS):
            it = self.task_list.item(i)
            if it:
                it.setText(f"{'✓' if t.id in done else '○'}  {t.id[1:]}. {t.title}")

    def _maybe_validate(self):
        st = hp.project_status(self.view.sheet)
        if st["validated"] and not self.ctx.project.state.get("validated"):
            self.ctx.project.state["validated"] = True
            self.ctx.db.add_evidence(["hotel_model", "hotel_kpis", "revenue_drivers", "variance"], "model:P3", 1.0, 3.0)
            self.ctx.award("project_validated", "P3")
            revealed = len(self.ctx.project.state.get("revealed", []))
            score = max(0.0, 1.0 - 0.1 * revealed)
            self.ctx.db.complete_lesson("P3", score)
            self._register()
            if self.ctx.project.path is None:
                self.ctx.db.upsert_project(self.ctx.project.name, str(autosave_dir() / "current.finpilot"),
                                           "hotel_model", True, 1.0)
            QMessageBox.information(self, "Model validated",
                                    "Your 12-month model matches FinPilot's independent calculation in every month "
                                    "and all model checks pass. Save it to your portfolio, then explore scenarios "
                                    "in the Hotel Simulation Center.")
            self.ctx.after_progress()
        self.refresh_checks()

    # ------------------------------------------------------------- checks
    def _checks_tab(self) -> QWidget:
        inner = QWidget()
        inner.setObjectName("PageInner")
        self.checks_lay = QVBoxLayout(inner)
        self.checks_lay.setSpacing(8)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setWidget(inner)
        return sa

    def refresh_checks(self):
        if not hasattr(self, "checks_lay"):
            return
        clear_layout(self.checks_lay)
        p = palette()
        s = self.view.sheet
        errs = s.errors()
        rows = []
        if errs:
            cats = {}
            for k, e in errs.items():
                cats.setdefault(e.category, []).append(key_to_a1(k))
            for cat, cells in cats.items():
                rows.append((False, f"{cat.title()} errors", ", ".join(cells[:8]) + (" …" if len(cells) > 8 else "")))
        else:
            rows.append((True, "No error values", "No formula, input, missing-data or maths errors."))
        if self.ctx.project.kind == "hotel_model":
            for r in (hs.R_CHK1, hs.R_CHK2):
                vals = [s.value(f"{c}{r}") for c in hs.MONTH_COLS]
                rows.append((all(v is True for v in vals), hs.LABELS[r],
                             "All months pass." if all(v is True for v in vals) else
                             "Fails until the rows it depends on are built correctly."))
            occ = [s.value(f"{c}{hs.R_OCC}") for c in hs.MONTH_COLS]
            bad = [hs.MONTH_COLS[i] for i, v in enumerate(occ) if isinstance(v, (int, float)) and not 0 <= v <= 1]
            rows.append((not bad, "Occupancy inputs between 0% and 100%",
                         "OK" if not bad else "Impossible occupancy in column " + ", ".join(bad)))
            warn = [hs.MONTH_COLS[i] for i, v in enumerate(occ) if isinstance(v, (int, float)) and 0.97 < v <= 1]
            if warn:
                rows.append((None, "Reasonableness: very high occupancy",
                             "Valid but unusual for a whole month: " + ", ".join(warn)))
            adr = [s.value(f"{c}{hs.R_ADR}") for c in hs.MONTH_COLS]
            odd = [hs.MONTH_COLS[i] for i, v in enumerate(adr) if isinstance(v, (int, float)) and (v < 100 or v > 2500)]
            if odd:
                rows.append((None, "Reasonableness: unusual ADR for a luxury hotel",
                             "Check columns " + ", ".join(odd)))
            st = hp.project_status(s) if self.ctx.project.state.get("guided") else None
            if st:
                rows.append((st["done"] == st["total"], f"Guided tasks complete: {st['done']} of {st['total']}", ""))
                for name, ok, msg in st["verification"]:
                    rows.append((ok, f"Independent check: {name}", msg))
        for ok, title, msg in rows:
            color = p.success if ok else (p.amber if ok is None else p.coral)
            mark = "✓" if ok else ("!" if ok is None else "✗")
            self.checks_lay.addWidget(label(f"<span style='color:{color}; font-weight:700'>{mark}</span> "
                                            f"<b>{html.escape(title)}</b><br><span>{html.escape(msg)}</span>",
                                            "Body", rich=True))
        self.checks_lay.addStretch(1)

    # -------------------------------------------------------------- chart
    def _chart_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("Select any cell in a row with monthly values (columns B-M) to chart that row.", "Muted"))
        self.chart = Chart(4.5, 3.2)
        lay.addWidget(self.chart, 1)
        self.side.currentChanged.connect(lambda i: self.refresh_chart() if i == 3 else None)
        return w

    def refresh_chart(self):
        key = self.view.current_key()
        if key is None:
            return
        r = key[0]
        s = self.view.sheet
        vals = [s.value((r, c)) for c in range(1, 13)]
        nums = [v if isinstance(v, (int, float)) and not isinstance(v, bool) else None for v in vals]
        name = s.get((r, 0)).raw or f"Row {r + 1}"
        if not any(v is not None for v in nums):
            self.chart.reset()
            self.chart.ax.text(0.5, 0.5, "No numbers in this row yet", ha="center", va="center",
                               transform=self.chart.ax.transAxes, color=palette().muted)
            self.chart.finish(legend=False)
            return
        fmt = s.get((r, 1)).fmt
        kind = "pct" if fmt.startswith("percent") else ("money" if fmt.startswith("currency") else "plain")
        labels = [s.get((hs.R_HEAD - 1, c)).raw or str(c) for c in range(1, 13)]
        self.chart.lines(labels, [(name, nums)], fmt=kind, title=name)

    def export_excel(self):
        self.ctx.navigate("export")
