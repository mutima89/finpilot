# Troubleshooting

## Building on Windows

| Problem | Fix |
|---|---|
| `Python not found` | Install Python 3.12 **64-bit** from python.org. Tick "Add python.exe to PATH" and keep the "py launcher" option. Then re-run. To use another interpreter: `-Python "C:\Path\python.exe"`. |
| `running scripts is disabled on this system` | Run the script as shown: `powershell -ExecutionPolicy Bypass -File build\build_windows.ps1` (affects only that run). |
| pip cannot download packages | The build needs internet once to fetch the pinned wheels. Behind a proxy, set `HTTPS_PROXY` first. After that, FinPilot itself runs offline. |
| A test fails during the build | The build stops on purpose. The failing test name and message are printed; `dist\test-results.xml` has details. Use `-SkipTests` only to investigate, never for a release. |
| `Packaged self-test FAILED` | Read `dist\selftest\selftest-report.txt`: each line says PASS or FAIL and why. A missing-file error usually means the spec's `datas` were edited. |
| Inno Setup not found | Optional. Install Inno Setup 6 and re-run to get `FinPilot-Setup-1.0.0.exe`; otherwise use the portable folder `dist\FinPilot\`. |
| Antivirus quarantines `FinPilot.exe` | Unsigned PyInstaller apps are sometimes flagged. UPX is disabled to reduce this. Restore the file and add an exclusion for the build folder, or sign the exe. |

## Running FinPilot

| Problem | Fix |
|---|---|
| SmartScreen "Windows protected your PC" | The app is not code-signed. Click **More info** → **Run anyway**. |
| "Progress database was damaged" on start | FinPilot found a damaged database, moved it aside (file name shown) and started fresh. Restore your latest backup from **Settings → Restore from backup…**. |
| A project will not open | The message names the problem (empty, damaged, not a FinPilot file, newer version). Every save keeps the previous version as `<name>.finpilot.bak`: rename it to `.finpilot` and open it. |
| "File was changed outside FinPilot" | The file opened, but its checksum did not match, so it was edited by hand or partly damaged. Review the Checks tab before relying on it. |
| The Lab lost my work | Autosave keeps a recovery copy in `%APPDATA%\FinPilot\autosave\current.finpilot`, which reopens automatically. |
| Exported workbook shows blank or zero values | Open it in Excel (it recalculates on open) or press F9. Some previewers do not calculate formulas. |
| A formula shows `#UNSUPPORTED!` | That Excel function is not in FinPilot's engine; see FORMULA_REFERENCE.md for supported alternatives. |
| Text is too small or too large | Windows display scaling applies; FinPilot follows it. |
| Something unexpected happened | Logs are in `%APPDATA%\FinPilot\logs\finpilot.log` (rotated, local only, never sent anywhere). |

## Where things are

- Progress database, logs, autosave, backups: `%APPDATA%\FinPilot`
- Projects and exports (default): `Documents\FinPilot Projects`
- Developers can redirect all data with the `FINPILOT_HOME` environment variable (the tests do this).

## Headless self-test

`FinPilot.exe --self-test C:\temp\fp` builds every screen, validates the curriculum and the reference hotel
model, writes an Excel workbook and a PDF, and writes `selftest-report.txt` in that folder. Exit code 0 means
every check passed. It uses a temporary data folder, so real progress is untouched.
