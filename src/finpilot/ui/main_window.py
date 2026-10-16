"""FinPilot main window: branded sidebar navigation and the screen stack."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import __app_name__, __tagline__, __version__
from .context import AppContext
from .logo import app_icon, logo_pixmap
from .theme import set_theme, stylesheet

log = logging.getLogger(__name__)

NAV = [
    ("home", "Home"),
    ("map", "Learning map"),
    ("lesson", "Lesson"),
    ("lab", "Modeling Lab"),
    ("simulation", "Simulation"),
    ("practice", "Practice"),
    ("challenge", "Final assessment"),
    ("mistakes", "Mistakes notebook"),
    ("progress", "Progress"),
    ("portfolio", "Portfolio"),
    ("export", "Export center"),
    ("settings", "Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.navigate = self.navigate
        self.setWindowTitle(__app_name__)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1000, 640)
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.current = "home"

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._menus()
        self.statusBar().showMessage(f"{__app_name__} {__version__} · fictional training data · works offline")

        ctx.signals.notify.connect(lambda t: self.statusBar().showMessage(t, 6000))
        ctx.signals.theme_changed.connect(self.apply_theme)
        ctx.signals.project_changed.connect(self._update_title)
        self._build_pages()

        if not ctx.setting("onboarded"):
            self._show_onboarding()
        else:
            self.navigate("home")

    # ------------------------------------------------------------ layout
    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 18, 14, 14)
        v.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(36))
        name = QLabel(__app_name__)
        name.setObjectName("Brand")
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch(1)
        v.addLayout(brand)
        tag = QLabel(__tagline__)
        tag.setObjectName("Tagline")
        tag.setWordWrap(True)
        v.addWidget(tag)
        v.addSpacing(16)
        for key, text in NAV:
            b = QPushButton(text)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.navigate(k))
            v.addWidget(b)
            self.nav_buttons[key] = b
        v.addStretch(1)
        foot = QLabel("All data is fictional\nand for training only.")
        foot.setObjectName("Tagline")
        v.addWidget(foot)
        self.sidebar = side
        return side

    def _build_pages(self):
        from .pages.challenge import ChallengePage
        from .pages.export_center import ExportPage
        from .pages.home import HomePage
        from .pages.lab import LabPage
        from .pages.learning_map import LearningMapPage
        from .pages.lesson import LessonPage
        from .pages.mistakes import MistakesPage
        from .pages.portfolio import PortfolioPage
        from .pages.practice import PracticePage
        from .pages.progress import ProgressPage
        from .pages.settings import SettingsPage
        from .pages.simulation import SimulationPage
        ctx = self.ctx
        # The Lab owns the open project, so it is built first.
        order = [("lab", LabPage), ("home", HomePage), ("map", LearningMapPage), ("lesson", LessonPage),
                 ("simulation", SimulationPage), ("practice", PracticePage), ("challenge", ChallengePage),
                 ("mistakes", MistakesPage), ("progress", ProgressPage), ("portfolio", PortfolioPage),
                 ("export", ExportPage), ("settings", SettingsPage)]
        for key, cls in order:
            page = cls(ctx)
            self.pages[key] = page
            self.stack.addWidget(page)
        self._update_title()

    def _menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "New guided hotel model", lambda: self._lab("new_guided"), QKeySequence.New)
        self._act(f, "Open project…", lambda: self._lab("open_dialog"), QKeySequence.Open)
        self._act(f, "Save project", lambda: self._lab("save"), QKeySequence.Save)
        self._act(f, "Save project as…", lambda: self._lab("save_as"), QKeySequence.SaveAs)
        f.addSeparator()
        self._act(f, "Export center", lambda: self.navigate("export"))
        f.addSeparator()
        self._act(f, "Exit", self.close, QKeySequence.Quit)
        g = mb.addMenu("&Go")
        for i, (key, text) in enumerate(NAV):
            self._act(g, text, lambda _=False, k=key: self.navigate(k), f"Ctrl+{i + 1}" if i < 9 else None)
        v = mb.addMenu("&View")
        self._act(v, "Light theme", lambda: self._set_theme("light"))
        self._act(v, "Dark theme", lambda: self._set_theme("dark"))
        h = mb.addMenu("&Help")
        self._act(h, "About FinPilot", self._about)

    def _act(self, menu, text, fn, shortcut=None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        return a

    # ------------------------------------------------------------ navigation
    def navigate(self, kind: str, ref: str | None = None):
        """Route a recommendation or a sidebar click to the right screen."""
        if self.stack.currentWidget() is getattr(self, "onboarding", None):
            return
        target = kind
        if kind == "lesson" and ref:
            self.pages["lesson"].open(ref)
        elif kind == "project":
            lesson = self.ctx.cur.lesson(ref) if ref else None
            if lesson is not None and lesson.kind != "lab_project":
                self.pages["lesson"].open(ref)
                target = "lesson"
            else:
                target = "lab"
        elif kind == "review":
            target = "mistakes"
        elif kind == "assessment":
            target = "challenge"
        if target not in self.pages:
            log.warning("Unknown navigation target %s", kind)
            target = "home"
        self.current = target
        page = self.pages[target]
        if hasattr(page, "refresh") and target != "lesson":
            try:
                page.refresh()
            except Exception:  # a broken refresh must not block navigation
                log.exception("Refresh failed for %s", target)
        self.stack.setCurrentWidget(page)
        for k, b in self.nav_buttons.items():
            b.setChecked(k == target)

    def _lab(self, method: str):
        self.navigate("lab")
        getattr(self.pages["lab"], method)()

    # ------------------------------------------------------------ onboarding / theme
    def _show_onboarding(self):
        from .pages.onboarding import OnboardingPage
        self.onboarding = OnboardingPage(self.ctx, self._onboarding_done)
        self.stack.addWidget(self.onboarding)
        self.stack.setCurrentWidget(self.onboarding)
        for b in self.nav_buttons.values():
            b.setEnabled(False)

    def _onboarding_done(self):
        for b in self.nav_buttons.values():
            b.setEnabled(True)
        ob = self.onboarding
        self.onboarding = None
        self.stack.removeWidget(ob)
        ob.deleteLater()
        self.ctx.signals.progress_changed.emit()
        self.navigate("home")
        name = self.ctx.setting("learner_name")
        self.ctx.notify(f"Welcome{', ' + name if name else ''}! Start with Level 1 on the learning map.")

    def _set_theme(self, name: str):
        self.ctx.set_setting("theme", name)
        self.ctx.signals.theme_changed.emit(name)

    def apply_theme(self, name: str):
        set_theme(name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet())
        # Pages that paint with palette colours rebuild on refresh.
        page = self.pages.get(self.current)
        if page is not None and hasattr(page, "refresh") and self.current != "lesson":
            try:
                page.refresh()
            except Exception:
                log.exception("Refresh after theme change failed")
        for p in self.pages.values():
            for ch in p.findChildren(QWidget):
                if hasattr(ch, "apply_theme"):
                    try:
                        ch.apply_theme()
                    except Exception:
                        log.exception("apply_theme failed")

    def _update_title(self):
        p = self.ctx.project
        self.setWindowTitle(f"{__app_name__} · {p.name}" if p is not None else __app_name__)

    def _about(self):
        QMessageBox.about(self, f"About {__app_name__}",
                          f"<b>{__app_name__} {__version__}</b><br>{__tagline__}<br><br>Interactive Financial "
                          "Modeling Academy. All companies, hotels and figures are fictional and for training "
                          "only. No account, internet connection or telemetry.")

    # ------------------------------------------------------------ close
    def closeEvent(self, event):
        lab = self.pages.get("lab")
        if lab is not None and self.ctx.project_dirty:
            if not lab._confirm_discard():
                event.ignore()
                return
        try:
            if lab is not None and hasattr(lab, "autosave"):
                lab.autosave()
        except Exception:
            log.exception("Final autosave failed")
        from PySide6.QtCore import QTimer
        for t in self.findChildren(QTimer):  # no deferred work may touch the database after it closes
            t.stop()
        self.ctx.db.close()
        event.accept()
