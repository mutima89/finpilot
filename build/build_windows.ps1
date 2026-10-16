<#
FinPilot Windows build script (Windows 10/11, 64-bit).

What it does, in order:
  1. Creates a clean virtual environment in .venv-build with Python 3.12 (64-bit).
  2. Installs the pinned dependencies from requirements-dev.txt.
  3. Runs the full automated test suite (stops if any test fails).
  4. Builds dist\FinPilot\FinPilot.exe with PyInstaller (build\finpilot.spec).
  5. Runs the packaged exe's headless self-test and checks its report.
  6. If Inno Setup 6 is installed, builds dist\installer\FinPilot-Setup-1.0.0.exe.
  7. Writes SHA-256 checksums of the outputs.

Usage (from the repository root, in PowerShell):
    powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
Options:
    -SkipTests      skip step 3 (not recommended)
    -Python "py -3.12"   the Python launcher command to use
#>
param(
    [switch]$SkipTests,
    [string]$Python = "py -3.12"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$root = Get-Location
Write-Host "FinPilot build in $root" -ForegroundColor Cyan

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Run($exe, [string[]]$argList) {
    & $exe @argList
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $exe $($argList -join ' ')" }
}

Step "1/7 Checking Python"
$pyParts = $Python.Split(" ")
$pyExe = $pyParts[0]
$pyArgs = @()
if ($pyParts.Length -gt 1) { $pyArgs = $pyParts[1..($pyParts.Length - 1)] }
$info = & $pyExe @pyArgs -c "import sys, struct; print(sys.version.split()[0], struct.calcsize('P')*8)"
if ($LASTEXITCODE -ne 0) { throw "Python not found. Install Python 3.12 (64-bit) from python.org and tick 'Add to PATH' / 'py launcher'." }
Write-Host "Python $info"
if (-not $info.EndsWith(" 64")) { throw "A 64-bit Python is required." }

Step "2/7 Creating virtual environment and installing pinned dependencies"
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
Run $pyExe ($pyArgs + @("-m", "venv", ".venv-build"))
$venvPy = Join-Path $root ".venv-build\Scripts\python.exe"
Run $venvPy @("-m", "pip", "install", "--upgrade", "pip")
Run $venvPy @("-m", "pip", "install", "-r", "requirements-dev.txt")

if (-not $SkipTests) {
    Step "3/7 Running the automated test suite"
    $env:QT_QPA_PLATFORM = "offscreen"
    Run $venvPy @("-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "--junitxml", "dist\test-results.xml")
    Remove-Item Env:\QT_QPA_PLATFORM
} else {
    Write-Host "Tests skipped (-SkipTests)." -ForegroundColor Yellow
}

Step "4/7 Building FinPilot.exe with PyInstaller"
if (Test-Path dist\FinPilot) { Remove-Item -Recurse -Force dist\FinPilot }
Run $venvPy @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build\_work",
              "build\finpilot.spec")
$exePath = Join-Path $root "dist\FinPilot\FinPilot.exe"
if (-not (Test-Path $exePath)) { throw "PyInstaller did not produce $exePath" }

Step "5/7 Self-testing the packaged exe"
$st = Join-Path $root "dist\selftest"
if (Test-Path $st) { Remove-Item -Recurse -Force $st }
$p = Start-Process -FilePath $exePath -ArgumentList @("--self-test", "`"$st`"") -Wait -PassThru
$report = Join-Path $st "selftest-report.txt"
if (Test-Path $report) { Get-Content $report | Write-Host }
if ($p.ExitCode -ne 0 -or -not (Test-Path $report)) { throw "Packaged self-test FAILED (exit code $($p.ExitCode))." }
Write-Host "Packaged self-test passed." -ForegroundColor Green

Step "6/7 Building the installer (Inno Setup 6, optional)"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    Run $iscc @("build\installer.iss")
    Write-Host "Installer: dist\installer\FinPilot-Setup-1.0.0.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup 6 not found: skipping the installer. The portable app is in dist\FinPilot\." -ForegroundColor Yellow
    Write-Host "Install it from https://jrsoftware.org/isdl.php and re-run to also get an installer."
}

Step "7/7 Writing checksums"
$outs = @($exePath) + (Get-ChildItem dist\installer\*.exe -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$outs | ForEach-Object { Get-FileHash $_ -Algorithm SHA256 } | Format-Table -AutoSize | Out-String |
    Set-Content dist\SHA256SUMS.txt
Get-Content dist\SHA256SUMS.txt
Write-Host "`nDone. Run dist\FinPilot\FinPilot.exe" -ForegroundColor Green
