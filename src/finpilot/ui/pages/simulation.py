"""Hotel Simulation Center: budget vs forecast scenarios and group displacement."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDoubleSpinBox, QFormLayout, QGridLayout, QHeaderView, QSlider, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
                               QAbstractItemView)

from ...core import hotel as H
from ...core import hotel_sheet as hs
from ...core.format import fmt_opt, format_value
from ...core.revenue_mgmt import GroupInputs, analyse, validate_inputs
from ...curriculum.hotel_project import assumptions_from_sheet
from ..charts import Chart
from ..context import AppContext
from ..theme import palette
from ..widgets import Card, ChipGroup, Page, StatTile, button, clear_layout, hbox, label

ROWS = [("occupancy", "Occupancy", "percent"), ("adr", "ADR ($)", "currency"),
        ("fb_per_occupied_room", "F&B per occupied room ($)", "currency"),
        ("other_pct", "Other revenue (% of rooms)", "percent")]


def _slider(lo, hi, value):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    return s


class SimulationPage(Page):
    def __init__(self, ctx: AppContext):
        super().__init__("Hotel Simulation Center", "Change the drivers and see the financial consequences. "
                         "All data is fictional. Outputs are model estimates, not guarantees.", "Simulate")
        self.ctx = ctx
        tabs = QTabWidget()
        tabs.addTab(self._scenario_tab(), "Budget vs forecast")
        tabs.addTab(self._group_tab(), "Group vs transient (Level 4 preview)")
        self.add(tabs)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.recalc)

    # ======================================================== scenarios tab
    def _scenario_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(14)
        self.edit_which = ChipGroup([("forecast", "Edit forecast"), ("budget", "Edit budget")], "forecast")
        self.edit_which.changed.connect(lambda _: self.load_table())
        self.rooms = QSpinBox()
        self.rooms.setRange(0, 2000)
        self.rooms.setMinimumWidth(90)
        self.rooms.valueChanged.connect(self._rooms_changed)
        sync = button("Reload from Lab model", "Ghost", self.reload_from_lab,
                      "Use the assumptions currently in the Modeling Lab sheet")
        reset = button("Reset to defaults", "Ghost", self.reset_defaults)
        lay.addLayout(hbox(self.edit_which, label("Rooms:", "Muted", wrap=False), self.rooms, "stretch", sync, reset))

        self.table = QTableWidget(len(ROWS), 12)
        self.table.setHorizontalHeaderLabels(H.MONTHS)
        self.table.setVerticalHeaderLabels([r[1] for r in ROWS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(64)
        self.table.setMaximumHeight(170)
        self.table.itemChanged.connect(self._cell_changed)
        lay.addWidget(self.table)
        self.input_msg = label("", "Muted")
        lay.addWidget(self.input_msg)

        what = Card("Card", 16, 8)
        what.add(label("What-if shifts (applied on top of the forecast, not saved)", "H3"))
        g = QGridLayout()
        self.occ_s = _slider(-15, 10, 0)
        self.adr_s = _slider(-20, 20, 0)
        self.fb_s = _slider(-30, 30, 0)
        self.occ_l, self.adr_l, self.fb_l = label("", wrap=False), label("", wrap=False), label("", wrap=False)
        for r, (name, s, l) in enumerate((("Occupancy (points)", self.occ_s, self.occ_l),
                                          ("ADR (%)", self.adr_s, self.adr_l),
                                          ("F&B spend (%)", self.fb_s, self.fb_l))):
            g.addWidget(label(name, wrap=False), r, 0)
            g.addWidget(s, r, 1)
            g.addWidget(l, r, 2)
            s.valueChanged.connect(lambda _=0: self._timer.start())
        g.setColumnStretch(1, 1)
        what.add(g)
        presets = hbox(button("Downside case", "", lambda: self._preset(-4, -3, -5), "Occupancy -4 points, ADR -3%, F&B -5%"),
                       button("Upside case", "", lambda: self._preset(2, 4, 3), "Occupancy +2 points, ADR +4%, F&B +3%"),
                       button("Clear shifts", "Ghost", lambda: self._preset(0, 0, 0)),
                       "stretch", button("Apply shifts to forecast", "", self.apply_shifts))
        what.add(presets)
        lay.addWidget(what)

        self.tiles = {k: StatTile(t) for k, t in (("rev", "Room revenue (scenario)"), ("var", "vs budget"),
                                                    ("occ", "Occupancy (weighted)"), ("adr", "ADR"),
                                                    ("revpar", "RevPAR"), ("total", "Total operating revenue"))}
        tl = QGridLayout()
        for i, t in enumerate(self.tiles.values()):
            tl.addWidget(t, i // 3, i % 3)
        lay.addLayout(tl)

        charts = QHBoxLayout()
        c1, c2 = Card("Card", 10, 4), Card("Card", 10, 4)
        self.rev_chart = Chart(6, 2.9)
        self.bridge_chart = Chart(4.2, 2.9)
        c1.add(self.rev_chart)
        c2.add(self.bridge_chart)
        charts.addWidget(c1, 3)
        charts.addWidget(c2, 2)
        lay.addLayout(charts)

        self.checks_card = Card("Card", 16, 6)
        lay.addWidget(self.checks_card)

        mt = Card("Card", 16, 8)
        mt.add(label("Monthly detail: scenario vs budget, with the revenue bridge", "H3"))
        self.month_table = QTableWidget(13, 9)
        self.month_table.setHorizontalHeaderLabels(["Occupancy", "ADR", "RevPAR", "Rooms sold", "Room revenue",
                                                    "Budget", "Variance", "Volume effect", "Rate effect"])
        self.month_table.setVerticalHeaderLabels(H.MONTHS + ["Year"])
        self.month_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.month_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.month_table.setMinimumHeight(430)
        mt.add(self.month_table)
        mt.add(label("Volume effect = (scenario rooms - budget rooms) × budget ADR. Rate effect = (scenario ADR - "
                     "budget ADR) × scenario rooms. They add up exactly to the variance.", "Muted"))
        lay.addWidget(mt)

        sens = Card("Card", 16, 8)
        sens.add(label("Sensitivity: annual room revenue by occupancy shift (rows) and ADR shift (columns)", "H3"))
        self.occ_steps = [-0.06, -0.03, 0.0, 0.03, 0.06]
        self.adr_steps = [-0.10, -0.05, 0.0, 0.05, 0.10]
        self.sens_table = QTableWidget(5, 5)
        self.sens_table.setHorizontalHeaderLabels([f"ADR {x:+.0%}" for x in self.adr_steps])
        self.sens_table.setVerticalHeaderLabels([f"Occ {x * 100:+.0f} pts" for x in self.occ_steps])
        self.sens_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sens_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sens_table.setMinimumHeight(190)
        sens.add(self.sens_table)
        sens.add(label("Each cell recalculates the full 12-month model with the shift applied to every month "
                       "(occupancy capped at 100%). The base case is the centre cell.", "Muted"))
        lay.addWidget(sens)

        act = Card("Card", 16, 8)
        act.add(label("Actual vs budget vs forecast: January to June (fictional actuals)", "H3"))
        self.act_table = QTableWidget(7, 6)
        self.act_table.setHorizontalHeaderLabels(["Actual room rev.", "Budget", "Forecast", "Actual vs budget",
                                                  "Actual vs forecast", "Actual ADR"])
        self.act_table.setVerticalHeaderLabels(H.MONTHS[:6] + ["YTD"])
        self.act_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.act_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.act_table.setMinimumHeight(250)
        act.add(self.act_table)
        lay.addWidget(act)
        return w

    def refresh(self):
        p = self.ctx.project
        if p and p.kind == "hotel_model":
            try:
                lab = assumptions_from_sheet(p.sheet)
                p.forecast.rooms, p.forecast.year, p.forecast.months = lab.rooms, lab.year, lab.months
            except ValueError:
                pass
        self.load_table()
        self.recalc()

    def _target(self) -> H.HotelAssumptions:
        p = self.ctx.project
        return p.forecast if self.edit_which.value == "forecast" else p.budget

    def load_table(self):
        if self.ctx.project is None:
            from ...data.projects import new_hotel_project
            self.ctx.project = new_hotel_project()
        a = self._target()
        self.table.blockSignals(True)
        for r, (attr, _, fmt) in enumerate(ROWS):
            for c in range(12):
                v = getattr(a.months[c], attr)
                it = QTableWidgetItem(format_value(v, fmt))
                it.setData(Qt.UserRole, v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                it.setForeground(Qt.blue if palette().name == "light" else Qt.cyan)
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        self.rooms.blockSignals(True)
        self.rooms.setValue(self.ctx.project.forecast.rooms)
        self.rooms.blockSignals(False)

    def _cell_changed(self, it: QTableWidgetItem):
        from ...core.sheet import parse_literal
        attr, name, fmt = ROWS[it.row()]
        raw = it.text().strip()
        v = parse_literal(raw)
        if fmt == "percent" and isinstance(v, float) and "%" not in raw and v > 1.5:
            v = v / 100
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            self.input_msg.setText(f"<span style='color:{palette().coral}'>Invalid input: '{html.escape(raw)}' is not a "
                                   "number. The previous value was kept.</span>")
            self.input_msg.setTextFormat(Qt.RichText)
            self.load_table()
            return
        setattr(self._target().months[it.column()], attr, float(v))
        self.input_msg.setText("")
        self._push_to_lab()
        self.load_table()
        self._timer.start()

    def _rooms_changed(self, v):
        self.ctx.project.forecast.rooms = v
        self.ctx.project.budget.rooms = v
        self._push_to_lab()
        self._timer.start()

    def _push_to_lab(self):
        p = self.ctx.project
        if p.kind == "hotel_model":
            hs.write_assumptions(p.sheet, p.forecast)
            hs.write_budget(p.sheet, p.budget)
            self.ctx.project_dirty = True

    def reload_from_lab(self):
        self.refresh()
        self.ctx.notify("Loaded assumptions from the Modeling Lab sheet.")

    def reset_defaults(self):
        p = self.ctx.project
        p.forecast, p.budget = H.default_forecast(), H.default_budget()
        self._push_to_lab()
        self.load_table()
        self.recalc()

    def _preset(self, o, a, f):
        self.occ_s.setValue(o)
        self.adr_s.setValue(a)
        self.fb_s.setValue(f)
        self.recalc()

    def scenario(self) -> H.HotelAssumptions:
        return H.apply_scenario(self.ctx.project.forecast, self.occ_s.value() / 100, self.adr_s.value() / 100,
                                self.fb_s.value() / 100, name="Scenario")

    def apply_shifts(self):
        p = self.ctx.project
        p.forecast = self.scenario().copy(scenario="Forecast")
        self._preset(0, 0, 0)
        self._push_to_lab()
        self.load_table()
        self.ctx.notify("Shifts applied to the forecast assumptions (also updated in the Lab sheet).")

    def recalc(self):
        if self.ctx.project is None:
            return
        self.occ_l.setText(f"{self.occ_s.value():+d} pts")
        self.adr_l.setText(f"{self.adr_s.value():+d}%")
        self.fb_l.setText(f"{self.fb_s.value():+d}%")
        p = self.ctx.project
        sc = self.scenario()
        checks = H.validate(sc)
        fails = [c for c in checks if c.status == "fail"]
        clear_layout(self.checks_card.lay)
        self.checks_card.add(label("Model checks", "H3"))
        pal = palette()
        for c in checks:
            color = {"pass": pal.success, "warn": pal.amber, "fail": pal.coral}[c.status]
            mark = {"pass": "✓", "warn": "!", "fail": "✗"}[c.status]
            self.checks_card.add(label(f"<span style='color:{color};font-weight:700'>{mark}</span> "
                                       f"<b>{html.escape(c.name)}</b> <span style='color:{pal.muted}'>"
                                       f"({c.category})</span> — {html.escape(c.message)}", "Body", rich=True))
        if fails:
            for t in self.tiles.values():
                t.set("n/a", "Fix the failed checks first", "bad")
            return
        r, b = H.compute(sc), H.compute(p.budget)
        t, bt = r.total, b.total
        var = t.room_revenue - bt.room_revenue
        self.tiles["rev"].set(format_value(t.room_revenue, "currency0"), f"{sc.rooms} rooms, {sc.year}")
        self.tiles["var"].set(format_value(var, "currency0"),
                              f"{var / bt.room_revenue:+.1%} vs budget" if bt.room_revenue else "budget is zero",
                              "good" if var >= 0 else "bad")
        self.tiles["occ"].set(fmt_opt(t.occupancy, "percent"),
                              f"budget {fmt_opt(bt.occupancy, 'percent')}")
        self.tiles["adr"].set(fmt_opt(t.adr, "currency"), f"budget {fmt_opt(bt.adr, 'currency')}")
        self.tiles["revpar"].set(fmt_opt(t.revpar, "currency"), f"budget {fmt_opt(bt.revpar, 'currency')}")
        self.tiles["total"].set(format_value(t.total_revenue, "currency0"), "rooms + F&B + other")
        self.rev_chart.bars(H.MONTHS, [("Budget", [m.room_revenue for m in b.months]),
                                       ("Scenario", [m.room_revenue for m in r.months])],
                            title="Room revenue by month")
        bridge = H.room_revenue_bridge(bt, t)
        self.bridge_chart.waterfall([("Volume", bridge.volume_effect), ("Rate", bridge.rate_effect)], "Budget",
                                    bt.room_revenue, "Scenario", title="Annual room revenue bridge")
        rows = list(zip(r.months, b.months)) + [(t, bt)]
        for i, (m, bm) in enumerate(rows):
            br = H.room_revenue_bridge(bm, m)
            vals = [fmt_opt(m.occupancy, "percent"), fmt_opt(m.adr, "currency"), fmt_opt(m.revpar, "currency"),
                    format_value(m.rooms_sold, "number0"), format_value(m.room_revenue, "currency0"),
                    format_value(bm.room_revenue, "currency0"), format_value(br.total_variance, "currency0"),
                    format_value(br.volume_effect, "currency0"), format_value(br.rate_effect, "currency0")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 6:
                    it.setForeground(Qt.darkGreen if br.total_variance >= 0 else Qt.red)
                self.month_table.setItem(i, c, it)
        grid = H.sensitivity_grid(p.forecast.copy(), self.occ_steps, self.adr_steps)
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                it = QTableWidgetItem(format_value(v, "currency0"))
                it.setTextAlignment(Qt.AlignCenter)
                if i == 2 and j == 2:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.sens_table.setItem(i, j, it)
        acts = H.actuals_result(p.forecast.rooms, p.forecast.year)
        f_res = H.compute(p.forecast)
        tot = [0.0, 0.0, 0.0, 0.0]
        for i, a in enumerate(acts):
            bm, fm = b.months[i], f_res.months[i]
            tot[0] += a.room_revenue
            tot[1] += bm.room_revenue
            tot[2] += fm.room_revenue
            tot[3] += a.rooms_sold
            self._act_row(i, a.room_revenue, bm.room_revenue, fm.room_revenue, a.adr)
        self._act_row(6, tot[0], tot[1], tot[2], tot[0] / tot[3] if tot[3] else None)

    def _act_row(self, i, act, bud, fc, adr):
        vals = [format_value(act, "currency0"), format_value(bud, "currency0"), format_value(fc, "currency0"),
                f"{format_value(act - bud, 'currency0')} ({(act - bud) / bud:+.1%})" if bud else "n/a",
                f"{format_value(act - fc, 'currency0')} ({(act - fc) / fc:+.1%})" if fc else "n/a",
                fmt_opt(adr, "currency")]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.act_table.setItem(i, c, it)

    # ============================================================ group tab
    def _group_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setSpacing(16)
        form_card = Card("Card", 16, 8)
        form_card.add(label("The decision", "H3"),
                      label("A conference group asks for a block of rooms at a discounted rate over peak nights. "
                            "Accept the group, or protect the rooms for individual (transient) guests who pay more "
                            "but may not all book?", "Body"))
        self.g_inputs = {}
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        d = GroupInputs()
        specs = [("rooms_available", "Rooms available per night", 0, 1000, 1, 0),
                 ("nights", "Nights", 1, 30, 1, 0),
                 ("group_rooms", "Group rooms per night", 0, 1000, 1, 0),
                 ("group_rate", "Group rate ($)", 0, 2000, 5, 2),
                 ("group_commission", "Group commission (%)", 0, 100, 1, 1),
                 ("group_fb_per_room", "Group F&B per room night ($)", 0, 1000, 5, 2),
                 ("transient_demand", "Transient demand (rooms/night)", 0, 1000, 5, 0),
                 ("booking_probability", "Probability transient demand books (%)", 0, 100, 1, 1),
                 ("transient_rate", "Transient rate ($)", 0, 2000, 5, 2),
                 ("transient_distribution_cost", "Transient channel cost (%)", 0, 100, 1, 1),
                 ("transient_fb_per_room", "Transient F&B per room night ($)", 0, 1000, 5, 2),
                 ("fb_margin", "F&B profit margin (%)", 0, 100, 1, 1),
                 ("variable_cost_per_room", "Variable cost per occupied room ($)", 0, 500, 1, 2)]
        for attr, text, lo, hi, step, dec in specs:
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(step)
            sb.setDecimals(dec if dec != 1 else 1)
            v = getattr(d, attr)
            pct = attr in ("group_commission", "booking_probability", "transient_distribution_cost", "fb_margin")
            sb.setValue(v * 100 if pct else v)
            sb.valueChanged.connect(self.recalc_group)
            form.addRow(text, sb)
            self.g_inputs[attr] = (sb, pct)
        form_card.add(form)
        form_card.add(button("Reset inputs", "Ghost", self._reset_group))
        lay.addWidget(form_card, 2)
        right = QVBoxLayout()
        self.g_tiles = {k: StatTile(t) for k, t in (("acc", "Accept: expected contribution"),
                                                     ("dec", "Decline: expected contribution"),
                                                     ("diff", "Difference (accept - decline)"),
                                                     ("be", "Break-even group rate"))}
        tg = QGridLayout()
        for i, t in enumerate(self.g_tiles.values()):
            tg.addWidget(t, i // 2, i % 2)
        right.addLayout(tg)
        self.g_rec = Card("FeedbackInfo", 14, 6)
        right.addWidget(self.g_rec)
        c = Card("Card", 10, 4)
        self.g_chart = Chart(5.5, 2.6)
        self.p_chart = Chart(5.5, 2.4)
        c.add(self.g_chart, self.p_chart)
        right.addWidget(c)
        self.g_table = QTableWidget(8, 2)
        self.g_table.setHorizontalHeaderLabels(["Accept group", "Decline group"])
        self.g_table.setVerticalHeaderLabels(["Group room nights", "Transient room nights", "Occupancy",
                                              "Room revenue", "Distribution costs", "Variable room costs",
                                              "F&B profit", "Contribution"])
        self.g_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.g_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.g_table.setMinimumHeight(290)
        right.addWidget(self.g_table)
        lay.addLayout(right, 3)
        self.recalc_group()
        return w

    def _reset_group(self):
        d = GroupInputs()
        for attr, (sb, pct) in self.g_inputs.items():
            sb.blockSignals(True)
            sb.setValue(getattr(d, attr) * 100 if pct else getattr(d, attr))
            sb.blockSignals(False)
        self.recalc_group()

    def group_inputs(self) -> GroupInputs:
        kw = {}
        for attr, (sb, pct) in self.g_inputs.items():
            v = sb.value() / 100 if pct else sb.value()
            if attr in ("rooms_available", "nights", "group_rooms"):
                v = int(round(v))
            kw[attr] = v
        return GroupInputs(**kw)

    def recalc_group(self):
        gi = self.group_inputs()
        problems = validate_inputs(gi)
        clear_layout(self.g_rec.lay)
        if problems:
            self.g_rec.setObjectName("FeedbackBad")
            self.g_rec.style().polish(self.g_rec)
            self.g_rec.add(label("Invalid inputs", "H3"), label(" ".join(problems), "Body"))
            for t in self.g_tiles.values():
                t.set("n/a", "")
            return
        res = analyse(gi)
        self.g_rec.setObjectName("FeedbackInfo")
        self.g_rec.style().polish(self.g_rec)
        self.g_tiles["acc"].set(format_value(res.accept.contribution, "currency0"),
                                f"occupancy {res.accept.occupancy:.0%}")
        self.g_tiles["dec"].set(format_value(res.decline.contribution, "currency0"),
                                f"occupancy {res.decline.occupancy:.0%}")
        self.g_tiles["diff"].set(format_value(res.incremental_contribution, "currency0"),
                                 "accepting adds value" if res.incremental_contribution > 0 else "accepting costs value",
                                 "good" if res.incremental_contribution > 0 else "bad")
        self.g_tiles["be"].set(fmt_opt(res.breakeven_group_rate, "currency"), f"offered ${gi.group_rate:,.0f}")
        self.g_rec.add(label("RECOMMENDATION (MODEL ESTIMATE)", "Eyebrow"), label(res.recommendation, "H3"))
        for e in res.explanation:
            self.g_rec.add(label("• " + e, "Body"))
        for col, o in enumerate((res.accept, res.decline)):
            vals = [format_value(o.group_rooms, "number0"), format_value(o.transient_rooms, "number0"),
                    f"{o.occupancy:.1%}", format_value(o.room_revenue, "currency0"),
                    format_value(-o.distribution_cost, "currency0"), format_value(-o.variable_cost, "currency0"),
                    format_value(o.fb_profit, "currency0"), format_value(o.contribution, "currency0")]
            for r, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.g_table.setItem(r, col, it)
        self.g_chart.bars(["Room revenue", "Costs", "F&B profit", "Contribution"],
                          [("Decline", [res.decline.room_revenue, -(res.decline.distribution_cost + res.decline.variable_cost),
                                        res.decline.fb_profit, res.decline.contribution]),
                           ("Accept", [res.accept.room_revenue, -(res.accept.distribution_cost + res.accept.variable_cost),
                                       res.accept.fb_profit, res.accept.contribution])],
                          title="Accept vs decline")
        probs = [i / 20 for i in range(21)]
        diffs = []
        for pr in probs:
            g2 = GroupInputs(**{**gi.__dict__, "booking_probability": pr})
            diffs.append(analyse(g2).incremental_contribution)
        self.p_chart.lines([f"{p:.0%}" if i % 4 == 0 else "" for i, p in enumerate(probs)],
                           [("Accept minus decline", diffs)], title="Decision vs transient booking probability")
        self.p_chart.ax.axhline(0, color=palette().muted, linewidth=0.8)
        self.p_chart.draw_idle()
