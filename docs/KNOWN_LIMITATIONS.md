# Known limitations (FinPilot 1.0.0)

Stated plainly so nobody relies on something that is not there.

## Build and platform

- **The Windows .exe and installer have not been built or run on Windows yet.** The development
  environment was Linux. What *was* verified: the PyInstaller spec builds a working one-folder app on Linux
  and that packaged app passes its own `--self-test`; the PowerShell build script parses without errors;
  Windows 64-bit wheels for every pinned dependency exist for Python 3.12. Run `build\build_windows.ps1` on
  Windows to produce and self-test `FinPilot.exe` (see README).
- The .exe is not code-signed. Windows SmartScreen may warn on first run ("More info" → "Run anyway"), and
  some antivirus products flag unsigned PyInstaller apps. Signing needs a code-signing certificate.
- The UI was tested with Qt's offscreen platform at 1000x640, 1024x700, 1366x768 and 1920x1080. It has not
  been checked on a physical Windows display, with Windows display scaling above 100%, or with a screen
  reader.

## Curriculum scope

- Levels 1-3 are complete. Level 4 (Hotel Revenue Management) is a preview: the group displacement simulator
  works, but there are no Level 4 lessons yet. Levels 5-10 are shown on the map as planned.
- Written answers are checked against a transparent rubric for the presence of required elements
  (a recommendation, numbers, a risk, an action). FinPilot cannot judge the quality of reasoning; the UI says
  so and shows a model answer to compare with.

## Formula engine and spreadsheet

- 56 Excel functions are supported; 33 common others return `#UNSUPPORTED!` (see FORMULA_REFERENCE.md).
  No array formulas or spilled ranges, no iterative calculation (circular references are flagged as
  `#CIRC!`), no cross-sheet references inside the Lab (it is a single sheet).
- The Lab grid is limited to 500 rows x 52 columns. There is no cell merging, conditional formatting, column
  resizing persistence or multi-sheet workbook editing.
- Number formats are a fixed set (general, number, currency, percent, date, text). Currency is shown as USD.

## Excel export

- FinPilot never runs Microsoft Excel. Exported formulas were verified by re-reading them into FinPilot's
  engine and by a LibreOffice headless recalculation (values matched). Opening in Excel itself was not
  tested in this environment. Workbooks are set to recalculate on open.

## Data

- Progress is stored per Windows user in `%APPDATA%\FinPilot`. There is no sync between computers; use
  Settings → Back up now and Restore to move progress.
- Uninstalling keeps progress data (by design). Delete `%APPDATA%\FinPilot` to remove it.

## Stack choices

- pandas is not used: the app's tables are small and the standard library (csv, json) covers the
  exports, which keeps the packaged app smaller. numpy is present as a matplotlib dependency.
- The app installs only `PySide6-Essentials` (not the full PySide6 add-ons), which is all it needs.
