; Inno Setup script for the OMR Checker installer, run by packaging/build.py:
;   ISCC /DAppVersion=1.0.0 /DSourceDir=<PyInstaller "OMR Checker" folder> /O<output dir> windows-installer.iss
; Installs for the current user (no admin), adds Start menu and optional desktop
; shortcuts, and an uninstaller. Scans and results stay in %LOCALAPPDATA%\OMR Checker.

#define AppName "OMR Checker"

[Setup]
AppId={{FBBEB596-0D14-4A25-828B-EC9001F3F9AE}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Debanshu Ghosh and Aravind Sathesh
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=OMR-Checker-{#AppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppName}.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; stop a running copy so its files can be removed
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""{#AppName}.exe"""; Flags: runhidden; RunOnceId: "StopApp"
