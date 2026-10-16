"""Home: continue learning, progress at a glance, review, projects."""
from __future__ import annotations

import html

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...curriculum import progression as prog
from ..context import AppContext
from ..logo import logo_pixmap
from ..widgets import Card, FlowLayout, Page, ProgressRing, button, clear_layout, hbox, label, vbox


class HomePage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Welcome back", "", "Home")
        self.ctx = ctx
        self.content = QVBoxLayout()
        self.content.setSpacing(16)
        self.add(self.content)
        self.add("stretch")
        ctx.signals.progress_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        clear_layout(self.content)
        ctx, cur, db = self.ctx, self.ctx.cur, self.ctx.db
        name = db.get_setting("learner_name")
        self.title.setText(f"Welcome back, {name}" if name else "Welcome to FinPilot")
        rec = prog.next_recommendation(cur, db)
        level = prog.current_level(cur, db)
        lv = cur.level(level)
        overall = prog.overall_progress(cur, db)

        hero = Card("Hero", 26, 10)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(56, background=False))
        top.addWidget(logo)
        top.addLayout(vbox(label("CONTINUE LEARNING", "Eyebrow"), label(rec.title, "H1"),
                           label(rec.reason, "Muted")), 1)
        ring = ProgressRing(104)
        ring.on_dark = True
        ring.set(overall, sub="of V1 path")
        top.addWidget(ring)
        hero.add(top)
        hero.add(hbox(button("Continue →", "Primary", lambda: ctx.navigate(rec.kind, rec.ref)),
                      label(f"Current level: {level} · {lv.title}", "Muted", wrap=False), stretch_end=True))
        self.content.addWidget(hero)

        row = QGridLayout()
        row.setSpacing(14)
        # skills
        comps = prog.competencies(cur, db)
        dem = [c for c in comps if c.status == "demonstrated"]
        dev = [c for c in comps if c.status in ("developing", "needs_practice")]
        sk = Card()
        sk.add(label("Skills", "H3"))
        sk.add(label(f"<b>{len(dem)}</b> of {len(comps)} skills demonstrated", "Body", rich=True))
        for c in dem[:4]:
            sk.add(label(f"✓ {html.escape(c.name)}", "Body", rich=True))
        if not dem:
            sk.add(label("Skills are demonstrated through correct answers and validated models, not by "
                         "finishing screens.", "Muted"))
        sk.add(button("Competency dashboard →", "Ghost", lambda: ctx.navigate("progress")))
        sk.add("stretch")
        row.addWidget(sk, 0, 0)

        # review
        due = db.due_reviews()
        rv = Card()
        rv.add(label("Recommended review", "H3"))
        if due:
            rv.add(label(f"{len(due)} concept{'s' if len(due) != 1 else ''} due for spaced review.", "Body"))
            for m in due[:3]:
                rv.add(label("• " + html.escape(m["question"][:90]), "Muted"))
            rv.add(button("Review now →", "Ghost", lambda: ctx.navigate("mistakes")))
        elif dev:
            rv.add(label("Strengthen these skills:", "Body"))
            for c in dev[:3]:
                rv.add(label(f"• {html.escape(c.name)} ({c.score:.0%})" if c.score is not None else
                             f"• {html.escape(c.name)}", "Muted"))
            rv.add(button("Formula practice →", "Ghost", lambda: ctx.navigate("practice")))
        else:
            rv.add(label("Nothing due. Mistakes you make are scheduled here for review at growing intervals "
                         "(1, 3, 7, 14, 30 days).", "Muted"))
        rv.add("stretch")
        row.addWidget(rv, 0, 1)

        # projects
        pr = Card()
        pr.add(label("Active projects", "H3"))
        projects = db.projects()[:3]
        if ctx.project is not None:
            st = ctx.project.state.get("tasks_done", [])
            pr.add(label(f"<b>{html.escape(ctx.project.name)}</b> (open in Lab) · {len(st)}/10 build tasks",
                         "Body", rich=True))
        for p in projects:
            pr.add(label(f"{html.escape(p['name'])} · {p['progress']:.0%}" + (" · validated ✓" if p["validated"] else ""),
                         "Muted"))
        if ctx.project is None and not projects:
            pr.add(label("No projects yet. Start the guided hotel model in the Modeling Lab.", "Muted"))
        pr.add(hbox(button("Modeling Lab →", "Ghost", lambda: ctx.navigate("lab")),
                    button("Portfolio →", "Ghost", lambda: ctx.navigate("portfolio")), stretch_end=True))
        pr.add("stretch")
        row.addWidget(pr, 0, 2)
        self.content.addLayout(row)

        # achievements (optional)
        if ctx.gamification:
            badges = db.badges()
            xp = db.total_xp()
            lvl, into, need = prog.skill_level(xp)
            ach = Card()
            goal = db.get_setting("daily_goal_xp") or 0
            goal_txt = f" · today {db.xp_today()}/{goal} XP (optional goal)" if goal else ""
            ach.add(hbox(label("Recent achievements", "H3"), "stretch",
                         label(f"XP rank {lvl} · {xp} XP{goal_txt}", "Muted", wrap=False)))
            if badges:
                recent = list(badges.items())[-4:]
                ach.add(label("   ".join(f"🏅 {prog.BADGES[b][0]}" for b, _ in recent if b in prog.BADGES),
                              "Body"))
            else:
                ach.add(label("Badges reward demonstrated skill: a first linked formula, a validated model, a "
                              "passed assessment. You can turn gamification off in Settings.", "Muted"))
            self.content.addWidget(ach)

        # level strip
        strip = Card()
        strip.add(label("Your path", "H3"))
        g = FlowLayout(spacing=8)
        progress = db.all_progress()
        for lvx in cur.levels:
            total = len(lvx.lessons)
            done = sum(1 for l in lvx.lessons if progress.get(l.id, {}).get("status") == "completed")
            state = ("planned" if lvx.status == "planned" else "preview" if lvx.status == "preview"
                     else f"{done}/{total}")
            b = button(f"L{lvx.number}\n{state}", "Chip" if lvx.number != level else "Primary",
                       lambda _=False: ctx.navigate("map"))
            b.setToolTip(lvx.title)
            b.setFixedSize(84, 46)
            g.addWidget(b)
        holder = QWidget()
        holder.setLayout(g)
        strip.add(holder)
        strip.add(label("Levels 1-3 are complete courses in V1. Level 4 includes the group displacement simulator "
                        "as a preview; Levels 5-10 are planned for later releases.", "Muted"))
        self.content.addWidget(strip)
