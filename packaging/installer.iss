; Inno Setup script for Zenith Business ERP (test installer)
; Build:  iscc packaging\installer.iss
; Installs the one-folder PyInstaller output. Customer data lives under
; %PROGRAMDATA%\ZenithBusinessERP and is NOT removed on uninstall.

#define AppName "Zenith Business ERP"
#define AppVersion "0.1.0"
#define Publisher "Zenith Software"
#define ExeName "ZenithBusinessERP.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\ZenithBusinessERP
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=ZenithBusinessERP-Test-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
; SetupIconFile=app.ico

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\ZenithBusinessERP\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
; Persistent customer data directory, preserved across upgrades/uninstall.
Name: "{commonappdata}\ZenithBusinessERP"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Intentionally empty: never delete {commonappdata}\ZenithBusinessERP (customer data).
