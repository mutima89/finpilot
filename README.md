# FinPilot

**Learn the numbers. Master the model.**
Interactive Financial Modeling Academy: a Windows desktop app (Python + PySide6) that teaches financial
modeling by having you build real models, step by step, with immediate feedback. Fully offline.

All companies, hotels and figures in FinPilot are **fictional** and for training only.

## What is in Version 1

- **Branded onboarding** (name, guidance mode, light/dark theme, XP on/off) and a home dashboard.
- **10-level learning map.** Levels 1-3 are complete courses (18 lessons + 2 projects); Level 4 has a
  working preview (group-vs-transient displacement simulator); Levels 5-10 are shown as planned.
- **Lesson engine** with 10 steps per lesson: Understand, See, Build, Predict, Test, Explain, Apply,
  Recall, Review, Progress. Three modes (Guided, Practice, Challenge). Hints and worked solutions unlock only
  after an attempt, in every mode (hints/solution after 1/1 tries in Guided, 1/2 in Practice, 2/3 in Challenge). Bookmarks, restart, resume where you left off.
- **Formula engine** (no `eval`): a safe parser and evaluator for 56 Excel functions, with Excel-style
  precedence, relative/absolute references, named ranges, and explicit error values
  (`#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?`, `#N/A`, `#NUM!`, `#CIRC!`, `#UNSUPPORTED!`). Unsupported Excel
  functions are reported as `#UNSUPPORTED!` with an explanation, never silently mis-evaluated.
- **Behavioural grading**: formula answers are re-evaluated with changed inputs, so typed numbers,
  hard-coded constants and missing `$` anchors are caught even when today's value looks right.
  Number answers diagnose percent-scale, sign, rounding, inverted ratios and known mistakes.
- **Modeling Lab**: a spreadsheet workspace where you build the 12-month Harbour Crest Hotel model in
  10 guided tasks (available room nights, rooms sold, room revenue, RevPAR, F&B, other revenue, total,
  full-year totals, weighted annual KPIs, budget variance). Each task is checked on changed inputs; the
  finished model is validated against an independent Python calculation. Undo/redo, fill right, copy/paste,
  explain cell, trace precedents, named ranges, roles/formats, autosave and recovery.
- **Hotel Simulation Center**: editable budget and forecast, what-if sliders and presets, KPI tiles,
  charts, validation checks, monthly volume/rate revenue bridge (reconciles exactly), sensitivity grid,
  actual vs budget vs forecast, and the group displacement analysis with break-even group rate.
- **Practice** (13 randomised formula drills), **final practical assessment** (18 items in 6 sections,
  70% overall and 50% per section to pass), **mistakes notebook** with spaced review (1, 3, 7, 14, 30 days;
  three correct reviews in a row resolve an item), **progress and competency dashboard** (20 skills, rated
  from evidence; the hotel-model skill requires a validated model), **portfolio**, **settings**
  (backup/restore, integrity check, reset).
- **Exports**: Excel workbook with live formulas (Model, Scenario inputs, Scenarios with charts, Bridge,
  Checks & notes, Recommendation), the Lab sheet alone, a project report PDF, a competency report PDF, and
  progress CSV/JSON.
- **Gamification** that rewards correct reasoning and validated models only; it can be switched off.
  No streaks, no timers, no penalties.
- **Privacy**: no account, no internet, no telemetry. Data stays in `%APPDATA%\FinPilot`.

## Run from source

Requires Python 3.11+ (3.12 64-bit recommended on Windows).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set PYTHONPATH=src
python -m finpilot
```

On macOS/Linux use `export PYTHONPATH=src` and `python3 -m finpilot`.

## Run the tests

```powershell
pip install -r requirements-dev.txt
set QT_QPA_PLATFORM=offscreen
python -m pytest tests
```

The suite (158 tests) covers the formula engine, sheet model, finance and hotel calculations against
independent hand calculations, grading, curriculum integrity, the hotel project checker, progression,
the database (including corruption and backup/restore), project files (including corrupted files), Excel
export round-trips (and a LibreOffice recalculation when LibreOffice is installed), PDFs, and UI tests that
render every screen at four window sizes and drive a complete learner journey through the real widgets.
See [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## Build the Windows app (.exe and installer)

On a Windows 10/11 64-bit PC with Python 3.12 (64-bit) installed:

```powershell
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
```

The script creates a clean virtual environment, installs pinned dependencies, runs the full test suite,
builds `dist\FinPilot\FinPilot.exe` with PyInstaller, runs the packaged app's headless self-test
(`FinPilot.exe --self-test <folder>`), and, if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed,
builds `dist\installer\FinPilot-Setup-1.0.0.exe` (per-user install, no admin rights). It finishes by writing
SHA-256 checksums. Details and troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

On GitHub, the **Windows build** workflow (`.github/workflows/windows-build.yml`) runs the same script on a
Windows runner for every push to `main` and uploads the portable app, the installer and the test/self-test
reports as downloadable artifacts of the run (Actions tab → latest run → Artifacts).

## Project layout

```
src/finpilot/
  core/          formula engine, sheet model, finance, hotel model, revenue management, formatting
  curriculum/    content JSON, loader/validator, grading, progression, hotel project, drills
  data/          SQLite progress database, .finpilot project files
  export/        Excel (openpyxl) and PDF (ReportLab)
  ui/            PySide6 app: theme, logo, widgets, grid, questions, main window, 12 screens
  assets/        icon files
tests/           pytest suite and the end-to-end UI journey
build/           PyInstaller spec, Windows build script, version info, Inno Setup script
tools/           content generators and icon generator
docs/            architecture, formula reference, known limitations, troubleshooting, checklist, test report
```

More: [ARCHITECTURE](docs/ARCHITECTURE.md) · [FORMULA_REFERENCE](docs/FORMULA_REFERENCE.md) ·
[KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md) · [CHECKLIST](docs/CHECKLIST.md)
