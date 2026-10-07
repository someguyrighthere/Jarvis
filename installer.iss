#define AppName "SARA"
#define AppVersion "2.0.0"
#define AppPublisher "SARA"
#define AppExeName "Jarvis.exe"
#ifndef PackageRoot
  #define PackageRoot "dist\JarvisPackage"
#endif

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

[Tasks]
Name: "chrome"; Description: "Install Chrome for voice recognition if missing"; GroupDescription: "Optional voice and local AI setup (downloads software; package licenses apply):"; Flags: unchecked
Name: "ollama"; Description: "Install Ollama for local AI responses if missing"; GroupDescription: "Optional voice and local AI setup (downloads software; package licenses apply):"; Flags: unchecked
Name: "saramodel"; Description: "Download SARA's AI model (requires Ollama; potentially several GB)"; GroupDescription: "Optional voice and local AI setup (downloads software; package licenses apply):"; Flags: unchecked
Name: "coding"; Description: "Enable coding features: install Forge 1.4.1+ and its AI model (requires Ollama; several GB)"; GroupDescription: "Optional coding setup:"; Flags: unchecked

[Files]
Source: "{#PackageRoot}\Jarvis.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageRoot}\Alam_data.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#PackageRoot}\input.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#PackageRoot}\log.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#PackageRoot}\schedule.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#PackageRoot}\voice_state.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#PackageRoot}\models\piper\en_GB-alba-medium.onnx"; DestDir: "{app}\models\piper"; Flags: ignoreversion
Source: "{#PackageRoot}\models\piper\en_GB-alba-medium.onnx.json"; DestDir: "{app}\models\piper"; Flags: ignoreversion
Source: "{#PackageRoot}\models\piper\PIPER-VOICE-NOTICE.txt"; DestDir: "{app}\models\piper"; Flags: ignoreversion

[Icons]
Name: "{group}\SARA"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\SARA"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch SARA"; Flags: nowait postinstall skipifsilent

[Code]
procedure AddComponent(var Components: String; Component: String);
begin
  if Components <> '' then
    Components := Components + ',';
  Components := Components + Component;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Components, LogPath, Parameters: String;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Components := '';
  if WizardIsTaskSelected('chrome') then AddComponent(Components, 'chrome');
  if WizardIsTaskSelected('ollama') then AddComponent(Components, 'ollama');
  if WizardIsTaskSelected('saramodel') then AddComponent(Components, 'sara-model');
  if WizardIsTaskSelected('coding') then begin
    AddComponent(Components, 'forge');
    AddComponent(Components, 'forge-model');
  end;
  if Components = '' then
    Exit;
  LogPath := ExpandConstant('{app}\dependency-setup.log');
  Parameters := '--setup-components "' + Components + '" --setup-log "' + LogPath + '"';
  WizardForm.StatusLabel.Caption := 'Setting up selected dependencies. Model downloads can take a long time...';
  if not Exec(ExpandConstant('{app}\{#AppExeName}'), Parameters, ExpandConstant('{app}'),
              SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    MsgBox('SARA was installed, but dependency setup could not start. Use Dependencies to install selected components later.',
           mbError, MB_OK)
  else if ResultCode <> 0 then
    MsgBox('SARA was installed, but some selected dependencies need attention. Check ' + LogPath +
           ' and use Dependencies to retry. Unselected components were not installed.', mbError, MB_OK);
end;
