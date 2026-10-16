"""Project portfolio: saved models and their validation state."""
from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QVBoxLayout

from ...config import projects_dir
from ..context import AppContext
from ..widgets import Card, Page, button, clear_layout, hbox, label


class PortfolioPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Project portfolio", "Your saved models. Validated models are evidence you can discuss in "
                         "interviews: export them as Excel workbooks with live formulas and PDF reports.", "Portfolio")
        self.ctx = ctx
        self.content = QVBoxLayout()
        self.content.setSpacing(12)
        self.add(self.content)
        self.add("stretch")
        ctx.signals.progress_changed.connect(self.refresh)
        ctx.signals.project_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        clear_layout(self.content)
        self.content.addLayout(hbox(button("New guided hotel model", "Primary", self._new),
                                    button("Open a project file…", "", self._open),
                                    stretch_end=True))
        self.content.addWidget(label(f"Default folder: {html.escape(str(projects_dir()))}", "Muted"))
        projects = self.ctx.db.projects()
        if self.ctx.project is not None:
            p = self.ctx.project
            c = Card()
            done = len(p.state.get("tasks_done", []))
            c.add(label("OPEN IN THE LAB", "Eyebrow"), label(p.name, "H3"),
                  label(f"{done}/10 guided tasks · {'validated ✓' if p.state.get('validated') else 'not validated yet'}"
                        f" · {'saved as ' + p.path.name if p.path else 'not saved yet'}", "Muted"))
            c.add(hbox(button("Continue in Lab", "Primary", lambda: self.ctx.navigate("lab")),
                       button("Export…", "", lambda: self.ctx.navigate("export")), stretch_end=True))
            self.content.addWidget(c)
        for pr in projects:
            path = Path(pr["path"])
            exists = path.exists()
            c = Card("Card", 16, 4)
            c.add(label(html.escape(pr["name"]), "H3"))
            c.add(label(f"{pr['kind'].replace('_', ' ')} · progress {pr['progress']:.0%} · "
                        f"{'validated ✓' if pr['validated'] else 'not validated'} · saved {pr['updated_at'][:16]}"
                        + ("" if exists else " · file missing"), "Muted"))
            c.add(label(html.escape(str(path)), "Muted"))
            row = hbox(stretch_end=False)
            ob = button("Open", "Primary", lambda _=False, p=path: self._open_path(p))
            ob.setEnabled(exists)
            row.addWidget(ob)
            row.addWidget(button("Remove from list", "Ghost", lambda _=False, p=pr: self._forget(p)))
            row.addStretch(1)
            c.add(row)
            self.content.addWidget(c)
        if not projects and self.ctx.project is None:
            self.content.addWidget(label("No saved projects yet.", "Muted"))

    def _lab(self):
        return self.window().pages["lab"]

    def _new(self):
        self.ctx.navigate("lab")
        self._lab().new_guided()

    def _open(self):
        self.ctx.navigate("lab")
        self._lab().open_dialog()

    def _open_path(self, path):
        lab = self._lab()
        if lab._confirm_discard() and lab.open_path(path):
            self.ctx.navigate("lab")

    def _forget(self, pr):
        if QMessageBox.question(self, "Remove from portfolio?",
                                f"Remove '{pr['name']}' from this list? The file itself is not deleted.") == QMessageBox.Yes:
            self.ctx.db.forget_project(pr["path"])
            self.refresh()
