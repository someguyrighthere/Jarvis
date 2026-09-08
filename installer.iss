#define AppName "JARVIS"
#define AppVersion "1.0.0"
#define AppPublisher "JARVIS"
#define AppExeName "Jarvis.exe"

[Setup]
AppId={{A4D0A6D5-8A20-4B22-9B1D-7E4D8B9D3C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\JARVIS
DefaultGroupName={#AppName}
OutputDir=dist\installer
OutputBaseFilename=JARVIS-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
Uninstallable=yes

[Files]
Source: "dist\JarvisPackage\Jarvis.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\JarvisPackage\Alam_data.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "dist\JarvisPackage\input.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "dist\JarvisPackage\log.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "dist\JarvisPackage\schedule.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "dist\JarvisPackage\voice_state.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\JARVIS"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\JARVIS"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch JARVIS"; Flags: nowait postinstall skipifsilent
