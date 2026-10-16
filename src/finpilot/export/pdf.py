"""PDF reports: competency report and hotel model project report (ReportLab)."""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from .. import __app_name__, __tagline__, __version__
from ..core.format import fmt_opt, format_value
from ..core.hotel import HotelAssumptions, compute, room_revenue_bridge, validate

NAVY = colors.HexColor("#101D2B")
TEAL = colors.HexColor("#59D6C0")
TEAL_DARK = colors.HexColor("#1E8C7A")
AMBER = colors.HexColor("#F3B65B")
CREAM = colors.HexColor("#F5F1E8")
SLATE = colors.HexColor("#5B6675")
CORAL = colors.HexColor("#E0675A")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Heading1"], textColor=NAVY, fontSize=18, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=_ss["Heading2"], textColor=NAVY, fontSize=13, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=_ss["BodyText"], fontSize=9.5, leading=13, alignment=TA_LEFT)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8, textColor=SLATE, leading=10)


def _header_footer(title: str):
    def draw(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 18 * mm, w, 18 * mm, fill=1, stroke=0)
        _draw_logo(canvas, 14 * mm, h - 13.5 * mm, 9 * mm)
        canvas.setFillColor(TEAL)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(26 * mm, h - 10.5 * mm, __app_name__)
        canvas.setFillColor(AMBER)
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.drawString(26 * mm, h - 14.5 * mm, __tagline__)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(w - 14 * mm, h - 11 * mm, title)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(14 * mm, 9 * mm, f"{__app_name__} {__version__} - generated "
                          f"{dt.datetime.now():%d %b %Y %H:%M} - fictional training data")
        canvas.drawRightString(w - 14 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def _draw_logo(canvas, x, y, size):
    """Compass mark: teal ring with an amber north needle."""
    from reportlab.lib.colors import white
    r = size / 2
    cx, cy = x + r, y + r
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.4)
    canvas.circle(cx, cy, r * 0.92, stroke=1, fill=0)
    p = canvas.beginPath()
    p.moveTo(cx, cy + r * 0.78)
    p.lineTo(cx + r * 0.22, cy)
    p.lineTo(cx, cy - r * 0.15)
    p.lineTo(cx - r * 0.22, cy)
    p.close()
    canvas.setFillColor(AMBER)
    canvas.drawPath(p, fill=1, stroke=0)
    p2 = canvas.beginPath()
    p2.moveTo(cx, cy - r * 0.78)
    p2.lineTo(cx + r * 0.16, cy)
    p2.lineTo(cx - r * 0.16, cy)
    p2.close()
    canvas.setFillColor(white)
    canvas.drawPath(p2, fill=1, stroke=0)


def _table(data, col_widths=None, header=True, zebra=True):
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1 if header else 0)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9D3C4")),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), CREAM))
    t.setStyle(TableStyle(style))
    return t


def _p(text, style=BODY):
    return Paragraph(text, style)


# ---------------------------------------------------------------- competency

STATUS_LABEL = {"demonstrated": "Demonstrated", "developing": "Developing", "needs_practice": "Needs practice",
                "not_assessed": "Not yet assessed"}


