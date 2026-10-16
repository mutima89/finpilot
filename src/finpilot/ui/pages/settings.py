"""Settings and data management."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QLineEdit, QMessageBox, QSpinBox)

from ... import __app_name__, __tagline__, __version__
from ...config import backups_dir, data_dir, projects_dir
from ..context import AppContext
from ..widgets import Card, Page, button, hbox, label


class SettingsPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Settings & data", "Everything is stored on this computer. FinPilot collects no telemetry "
                         "and needs no internet connection or account.", "Settings")
        self.ctx = ctx
        prefs = Card()
        prefs.add(label("Preferences", "H3"))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.editingFinished.connect(lambda: self._set("learner_name", self.name.text().strip()))
        self.theme = QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.activated.connect(self._theme)
        self.mode = QComboBox()
        for k, t in (("guided", "Guided: hints and solution after 1 attempt"),
                     ("practice", "Practice: hints after 1 attempt, solution after 2"),
                     ("challenge", "Challenge: hints after 2 attempts, solution after 3")):
            self.mode.addItem(t, k)
        self.mode.activated.connect(lambda: self._set("practice_mode", self.mode.currentData()))
        self.gam = QCheckBox("Show XP, levels and achievement badges")
        self.gam.toggled.connect(lambda v: self._set("gamification", v, refresh=True))
        self.goal = QSpinBox()
        self.goal.setRange(0, 500)
        self.goal.setSingleStep(10)
        self.goal.setSuffix(" XP per day (0 = off)")
        self.goal.valueChanged.connect(lambda v: self._set("daily_goal_xp", v))
        self.unlock = QCheckBox("Unlock all lessons (explore freely; prerequisites become recommendations)")
        self.unlock.toggled.connect(lambda v: self._set("unlock_all", v, refresh=True))
        self.autosave = QCheckBox("Autosave the open model to a recovery file every few seconds")
        self.autosave.toggled.connect(lambda v: self._set("autosave", v))
        form.addRow("Your name", self.name)
        form.addRow("Theme", self.theme)
        form.addRow("Default practice mode", self.mode)
        form.addRow("Gamification", self.gam)
        form.addRow("Daily practice goal", self.goal)
        form.addRow("Learning path", self.unlock)
        form.addRow("Recovery", self.autosave)
        prefs.add(form)
        prefs.add(label("No streaks, no timers and no notifications: a missed day is never penalised.", "Muted"))
        self.add(prefs)

        data = Card()
        data.add(label("Data management", "H3"))
        data.add(label(f"Data folder: {data_dir()}", "Muted"), label(f"Projects folder: {projects_dir()}", "Muted"))
        data.add(hbox(button("Back up now", "Primary", self.backup), button("Restore from backup…", "", self.restore),
                      button("Check data integrity", "", self.integrity), button("Open data folder", "Ghost",
                                                                                 lambda: _open(data_dir())),
                      stretch_end=True))
        data.add(hbox(button("Reset all progress…", "Danger", self.reset_all), stretch_end=True))
        self.add(data)

        about = Card()
        about.add(label("About", "H3"),
                  label(f"{__app_name__} {__version__} · {__tagline__}<br>Interactive Financial Modeling Academy. "
                        "All companies, hotels and figures in FinPilot are fictional and for training only. Model "
                        "outputs are estimates based on stated assumptions, not forecasts of real results or "
                        "investment advice.", "Body", rich=True))
        self.add(about)
        self.add("stretch")

    def refresh(self):
        s = self.ctx.db.settings()
        for w in (self.name, self.theme, self.mode, self.gam, self.goal, self.unlock, self.autosave):
            w.blockSignals(True)
        self.name.setText(s["learner_name"])
        self.theme.setCurrentIndex(max(0, self.theme.findData(s["theme"])))
        self.mode.setCurrentIndex(max(0, self.mode.findData(s["practice_mode"])))
        self.gam.setChecked(bool(s["gamification"]))
        self.goal.setValue(int(s["daily_goal_xp"] or 0))
        self.unlock.setChecked(bool(s["unlock_all"]))
        self.autosave.setChecked(bool(s["autosave"]))
        for w in (self.name, self.theme, self.mode, self.gam, self.goal, self.unlock, self.autosave):
            w.blockSignals(False)

    def _set(self, key, value, refresh=False):
        self.ctx.set_setting(key, value)
        if refresh:
            self.ctx.signals.progress_changed.emit()

    def _theme(self):
        t = self.theme.currentData()
        self.ctx.set_setting("theme", t)
        self.ctx.signals.theme_changed.emit(t)

    def backup(self):
        extra = list(projects_dir().glob("*.finpilot"))
        path = self.ctx.db.backup(extra_files=extra)
        QMessageBox.information(self, "Backup created", f"Backup saved to:\n{path}\n\nIt contains your progress "
                                f"database and {len(extra)} project file(s).")

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restore FinPilot backup", str(backups_dir()), "Backups (*.zip)")
        if not path:
            return
        if QMessageBox.question(self, "Restore backup?", "This replaces your current progress with the backup. "
                                "Your current data is backed up first, so you can undo this. Continue?") \
                != QMessageBox.Yes:
            return
        try:
            restored = self.ctx.db.restore(Path(path))
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Restore failed", str(e))
            return
        QMessageBox.information(self, "Restored", "Progress restored." + (
            f" Project files restored: {', '.join(restored)}." if restored else ""))
        self.refresh()
        self.ctx.signals.progress_changed.emit()

    def integrity(self):
        ok = self.ctx.db.integrity_ok()
        QMessageBox.information(self, "Data integrity", "The progress database passed SQLite's integrity check."
                                if ok else "The database reported a problem. Restore a backup from Settings.")

    def reset_all(self):
        if QMessageBox.warning(self, "Reset all progress?", "This erases lessons, assessments, XP, badges, "
                               "bookmarks, mistakes and settings. A backup is made first. Project files are not "
                               "deleted. Continue?", QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
            return
        b = self.ctx.db.reset_all()
        QMessageBox.information(self, "Progress reset", f"Done. A backup was saved to:\n{b}")
        self.refresh()
        self.ctx.signals.progress_changed.emit()


def _open(path: Path):
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass
