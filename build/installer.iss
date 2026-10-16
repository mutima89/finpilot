; Inno Setup 6 script for FinPilot. Built by build\build_windows.ps1 after PyInstaller.
; Per-user install (no administrator rights needed). Progress data lives in %APPDATA%\FinPilot
; and is NOT removed on uninstall, so reinstalling keeps the learner's progress.

#define AppName "FinPilot"
#define AppVersion "1.0.0"

[Setup]
AppId={{8C1B7E4E-5B7A-4F7B-9E59-2F1D0C9A6F31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=FinPilot
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=FinPilot-Setup-{#AppVersion}
SetupIconFile=..\src\finpilot\assets\finpilot.ico
UninstallDisplayIcon={app}\FinPilot.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\FinPilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\FinPilot.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\FinPilot.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FinPilot.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
