#ifndef AppVersion
#define AppVersion "6.3.1"
#endif

#define AppName "Nishizumi Paints"
#define AppPublisher "Nishizumi Paints"
#define AppExeName "NishizumiPaints.exe"
[Setup]
AppId={{7F0E27E1-89E3-4F3A-8C6F-8E1F9E5A5B4D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Nishizumi Paints
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\icons\nishizumi_paints_icon.ico
OutputDir=output
OutputBaseFilename=NishizumiPaints-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Start Nishizumi Paints when I sign in"; GroupDescription: "Startup options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{app}\{#AppExeName}"
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\embedded_browser"
Type: filesandordirs; Name: "{app}\browser"
Type: filesandordirs; Name: "{app}\chrome"
Type: filesandordirs; Name: "{app}\chrome_runtime"
Type: filesandordirs; Name: "{app}\chrome-portable"
Type: filesandordirs; Name: "{app}\ms-playwright"
Type: filesandordirs; Name: "{app}\playwright"

[Files]
Source: "..\dist\NishizumiPaints\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NishizumiPaints"; ValueData: """{app}\{#AppExeName}"" --autostart-launched"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "NishizumiPaints"; Flags: deletevalue; Check: not WizardIsTaskSelected('autostart')
Root: HKCU; Subkey: "Software\NishizumiPaints"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "1"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\NishizumiPaints"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "0"; Check: not WizardIsTaskSelected('autostart'); Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\embedded_browser"
Type: filesandordirs; Name: "{app}\browser"
Type: filesandordirs; Name: "{app}\chrome"
Type: filesandordirs; Name: "{app}\chrome_runtime"
Type: filesandordirs; Name: "{app}\chrome-portable"
Type: filesandordirs; Name: "{app}\ms-playwright"
Type: filesandordirs; Name: "{app}\playwright"
