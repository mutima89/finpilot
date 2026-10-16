"""FinPilot application entry point."""
from __future__ import annotations

import logging
import sys
import traceback

log = logging.getLogger("finpilot")


def _excepthook(exc_type, exc, tb):
    """Log unexpected errors and tell the learner, instead of silently dying."""
    log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            from .config import data_dir
            QMessageBox.warning(None, "Something went wrong",
                                f"FinPilot hit an unexpected error: {exc}\n\nYour progress is saved after every "
                                f"step. Details were written to the log in:\n{data_dir() / 'logs'}")
    except Exception:
        pass


def create_app(argv=None):
    """Build the QApplication, context and main window (used by main() and the tests)."""
    from PySide6.QtWidgets import QApplication

    from . import __app_name__
    from .ui.context import AppContext
    from .ui.logo import app_icon
    from .ui.main_window import MainWindow
    from .ui.theme import font_family, set_theme, stylesheet

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setWindowIcon(app_icon())
    f = app.font()
    f.setFamily(font_family())
    f.setPointSize(10)
    app.setFont(f)
    ctx = AppContext()
    set_theme(ctx.setting("theme") or "light")
    app.setStyleSheet(stylesheet())
    win = MainWindow(ctx)
    return app, ctx, win


def self_test(out_dir=None) -> int:
    """Headless check used by the build script on the packaged app.

    Builds every screen, loads the curriculum, builds and validates the reference
    hotel model, and writes an Excel workbook and a PDF. Prints a report; exit
    code 0 means every check passed.
    """
    import tempfile
    from pathlib import Path

    results = []

    def check(name, fn):
        try:
            ok, info = fn()
        except Exception as e:  # report, never crash
            ok, info = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, info))

    out = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="finpilot-selftest-"))
    out.mkdir(parents=True, exist_ok=True)
    app, ctx, win = create_app([sys.argv[0]])
    win.resize(1280, 800)

    def screens():
        if getattr(win, "onboarding", None) is not None:
            win.stack.setCurrentWidget(win.pages["home"])
        for key in win.pages:
            win.navigate(key)
            app.processEvents()
        return True, f"{len(win.pages)} screens built"

    def curriculum():
        from .curriculum import validate
        problems = validate(ctx.cur)
        return not problems, f"{len(ctx.cur.lessons)} lessons, problems: {len(problems)}"

    def model():
        from .core import hotel as H, hotel_sheet as hs
        from .curriculum.hotel_project import project_status
        sheet = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
        st = project_status(sheet)
        total = round(sheet.value(f"{hs.TOT}{hs.R_RREV}"))
        return st["validated"] and total == 17_484_066, f"validated={st['validated']}, room revenue {total:,}"

    def excel_export():
        from .core import hotel as H, hotel_sheet as hs
        from .export import excel
        sheet = hs.build_sheet(H.default_forecast(), H.default_budget(), include_calcs=True)
        p = excel.export_hotel_model(out / "selftest.xlsx", sheet, H.default_forecast(), H.default_budget())
        back = excel.read_back_sheet(p, "Model")
        v = round(back.value(f"{hs.TOT}{hs.R_RREV}"))
        return v == 17_484_066, f"{p} re-read total {v:,}"

    def pdf_export():
        from .core import hotel as H
        from .export import pdf
        p = pdf.project_report_pdf(out / "selftest.pdf", "Self-test", H.default_forecast(), H.default_budget(), "", None)
        return p.read_bytes()[:4] == b"%PDF", str(p)

    for name, fn in (("screens", screens), ("curriculum", curriculum), ("hotel model", model),
                     ("excel export", excel_export), ("pdf export", pdf_export)):
        check(name, fn)
    lines = [f"[{'PASS' if ok else 'FAIL'}] {name}: {info}" for name, ok, info in results]
    # A windowed .exe has no console, so the report is also written to a file.
    (out / "selftest-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print("\n".join(lines))
    ctx.project_dirty = False
    win.close()
    return 0 if all(ok for _, ok, _ in results) else 1


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--self-test" in argv:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if "FINPILOT_HOME" not in os.environ:
            import tempfile
            os.environ["FINPILOT_HOME"] = tempfile.mkdtemp(prefix="finpilot-home-")
        i = argv.index("--self-test")
        out = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else None
        return self_test(out)
    from .config import setup_logging
    log_file = setup_logging()
    sys.excepthook = _excepthook
    log.info("Starting FinPilot; log at %s", log_file)
    app, ctx, win = create_app(argv)
    win.resize(1360, 860)
    win.show()
    if ctx.db.recovered_from is not None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(win, "Progress database was damaged",
                            "FinPilot found a damaged progress database and started a fresh one. The damaged file "
                            f"was kept as:\n{ctx.db.recovered_from}\n\nYou can restore an earlier backup from "
                            "Settings → Data management.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