def competency_report_pdf(path: Path, report: dict) -> Path:
    path = Path(path)
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=26 * mm, bottomMargin=16 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title="FinPilot Competency Report",
                            author=__app_name__)
    story = [_p("Competency report", H1),
             _p(f"Learner: <b>{report['learner']}</b> &nbsp;&nbsp; Generated: {report['generated']} &nbsp;&nbsp; "
                f"XP: {report['xp']}", BODY), Spacer(1, 6)]
    finals = report["assessments"]
    model_ok = report["model_validated"]
    if finals:
        last = finals[-1]
        best = max(finals, key=lambda a: a["score"])
        verdict = ("PASSED" if last["passed"] else "NOT YET PASSED")
        story.append(_p(f"Final practical assessment: <b>{verdict}</b> - latest {last['score']:.0%}, best "
                        f"{best['score']:.0%}, attempts {len(finals)}.", BODY))
    else:
        story.append(_p("Final practical assessment: not attempted yet.", BODY))
    story.append(_p(("12-month hotel model: <b>validated</b> against FinPilot's independent calculation."
                     if model_ok else "12-month hotel model: <b>not yet validated</b>. Modeling competence "
                     "requires a validated model; a quiz alone is not sufficient."), BODY))

    story.append(_p("Skills", H2))
    rows = [["Skill", "Area", "Status", "Score", "Evidence", "Note"]]
    for key in ("demonstrated", "developing", "needs_practice", "not_assessed"):
        for c in report[key]:
            rows.append([_p(c.name, SMALL), _p(c.area, SMALL), STATUS_LABEL[c.status],
                         "" if c.score is None else f"{c.score:.0%}", str(c.evidence), _p(c.note, SMALL)])
    story.append(_table(rows, [48 * mm, 34 * mm, 24 * mm, 14 * mm, 15 * mm, 47 * mm]))

    if finals:
        story.append(_p("Assessment results by section (latest attempt)", H2))
        secs = finals[-1]["details"].get("sections", {})
        rows = [["Section", "Score", "Items"]] + [[s, f"{v['score']:.0%}", str(v["items"])] for s, v in secs.items()]
        story.append(_table(rows, [80 * mm, 25 * mm, 20 * mm]))
        hist = [["Attempt", "Date", "Score", "Result"]] + [
            [str(i + 1), a["ts"][:16].replace("T", " "), f"{a['score']:.0%}", "Pass" if a["passed"] else "Not yet"]
            for i, a in enumerate(finals)]
        story.append(Spacer(1, 6))
        story.append(_table(hist, [20 * mm, 45 * mm, 25 * mm, 25 * mm]))

    story.append(_p("Model validation and projects", H2))
    if report["projects"]:
        rows = [["Project", "Progress", "Validated", "Last saved"]] + [
            [_p(p["name"], SMALL), f"{p['progress']:.0%}", "Yes" if p["validated"] else "No", p["updated_at"][:16]]
            for p in report["projects"]]
        story.append(_table(rows, [80 * mm, 25 * mm, 25 * mm, 40 * mm]))
    else:
        story.append(_p("No saved projects yet.", BODY))

    story.append(_p("Completed lessons", H2))
    story.append(_p(", ".join(report["completed_lessons"]) or "None yet.", BODY))
    story.append(_p("Outstanding learning objectives", H2))
    story.append(_p(", ".join(report["outstanding"]) or "All V1 objectives complete.", BODY))
    rec = report["next_step"]
    story.append(_p("Recommended next steps", H2))
    steps = [f"<b>{rec.title}</b>: {rec.reason}"]
    for c in report["needs_practice"][:4]:
        steps.append(f"Practise <b>{c.name}</b>: revisit its lesson and the related mistakes in your notebook.")
    for c in report["developing"][:3]:
        steps.append(f"Strengthen <b>{c.name}</b> with Challenge mode exercises.")
    for s in steps:
        story.append(_p("• " + s, BODY))
    story.append(_p("Assessment criteria", H2))
    for c in report["criteria"]:
        story.append(_p("• " + c, SMALL))
    story.append(Spacer(1, 4))
    story.append(_p("FinPilot assesses evidence gathered inside the application. It is a learning record, not a "
                    "professional certification.", SMALL))
    doc.build(story, onFirstPage=_header_footer("Competency report"),
              onLaterPages=_header_footer("Competency report"))
    return path


# ------------------------------------------------------------ project report


