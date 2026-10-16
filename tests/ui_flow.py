"""End-to-end UI journey used by tests/test_ui.py (and runnable on its own).

Drives the real widgets: onboarding, every V1 lesson step by step (one deliberate
mistake per lesson, then the right answer), the guided hotel model in the Lab
via the formula bar and Fill right, the final assessment, the mistakes
notebook, save/reopen and every export.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel
from PySide6.QtWidgets import QApplication

from finpilot.core.formula.refs import a1_to_key
from finpilot.ui.questions import (ChoiceQuestion, FormulaQuestion, NumberQuestion, QuestionWidget,
                                   WrittenQuestion)


def pump(n: int = 3):
    for _ in range(n):
        QApplication.processEvents()


def answer(w: QuestionWidget, wrong_first: bool = False) -> None:
    """Answer a question widget through its own controls."""
    if wrong_first and not isinstance(w, WrittenQuestion):
        if isinstance(w, ChoiceQuestion):
            wrong = next(i for i in range(len(w.q["options"])) if i != w.q["correct"])
            w.group.button(wrong).setChecked(True)
        elif isinstance(w, NumberQuestion):
            w.edit.setText("123456789")
        elif isinstance(w, FormulaQuestion):
            w.edit.setText("=1")
        w.check_btn.click()
        assert not w.done or w.revealed is False
    if isinstance(w, ChoiceQuestion):
        w.group.button(w.q["correct"]).setChecked(True)
    elif isinstance(w, NumberQuestion):
        w.edit.setText(w.expected_text())
    elif isinstance(w, FormulaQuestion):
        w.edit.setText(w.task.reference)
    elif isinstance(w, WrittenQuestion):
        w.edit.setPlainText(w.q.get("model_answer", ""))
    w.check_btn.click()
    pump(1)


def complete_lesson(win, lesson_id: str, mistakes: bool = True) -> dict:
    page = win.pages["lesson"]
    win.navigate("lesson", lesson_id)
    pump()
    first_wrong = mistakes
    guard = 0
    while True:
        guard += 1
        assert guard < 60, f"{lesson_id}: lesson did not finish"
        step = page.steps[page.index]
        if step["type"] == "progress":
            break
        if step["type"] == "predict":
            qs = [w for w in page.card.findChildren(ChoiceQuestion)]
            qs[0].group.button(0).setChecked(True)
            qs[0].check_btn.click()
        for w in page.card.findChildren(QuestionWidget):
            if not w.done and w.check_btn.isVisible() and step["type"] != "predict":
                answer(w, wrong_first=first_wrong)
                first_wrong = False
                assert w.done, (f"{lesson_id} {step['type']}: correct answer not accepted: "
                                f"{w.q.get('question', '')[:80]!r} answered {w.answer_text()!r}: "
                                f"{w.feedback.title.text()} {w.feedback.msg.text()[:200]}")
        pump(1)
        assert page.next_btn.isEnabled(), f"{lesson_id} {step['type']}: Continue still blocked"
        page.next_btn.click()
        pump(1)
    return win.ctx.db.lesson_progress(lesson_id)


def build_lab_model(win) -> dict:
    """Build the 10 guided tasks through the formula bar and Fill right."""
    from finpilot.curriculum import hotel_project as hp
    win.navigate("lab")
    lab = win.pages["lab"]
    lab.new_guided()
    pump()
    view, model = lab.view, lab.view.model()
    for ti, task in enumerate(hp.TASKS):
        lab.select_task(ti)
        cells = task.cells
        first = a1_to_key(cells[0])
        view.setCurrentIndex(model.index(*first))
        lab.formula.setText(task.reference[cells[0]])
        lab.commit_formula()
        rest = cells[1:]
        if rest and all(a1_to_key(c)[0] == first[0] for c in cells):
            # select the row range and use Fill right, as a learner would
            last = a1_to_key(cells[-1])
            sel = QItemSelection(model.index(*first), model.index(*last))
            view.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)
            lab.fill_right()
        else:
            for c in rest:
                view.setCurrentIndex(model.index(*a1_to_key(c)))
                lab.formula.setText(task.reference[c])
                lab.commit_formula()
        lab.check_task()
        pump(1)
        assert task.id in lab.ctx.project.state.get("tasks_done", []), f"Lab task {task.id} not accepted"
    return hp.project_status(view.sheet)


def run_all(win, out_dir: Path, shots: bool = False) -> dict:
    ctx = win.ctx
    results = {}
    if getattr(win, "onboarding", None):
        win.onboarding.name.setText("Test learner")
        win.onboarding.finish()
    pump()
    order = [l.id for l in ctx.cur.lessons if l.kind != "lab_project"]
    for lid in order:
        pr = complete_lesson(win, lid)
        results[lid] = pr["status"]
    status = build_lab_model(win)
    results["lab_validated"] = status["validated"]
    lab = win.pages["lab"]
    path = out_dir / "Harbour Crest test.finpilot"
    assert lab._write(path)
    results["saved"] = path.exists()
    assert lab.open_path(path)
    results["reopened_tasks"] = len(ctx.project.state.get("tasks_done", []))

    # Final assessment: answer everything correctly first time.
    win.navigate("challenge")
    ch = win.pages["challenge"]
    ch.start()
    pump()
    for q, w in ch.widgets:
        answer(w)
    ch.submit()
    a = ctx.db.assessments("final")[-1]
    results["final_score"] = a["score"]
    results["final_passed"] = bool(a["passed"])

    # Mistakes notebook: review every due item correctly.
    win.navigate("mistakes")
    mk = win.pages["mistakes"]
    results["mistakes_recorded"] = len(ctx.db.mistakes())
    # Pretend a day has passed so the first reviews are due, then review them correctly.
    import datetime as dt
    ctx.db.conn.execute("UPDATE mistakes SET next_review=?", (dt.date.today().isoformat(),))
    ctx.db.conn.commit()
    mk.refresh()
    mk.start_review()
    pump()
    reviewed = 0
    for w in mk.findChildren(QuestionWidget):
        if not w.done:
            answer(w)
            reviewed += 1
    results["mistakes_reviewed"] = reviewed
    results["mistakes_still_open"] = len(ctx.db.mistakes())
    results["mistakes_due_after"] = len(ctx.db.due_reviews())

    # Simulation: move the sliders, then group analysis.
    win.navigate("simulation")
    sim = win.pages["simulation"]
    sim.occ_s.setValue(-4)
    sim.adr_s.setValue(-3)
    sim.recalc()
    results["sim_tile"] = sim.tiles["rev"].value.text()
    sim.occ_s.setValue(0)
    sim.adr_s.setValue(0)
    sim.recalc()
    sim.recalc_group()

    # Exports through the export center with the save dialog answered.
    ex = win.pages["export"]
    win.navigate("export")
    ex.rec.setPlainText("Forecast room revenue is slightly above budget; protect winter rate.")
    targets = {}

    def fake_ask(title, name, filt):
        p = out_dir / name
        targets[title] = p
        return p
    ex._ask = fake_ask
    ex.export_model_xlsx()
    ex.export_lab_xlsx()
    ex.export_project_pdf()
    ex.export_competency_pdf()
    ex.export_progress()
    results["exports"] = {t: (p.exists() and p.stat().st_size > 0) for t, p in targets.items()}
    for key in win.pages:
        win.navigate(key)
        pump(1)
        if shots:
            win.grab().save(str(out_dir / f"after_{key}.png"))
    from finpilot.curriculum import progression as prog
    results["badges"] = ctx.db.badges()
    results["competency"] = {c.skill_id: c.status for c in prog.competencies(ctx.cur, ctx.db)}
    results["overall"] = prog.overall_progress(ctx.cur, ctx.db)
    return results


if __name__ == "__main__":
    import os
    import sys
    import pprint
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: print("WARNING:", a[1:3]) or QMessageBox.Ok)
    from finpilot.app import create_app
    app, ctx, win = create_app([])
    win.resize(1360, 860)
    win.show()
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pprint.pprint(run_all(win, out, shots=True))
