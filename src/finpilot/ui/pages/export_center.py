"""Excel / PDF export center."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QPlainTextEdit

from ...config import projects_dir
from ...core import hotel_sheet as hs
from ...curriculum import progression as prog
from ...curriculum.hotel_project import assumptions_from_sheet, independent_verification
from ...export import excel, pdf
from ..context import AppContext
from ..widgets import Card, Page, button, hbox, label


class ExportPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Export center", "Professional deliverables: Excel workbooks with live formulas and "
                         "management-ready PDF reports.", "Export")
        self.ctx = ctx
        c = Card()
        c.add(label("Management recommendation (optional)", "H3"),
              label("Included in the Excel workbook and the PDF report. Write it in your own words.", "Muted"))
        self.rec = QPlainTextEdit()
        self.rec.setPlaceholderText("e.g. The forecast is 0.7% above budget overall, but winter months are weak…")
        self.rec.setMinimumHeight(110)
        self.rec.textChanged.connect(self._save_rec)
        c.add(self.rec)
        self.add(c)
        items = [
            ("Hotel model workbook (.xlsx)", "Model sheet with every formula, budget-vs-forecast scenarios, revenue "
             "bridge, charts, checks and notes.", self.export_model_xlsx),
            ("Lab sheet only (.xlsx)", "The current Modeling Lab sheet exactly as built, with formulas.",
             self.export_lab_xlsx),
            ("Project report (.pdf)", "KPIs, chart, monthly detail with volume/rate bridge, model checks, "
             "assumptions and your recommendation.", self.export_project_pdf),
            ("Competency report (.pdf)", "Demonstrated skills, areas to practise, assessment results, model "
             "validation and next steps.", self.export_competency_pdf),
            ("Progress data (.csv / .json)", "Your lesson progress and assessment history for your own records.",
             self.export_progress),
        ]
        for title, desc, fn in items:
            card = Card("Card", 16, 4)
            card.add(hbox(label(title, "H3", wrap=False), "stretch", button("Export…", "Primary", fn)),
                     label(desc, "Muted"))
            self.add(card)
        self.add(label("About Excel recalculation: exported workbooks contain real Excel formulas and are set to "
                       "recalculate fully when opened. FinPilot itself does not run Microsoft Excel. FinPilot's own "
                       "test suite verifies the exported formulas by re-reading them and recalculating them with "
                       "FinPilot's formula engine (and LibreOffice where available).", "Muted"))
        self.add("stretch")

    def refresh(self):
        p = self.ctx.project
        if p is not None:
            self.rec.blockSignals(True)
            self.rec.setPlainText(p.state.get("recommendation", ""))
            self.rec.blockSignals(False)

    def _save_rec(self):
        if self.ctx.project is not None:
            self.ctx.project.state["recommendation"] = self.rec.toPlainText()
            self.ctx.project_dirty = True

    def _ask(self, title, name, filt):
        path, _ = QFileDialog.getSaveFileName(self, title, str(projects_dir() / name), filt)
        return Path(path) if path else None

    def _project(self):
        if self.ctx.project is None:
            from ...data.projects import new_hotel_project
            self.ctx.project = new_hotel_project()
        return self.ctx.project

    def _sync(self):
        p = self._project()
        if p.kind == "hotel_model":
            try:
                lab = assumptions_from_sheet(p.sheet)
                p.forecast.rooms, p.forecast.year, p.forecast.months = lab.rooms, lab.year, lab.months
            except ValueError:
                pass
        return p

    def _done(self, path: Path):
        self.ctx.notify(f"Exported {path.name}")
        QMessageBox.information(self, "Export complete", f"Saved:\n{path}")

    def export_model_xlsx(self):
        p = self._sync()
        if p.kind != "hotel_model":
            QMessageBox.information(self, "Not a hotel model", "Open or create a hotel model in the Lab first, or "
                                    "use 'Lab sheet only'.")
            return
        built = sum(1 for c in hs.MONTH_COLS if p.sheet.raw(f"{c}{hs.R_RREV}").startswith("="))
        if built < 12 and QMessageBox.question(
                self, "Model not finished", "Some calculation rows in your Lab model are not built yet, so the Model "
                "sheet will be incomplete. The Scenarios and Bridge sheets are always complete. Export anyway?") \
                != QMessageBox.Yes:
            return
        path = self._ask("Export hotel model", f"{p.name}.xlsx", "Excel workbook (*.xlsx)")
        if path:
            excel.export_hotel_model(path, p.sheet, p.forecast, p.budget, p.name, p.state.get("recommendation", ""))
            self._done(path)

    def export_lab_xlsx(self):
        p = self._project()
        path = self._ask("Export Lab sheet", f"{p.name} - sheet.xlsx", "Excel workbook (*.xlsx)")
        if path:
            excel.export_lab_sheet(path, p.sheet, p.name)
            self._done(path)

    def export_project_pdf(self):
        p = self._sync()
        path = self._ask("Export project report", f"{p.name}.pdf", "PDF (*.pdf)")
        if path:
            checks = None
            if p.kind == "hotel_model" and p.state.get("guided"):
                ver = independent_verification(p.sheet)
                checks = [(n, "pass" if ok else "fail", m) for n, ok, m in ver]
            pdf.project_report_pdf(path, p.name, p.forecast, p.budget, p.state.get("recommendation", ""), checks)
            self._done(path)

    def export_competency_pdf(self):
        path = self._ask("Export competency report", "FinPilot competency report.pdf", "PDF (*.pdf)")
        if path:
            pdf.competency_report_pdf(path, prog.competency_report(self.ctx.cur, self.ctx.db))
            self._done(path)

    def export_progress(self):
        path = self._ask("Export progress", "FinPilot progress.csv", "CSV (*.csv);;JSON (*.json)")
        if not path:
            return
        db = self.ctx.db
        rows = []
        for l in self.ctx.cur.lessons:
            pr = db.lesson_progress(l.id) or {}
            rows.append({"lesson_id": l.id, "title": l.title, "level": l.level, "status": pr.get("status", "not started"),
                         "best_score": pr.get("best_score"), "completed_at": pr.get("completed_at")})
        if path.suffix.lower() == ".json":
            path.write_text(json.dumps({"lessons": rows, "assessments": db.assessments(), "xp": db.total_xp(),
                                        "badges": db.badges()}, indent=1, default=str), encoding="utf-8")
        else:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        self._done(path)