def _chart_png(forecast: HotelAssumptions, budget: HotelAssumptions) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    f, b = compute(forecast), compute(budget)
    months = [m.month for m in f.months]
    fig, ax = plt.subplots(figsize=(7.2, 2.8), dpi=150)
    x = range(12)
    ax.bar([i - 0.2 for i in x], [m.room_revenue / 1e6 for m in b.months], width=0.4, color="#B8C2CC",
           label="Budget")
    ax.bar([i + 0.2 for i in x], [m.room_revenue / 1e6 for m in f.months], width=0.4, color="#2BA88F",
           label="Forecast")
    ax.set_xticks(list(x))
    ax.set_xticklabels(months, fontsize=8)
    ax.set_ylabel("Room revenue ($m)", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.grid(axis="y", color="#E5E0D5", linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def project_report_pdf(path: Path, name: str, forecast: HotelAssumptions, budget: HotelAssumptions,
                       recommendation: str = "", model_checks: Optional[list] = None) -> Path:
    path = Path(path)
    f, b = compute(forecast), compute(budget)
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=26 * mm, bottomMargin=16 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title=name, author=__app_name__)
    story = [_p(name, H1),
             _p(f"{forecast.hotel_name} - 12-month room revenue forecast {forecast.year} vs budget. "
                f"Currency {forecast.currency}. All figures fictional.", BODY), Spacer(1, 4)]
    var = f.total.room_revenue - b.total.room_revenue
    kpis = [["", "Budget", "Forecast", "Variance"],
            ["Room revenue", format_value(b.total.room_revenue, "currency0"),
             format_value(f.total.room_revenue, "currency0"), format_value(var, "currency0")],
            ["Total operating revenue", format_value(b.total.total_revenue, "currency0"),
             format_value(f.total.total_revenue, "currency0"),
             format_value(f.total.total_revenue - b.total.total_revenue, "currency0")],
            ["Occupancy (weighted)", fmt_opt(b.total.occupancy, "percent"), fmt_opt(f.total.occupancy, "percent"),
             f"{(f.total.occupancy - b.total.occupancy) * 100:+.1f} pts"],
            ["ADR", fmt_opt(b.total.adr, "currency"), fmt_opt(f.total.adr, "currency"),
             format_value(f.total.adr - b.total.adr, "currency")],
            ["RevPAR", fmt_opt(b.total.revpar, "currency"), fmt_opt(f.total.revpar, "currency"),
             format_value(f.total.revpar - b.total.revpar, "currency")]]
    story.append(_p("Key results", H2))
    story.append(_table(kpis, [55 * mm, 40 * mm, 40 * mm, 40 * mm]))
    story.append(Spacer(1, 6))
    story.append(Image(io.BytesIO(_chart_png(forecast, budget)), width=180 * mm, height=70 * mm))

    story.append(_p("Monthly detail (forecast)", H2))
    rows = [["Month", "Occ.", "ADR", "RevPAR", "Rooms sold", "Room rev.", "Budget", "Var.", "Volume", "Rate"]]
    for fm, bm in zip(f.months, b.months):
        br = room_revenue_bridge(bm, fm)
        rows.append([fm.month, fmt_opt(fm.occupancy, "percent"), fmt_opt(fm.adr, "currency0"),
                     fmt_opt(fm.revpar, "currency0"), format_value(fm.rooms_sold, "number0"),
                     format_value(fm.room_revenue, "currency0"), format_value(bm.room_revenue, "currency0"),
                     format_value(br.total_variance, "currency0"), format_value(br.volume_effect, "currency0"),
                     format_value(br.rate_effect, "currency0")])
    t = _table(rows, [13 * mm, 14 * mm, 14 * mm, 16 * mm, 19 * mm, 23 * mm, 23 * mm, 20 * mm, 20 * mm, 19 * mm])
    t.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
                           ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5)]))
    story.append(t)
    story.append(_p("Volume effect = (forecast rooms - budget rooms) x budget ADR. Rate effect = (forecast ADR - budget "
                    "ADR) x forecast rooms. Effects reconcile exactly to the variance.", SMALL))

    story.append(_p("Model checks", H2))
    checks = model_checks if model_checks is not None else [(c.name, c.status, c.message) for c in validate(forecast)]
    rows = [["Check", "Result", "Detail"]] + [[_p(n, SMALL), s.upper() if isinstance(s, str) else ("PASS" if s else "FAIL"),
                                               _p(m, SMALL)] for n, s, m in checks]
    story.append(_table(rows, [55 * mm, 18 * mm, 107 * mm]))

    story.append(_p("Assumptions and methodology", H2))
    for line in [
        f"Rooms: {forecast.rooms}. Year: {forecast.year}. Days per month from the calendar (leap years handled).",
        "Occupancy = Rooms Sold / Available Room Nights; ADR = Room Revenue / Rooms Sold; RevPAR = Room Revenue / "
        "Available Room Nights. Annual ratios are weighted from totals.",
        "F&B revenue = rooms sold x spend per occupied room; other revenue = % of room revenue (simplified).",
        forecast.notes or "", budget.notes or "",
        "This is a model output based on stated assumptions. It is not a guarantee of future results."]:
        if line:
            story.append(_p("• " + line, BODY))
    if recommendation.strip():
        story.append(_p("Management recommendation", H2))
        for para in recommendation.strip().split("\n"):
            if para.strip():
                story.append(_p(para.strip(), BODY))
    doc.build(story, onFirstPage=_header_footer("Project report"), onLaterPages=_header_footer("Project report"))
    return path
