# V1 requirements checklist

Status key: **Done** (implemented and covered by tests or visual review), **Partial**, **Not done**.

| Requirement | Status | Where / notes |
|---|---|---|
| Windows 10/11 64-bit desktop app, Python + PySide6 | Done (source) | `src/finpilot`; runs from source; packaging verified on Linux only |
| Standalone .exe | **Not built** | `build/build_windows.ps1` + `build/finpilot.spec` produce and self-test it on Windows |
| Installer | **Not built** | `build/installer.iss` (Inno Setup 6), run by the build script |
| Fully offline, no telemetry, no account | Done | No network code; data in `%APPDATA%\FinPilot` |
| Brand: name, tagline, palette, compass logo, light/dark | Done | `ui/theme.py`, `ui/logo.py`, `assets/` |
| Modular architecture | Done | `docs/ARCHITECTURE.md` |
| No `eval()` on learner formulas; unsupported formulas reported | Done | Parser/evaluator; `#UNSUPPORTED!`; test "code-injection text is not executed" |
| 10-level learning map | Done | Levels 1-3 complete, 4 preview, 5-10 planned |
| Branded onboarding | Done | `ui/pages/onboarding.py` |
| Progress tracking | Done | SQLite, resume, best scores, dashboard |
| Financial foundations (Level 1) | Done | 6 lessons + project "Profitable but short of cash" |
| Spreadsheet fundamentals (Level 2) | Done | 6 lessons |
| Hotel revenue course (Level 3) | Done | 6 lessons + 12-month model project |
| 12-month model built step by step: occupancy, ADR, RevPAR, room revenue, seasonality, budget vs forecast | Done | Modeling Lab, 10 guided tasks, independent verification |
| Live recalculation | Done | Sheet dependency graph; simulation sliders |
| Scenarios | Done | Presets, sliders, budget vs forecast, sensitivity grid, group vs transient |
| Feedback and hints; hints/solutions only after an attempt | Done | Failed attempts before hint/solution: Guided 1/1, Practice 1/2, Challenge 2/3 (tested) |
| Validation checks | Done | Model checks, input checks, reasonableness warnings, independent verification |
| Save / reopen | Done | `.finpilot` with checksum, `.bak`, autosave recovery |
| Excel export with real formulas | Done | Verified by re-read and LibreOffice recalculation (not Excel) |
| Final assessment with meaningful report | Done | 18 items, 6 sections, per-section results, competency PDF |
| Lesson engine: 10 steps, 3 modes | Done | `ui/pages/lesson.py` |
| Bookmarks, mistakes notebook, spaced repetition | Done | 1/3/7/14/30 days, three correct in a row resolves |
| Meaningful XP/badges, can be switched off, no streaks or timers | Done | Settings → Gamification |
| 12 screens | Done | Onboarding, home, map, lesson, lab, simulation, practice, assessment, mistakes, progress, portfolio, export, settings (13 including onboarding) |
| Zero denominators handled explicitly | Done | `None`/`n/a` in Python, `#DIV/0!` or guarded formulas in sheets |
| Never plug imbalances | Done | Bridge reconciles exactly by construction; checks fail rather than force |
| Fictional data, clearly labelled | Done | Cover sheets, PDFs, UI footer, lesson text |
| Automated tests | Done | 158 passing (`docs/TEST_REPORT.md`) |
| pandas | Not used | Deliberately omitted (see KNOWN_LIMITATIONS) |
| Documentation | Done | README, ARCHITECTURE, FORMULA_REFERENCE, KNOWN_LIMITATIONS, TROUBLESHOOTING, TEST_REPORT |

## Release steps on Windows

1. Install Python 3.12 64-bit (and optionally Inno Setup 6).
2. `powershell -ExecutionPolicy Bypass -File build\build_windows.ps1`
3. Confirm: tests pass, `dist\selftest\selftest-report.txt` shows five PASS lines, the installer is in
   `dist\installer\`.
4. Launch `dist\FinPilot\FinPilot.exe`, complete onboarding, open a lesson and the Modeling Lab, export a
   workbook and open it in Excel.
5. Install with the installer on a second PC (or a clean user account) and repeat step 4.
