# FinPilot 1.0.0 test report

Date: 16 October 2026. Every result below comes from an actual run; nothing is estimated.

## Environment

- Linux x86-64 container (not Windows), Python 3.13.16, in a fresh virtual environment created from
  `requirements-dev.txt` (PySide6-Essentials 6.8.1, matplotlib 3.11.2, numpy 2.5.3, openpyxl 3.1.5,
  ReportLab 5.0.1, pytest 9.1.1, pytest-qt 4.5.0, PyInstaller 6.22.3).
- Qt ran with the `offscreen` platform (no physical display).
- LibreOffice 24.2.7.2 was available and used for the independent Excel recalculation test.
- Microsoft Excel and Windows were **not** available.

## Automated test suite: 158 passed, 0 failed, 0 skipped (80.4 s)

Command: `QT_QPA_PLATFORM=offscreen python -m pytest tests -p no:cacheprovider -rA`

| File | Tests | Time | What it covers |
|---|---|---|---|
| test_formula_engine.py | 40 | 0.1 s | Precedence (`-2^2`, `2^3^2`, `%`), references and ranges, 13 function cases, dates (Excel serials), PMT/NPV/IRR/FV against known values, all error codes incl. `#UNSUPPORTED!`, error propagation, syntax errors, code-injection text is not executed, reference shifting |
| test_sheet.py | 7 | 0.0 s | Recalculation order, circular references (`#CIRC!`), undo/redo, fill right with `$` anchors, named ranges, save/load of sheets, Explain |
| test_finance_hotel.py | 18 | 0.0 s | Zero denominators, finance formulas, profit vs cash, KPI identities (RevPAR = ADR x occupancy), budget 17,366,058 and forecast 17,484,066 recomputed by hand from the calendar, weighted (not averaged) annual KPIs, leap years, zero rooms, invalid occupancy, 12-month requirement, bridge reconciles exactly for every month and the year, variance 118,008 (+0.68%), scenario figure $16.10m, the Lesson 3.6 sensitivity table, seasonal occupancy, group displacement by hand, break-even group rate, invalid group inputs |
| test_grading_curriculum.py | 43 | 2.0 s | Number grading (percent notations, accounting negatives, unit/sign/known-mistake diagnoses), choice, formula grading (equivalent forms accepted; typed values, constants and missing `$` rejected; circular; syntax; required functions), written rubric, curriculum validation, curriculum shape, every formula item's reference passes its own grader, fictional-data labelling, final assessment rules, hotel project checker (reference validates, empty guided sheet, typed values, missing anchor, named range accepted, AVERAGE of ratios rejected, budget total present, error cells block validation), all 13 drills x 15 seeds |
| test_progression.py | 14 | 0.5 s | Item scoring, starting point, prerequisites, level unlocking, planned levels stay locked, unlock-all, mastery threshold, review priority, final assessment recommendation, idempotent XP and badges, competency requires evidence, hotel-model skill requires a validated model, needs-practice rating, report contents |
| test_data.py | 19 | 0.3 s | Settings, progress persists across reopen, best score kept, XP once per item, spaced-repetition dates (1/3/7 days) and resolution after three correct reviews, streak reset, backup/restore round trip, non-backup rejected, restore never overwrites a newer project, corrupted database moved aside and recreated, project save/load, `.bak` on save, empty/invalid/foreign/binary/missing project files give clear errors, hand-edited file opens with a checksum warning, 11-month file rejected |
| test_exports.py | 5 | 1.8 s | Workbook sheets and real formulas, every exported formula re-read and recalculated by FinPilot's engine equals the original, Lab sheet export, **LibreOffice headless recalculation matches FinPilot for every formula cell** (Model N17 = 17,484,066; Scenarios 17,366,058 and 17,484,066; all Bridge checks TRUE), both PDFs are valid |
| test_ui.py | 12 | 75.1 s | Onboarding to home, every screen at 1000x640, 1024x700, 1366x768 and 1920x1080 with no horizontal overflow, theme switch, navigation routing, Lab error explanation, hints and solutions locked until the required attempts in each mode, and the **full learner journey** below |

### Full learner journey (test_ui.py::test_full_learner_journey)

Drives the real widgets, not the functions behind them:

1. Completes onboarding.
2. Completes all 18 lessons and project P1 step by step. In each lesson the first question is answered wrongly
   on purpose, then correctly; every step's Continue button must unlock.
3. Builds the 12-month model in the Lab: each of the 10 tasks is typed in the formula bar, rows are filled
   with **Fill right**, and **Check task** must accept it. The model must validate against the independent
   calculation.
4. Saves the project to a `.finpilot` file and reopens it (10 tasks still complete).
5. Takes the final assessment (18 items): result 100%, passed.
6. Mistakes notebook: 19 mistakes recorded; due items are reviewed correctly.
7. Simulation: downside preset tile shows $16,101,064.
8. Exports the hotel workbook, the Lab sheet, the project PDF, the competency PDF and progress CSV: all
   files exist and are non-empty.
9. Checks badges (Model builder, V1 competency), every skill demonstrated, overall progress 100%.

## Packaged app (PyInstaller)

- `pyinstaller build/finpilot.spec` **on Linux**: build succeeded (one-folder app, 237 MB).
- `FinPilot --self-test <folder>` on that packaged app: exit code 0, all five checks PASS (12 screens built;
  20 lessons, 0 content problems; reference model validated with room revenue 17,484,066; Excel export
  re-read total 17,484,066; PDF written).
- `build/build_windows.ps1` was parsed with PowerShell 7.4.6 on Linux: no syntax errors. It has **not been
  run on Windows**.
- Windows 64-bit wheels for every pinned runtime dependency and PyInstaller were downloaded successfully for
  Python 3.12 (`win_amd64`), confirming the pins are installable on Windows.

## Windows build (GitHub Actions, windows-latest, Python 3.12.10 x64)

Run 38960959983 of `.github/workflows/windows-build.yml` executed `build\build_windows.ps1` end to end:

- Test suite with the native Windows Qt platform: 157 passed, 1 skipped (the LibreOffice recalculation test;
  LibreOffice is not installed on the runner), 0 failed.
- PyInstaller built `dist\FinPilot\FinPilot.exe`; its `--self-test` passed all five checks (12 screens,
  20 lessons with 0 content problems, reference model 17,484,066, Excel re-read 17,484,066, PDF written).
- Inno Setup built `dist\installer\FinPilot-Setup-1.0.0.exe`; checksums written to `SHA256SUMS.txt`.

The first Windows run found three Windows-only problems, now fixed: the database health check kept a file
handle open (a damaged database could not be moved aside), the learning map used a fixed column breakpoint
that did not fit Windows text widths, and the UI tests used Qt's `offscreen` platform, whose font metrics on
Windows do not match real use.

## Not tested

- Launching `FinPilot.exe` or running the installer interactively on a physical Windows 10/11 PC; SmartScreen behaviour.
- Opening exported workbooks in Microsoft Excel.
- Physical displays, Windows display scaling above 100%, keyboard-only use and screen readers.
- Long-term use (months of spaced-repetition data) beyond the date-shifting in the tests.

## Visual review

Screenshots of every screen were taken at 1024x700, 1366x768 and 1920x1080 in light and dark themes and
inspected. Issues found this way and fixed: clipped chips and buttons, wrapped headings, overflowing toolbar
and tables at 1024 px, unformatted learner-built cells, check rows reading FALSE before the model was built,
missing budget total in the guided model, and the Checks panel text overlapping. Final screenshots are in
`docs/screenshots/`.
