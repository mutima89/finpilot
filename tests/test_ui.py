"""UI tests with pytest-qt (offscreen): every screen at several window sizes, and a full learner journey."""
import pytest
from PySide6.QtWidgets import QMessageBox, QScrollArea


@pytest.fixture
def app_window(qtbot, monkeypatch):
    # Answer modal dialogs automatically so the tests never block.
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from finpilot.app import create_app
    app, ctx, win = create_app([])
    qtbot.addWidget(win)
    win.show()
    yield win
    ctx.project_dirty = False
    win.close()


def test_first_run_shows_onboarding_then_home(app_window):
    win = app_window
    assert win.onboarding is not None
    win.onboarding.name.setText("Alex")
    win.onboarding.mode.set_value("practice")
    win.onboarding.finish()
    assert win.ctx.setting("onboarded") is True
    assert win.ctx.setting("practice_mode") == "practice"
    assert win.stack.currentWidget() is win.pages["home"]
    assert win.windowTitle().startswith("FinPilot")


@pytest.mark.parametrize("size", [(1000, 640), (1024, 700), (1366, 768), (1920, 1080)])
def test_every_screen_renders_without_horizontal_overflow(app_window, qtbot, size):
    win = app_window
    win.onboarding.finish()
    win.resize(*size)
    qtbot.wait(20)
    for key, page in win.pages.items():
        win.navigate(key)
        qtbot.wait(5)
        assert win.stack.currentWidget() is page
        sa = page.findChild(QScrollArea, "PageScroll")
        inner = sa.widget() if sa else page
        assert inner.minimumSizeHint().width() <= win.stack.width(), \
            f"{key} overflows at {size}; widest parts: {_widest(inner)}"


def _widest(root, n=6):
    """Name the widgets with the largest minimum widths, to make an overflow failure actionable."""
    from PySide6.QtGui import QFontInfo
    from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget
    rows = []
    for w in root.findChildren(QWidget):
        if not w.isVisibleTo(root):
            continue
        mw = max(w.minimumSizeHint().width(), w.minimumWidth())
        text = w.text().replace("\n", " | ")[:60] if isinstance(w, (QLabel, QAbstractButton)) else ""
        rows.append((mw, type(w).__name__, w.objectName(), text))
    rows.sort(key=lambda r: -r[0])
    fi = QFontInfo(root.font())
    return f"font={fi.family()} {fi.pointSizeF()}pt/{fi.pixelSize()}px " + "; ".join(
        f"{mw}px {cls}#{name} '{text}'" for mw, cls, name, text in rows[:n])


def test_theme_switch(app_window):
    win = app_window
    win.onboarding.finish()
    win._set_theme("dark")
    assert win.ctx.setting("theme") == "dark"
    from finpilot.ui.theme import palette
    assert palette().name == "dark"
    win._set_theme("light")
    assert palette().name == "light"


def test_navigation_routes(app_window):
    win = app_window
    win.onboarding.finish()
    win.navigate("lesson", "L1.1")
    assert win.stack.currentWidget() is win.pages["lesson"]
    win.navigate("project", "P3")
    assert win.stack.currentWidget() is win.pages["lab"]
    win.navigate("review", "mistakes")
    assert win.stack.currentWidget() is win.pages["mistakes"]
    win.navigate("assessment", "final")
    assert win.stack.currentWidget() is win.pages["challenge"]
    win.navigate("nonsense")
    assert win.stack.currentWidget() is win.pages["home"]


def test_lab_error_values_are_explained(app_window):
    win = app_window
    win.onboarding.finish()
    win.navigate("lab")
    lab = win.pages["lab"]
    lab.view.sheet.set("B15", "=B4/0")
    lab.on_edit()
    assert "error" in lab.err_lbl.text().lower()


def test_full_learner_journey(app_window, tmp_path):
    """Complete every V1 lesson, build and validate the model, pass the assessment, review mistakes, export."""
    from ui_flow import run_all
    r = run_all(app_window, tmp_path)
    lessons = [k for k in r if k.startswith(("L", "P")) and k[1].isdigit()]
    assert len(lessons) == 19 and all(r[k] == "completed" for k in lessons)
    assert r["lab_validated"] and r["saved"] and r["reopened_tasks"] == 10
    assert r["final_passed"] and r["final_score"] == pytest.approx(1.0)
    assert r["mistakes_recorded"] >= 19 and r["mistakes_reviewed"] > 0
    assert r["sim_tile"] == "$16,101,064"
    assert r["exports"] and all(r["exports"].values())
    assert "model_builder" in r["badges"] and "certified_v1" in r["badges"]
    assert r["competency"]["hotel_model"] == "demonstrated"
    assert r["overall"] == pytest.approx(1.0)


@pytest.mark.parametrize("mode,hint_after,solution_after", [("guided", 1, 1), ("practice", 1, 2),
                                                            ("challenge", 2, 3)])
def test_hints_and_solutions_unlock_only_after_attempts(qtbot, mode, hint_after, solution_after):
    from finpilot.ui.questions import NumberQuestion
    q = {"question": "Occupancy?", "answer": 0.75, "fmt": "percent", "hints": ["Sold / available."],
         "solution": "75%"}
    w = NumberQuestion(q, mode)
    qtbot.addWidget(w)
    for attempt in range(4):
        assert w.hint_btn.isEnabled() == (attempt >= hint_after), (mode, attempt)
        assert w.solution_btn.isEnabled() == (attempt >= solution_after), (mode, attempt)
        w.reveal()                                   # ignored while locked
        assert w.revealed == (attempt >= solution_after), (mode, attempt)
        if w.revealed:
            break
        w.edit.setText("10%")
        w.check_btn.click()
