"""Welcome and onboarding (first run)."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ... import __descriptor__, __tagline__
from ..context import AppContext
from ..logo import logo_pixmap
from ..widgets import Card, ChipGroup, button, hbox, label


class OnboardingPage(QWidget):
    def __init__(self, ctx: AppContext, on_done):
        super().__init__()
        self.setObjectName("Page")
        self.ctx = ctx
        self.on_done = on_done
        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 40, 60, 40)
        outer.addStretch(1)
        hero = Card("Hero", 40, 14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96, background=False))
        hero.add(hbox(logo, "stretch"))
        t = label("FinPilot", "H1")
        t.setStyleSheet("font-size: 34pt; color: #59D6C0;")
        hero.add(t, label(__tagline__, "H2"), label(__descriptor__, "Muted"))
        hero.add(label("Build real models step by step: from profit versus cash to a working 12-month hotel revenue "
                       "forecast. Short lessons, immediate feedback, models checked with changed inputs, and "
                       "professional Excel and PDF exports. Everything works offline.", "Body"))
        outer.addWidget(hero)
        form = Card("Card", 28, 12)
        form.add(label("Set up your academy", "H2"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Your first name (optional, shown on reports)")
        form.add(label("What should FinPilot call you?", "H3"), self.name)
        form.add(label("How much guidance would you like?", "H3"))
        self.mode = ChipGroup([("guided", "Guided"), ("practice", "Practice"), ("challenge", "Challenge")], "guided")
        form.add(self.mode, label("In every mode you try first: hints and worked solutions unlock after an attempt. "
                                  "Guided unlocks them soonest. You can change this any time, per lesson.",
                                  "Muted"))
        self.theme = ChipGroup([("light", "Light theme"), ("dark", "Dark theme")], "light")
        self.theme.changed.connect(lambda t: ctx.signals.theme_changed.emit(t))
        form.add(label("Appearance", "H3"), self.theme)
        self.gam = QCheckBox("Show XP and achievements (rewards correct reasoning and validated models only)")
        self.gam.setChecked(True)
        form.add(self.gam)
        form.add(hbox(button("Start learning →", "Primary", self.finish),
                      label("No account, no internet, no telemetry.", "Muted", wrap=False), stretch_end=True))
        outer.addWidget(form)
        outer.addStretch(1)

    def finish(self):
        db = self.ctx.db
        db.set_setting("learner_name", self.name.text().strip())
        db.set_setting("practice_mode", self.mode.value)
        db.set_setting("theme", self.theme.value)
        db.set_setting("gamification", self.gam.isChecked())
        db.set_setting("onboarded", True)
        self.on_done()
