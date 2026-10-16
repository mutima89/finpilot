"""Progress & competency dashboard."""
from __future__ import annotations

import html

from PySide6.QtWidgets import QFileDialog, QGridLayout, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout

from ...config import projects_dir
from ...curriculum import progression as prog
from ...export.pdf import STATUS_LABEL, competency_report_pdf
from ..context import AppContext
from ..theme import palette
from ..widgets import Card, Page, ProgressRing, StatTile, button, clear_layout, hbox, label


class ProgressPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Progress & competency", "What you have demonstrated, where to practise, and the "
                         "evidence behind each rating.", "Progress")
        self.ctx = ctx
        self.content = QVBoxLayout()
        self.content.setSpacing(14)
        self.add(self.content)
        self.add("stretch")
        ctx.signals.progress_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        clear_layout(self.content)
        cur, db = self.ctx.cur, self.ctx.db
        rep = prog.competency_report(cur, db)
        top = QGridLayout()
        ring = ProgressRing(110)
        ring.set(prog.overall_progress(cur, db), sub="V1 path")
        rc = Card()
        rc.add(label("Curriculum progress", "H3"), ring)
        comps = rep["demonstrated"] + rep["developing"] + rep["needs_practice"] + rep["not_assessed"]
        t1 = StatTile("Skills demonstrated", f"{len(rep['demonstrated'])}/{len(comps)}",
                      f"{len(rep['needs_practice'])} need practice")
        finals = rep["assessments"]
        t2 = StatTile("Final assessment", f"{finals[-1]['score']:.0%}" if finals else "—",
                      ("passed" if finals[-1]["passed"] else "not yet passed") if finals else "not attempted")
        t3 = StatTile("Hotel model", "Validated" if rep["model_validated"] else "Not yet",
                      "independent check" if rep["model_validated"] else "build it in the Lab")
        tiles = [t1, t2, t3]
        if self.ctx.gamification:
            lvl, into, need = prog.skill_level(rep["xp"])
            tiles.append(StatTile("Experience", f"{rep['xp']} XP", f"XP rank {lvl} · {need - into} XP to next rank"))
        top.addWidget(rc, 0, 0, 2, 1)
        for i, t in enumerate(tiles):
            top.addWidget(t, i // 2, 1 + i % 2)
        top.setColumnStretch(1, 1)
        top.setColumnStretch(2, 1)
        self.content.addLayout(top)

        sk = Card()
        sk.add(hbox(label("Competencies", "H3"), "stretch",
                    button("Export competency report (PDF)", "Primary", self.export_pdf)))
        tbl = QTableWidget(len(comps), 5)
        tbl.setHorizontalHeaderLabels(["Skill", "Area", "Status", "Score", "Note"])
        tbl.verticalHeader().hide()
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        p = palette()
        colors = {"demonstrated": p.success, "developing": p.amber, "needs_practice": p.coral,
                  "not_assessed": p.muted}
        from PySide6.QtGui import QBrush, QColor
        for r, c in enumerate(comps):
            vals = [c.name, c.area, STATUS_LABEL[c.status], "" if c.score is None else f"{c.score:.0%}", c.note]
            for k, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if k == 2:
                    it.setForeground(QBrush(QColor(colors[c.status])))
                tbl.setItem(r, k, it)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setMinimumHeight(30 + 30 * len(comps))
        sk.add(tbl)
        sk.add(label(" ".join(rep["criteria"]), "Muted"))
        self.content.addWidget(sk)

        if self.ctx.gamification:
            b = Card()
            b.add(label("Achievements", "H3"))
            earned = db.badges()
            g = QGridLayout()
            for i, (bid, (name, desc)) in enumerate(prog.BADGES.items()):
                got = bid in earned
                g.addWidget(label(f"{'🏅' if got else '○'} <b>{html.escape(name)}</b><br>"
                                  f"<span style='color:{p.muted}'>{html.escape(desc)}</span>", "Body", rich=True),
                            i // 3, i % 3)
            b.add(g)
            self.content.addWidget(b)

        nx = Card()
        rec = rep["next_step"]
        nx.add(label("Recommended next steps", "H3"), label(f"<b>{html.escape(rec.title)}</b>: "
                                                             f"{html.escape(rec.reason)}", "Body", rich=True))
        for c in rep["needs_practice"][:4]:
            nx.add(label(f"• Practise {html.escape(c.name)}", "Body"))
        if rep["outstanding"]:
            nx.add(label("Outstanding: " + ", ".join(html.escape(t) for t in rep["outstanding"][:8]) +
                         (" …" if len(rep["outstanding"]) > 8 else ""), "Muted"))
        nx.add(hbox(button("Go →", "Primary", lambda: self.ctx.navigate(rec.kind, rec.ref)), stretch_end=True))
        self.content.addWidget(nx)

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save competency report",
                                              str(projects_dir() / "FinPilot competency report.pdf"), "PDF (*.pdf)")
        if not path:
            return
        competency_report_pdf(path, prog.competency_report(self.ctx.cur, self.ctx.db))
        self.ctx.notify(f"Saved {path}")
