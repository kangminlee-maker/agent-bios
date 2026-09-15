#ifndef AppVersion
#define AppVersion "0.19.2"
#endif
[Setup]
AppId=agent-bios-native-windows
AppName=agent-bios
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\agent-bios
DefaultGroupName=agent-bios
PrivilegesRequired=lowest
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\windows
OutputBaseFilename=agent-bios-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
UninstallDisplayIcon={app}\agent-bios.exe
[Messages]
FinishedLabel=agent-bios is installed. Open a new PowerShell window to use its commands, or open setup below.
[Files]
Source: "..\..\dist\windows\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\agent-bios"; Filename: "{app}\agent-bios.exe"; Parameters: "install"; WorkingDir: "{userdocs}"
Name: "{group}\Instructions Studio"; Filename: "{app}\agent-bios.exe"; Parameters: "instructions"; WorkingDir: "{userdocs}"
[Run]
Filename: "{app}\agent-bios.exe"; Parameters: "install"; Description: "Open agent-bios setup"; Flags: postinstall skipifsilent nowait
[Code]
var OwnedPathToRemove: String;
function InitializeUninstall(): Boolean;
var ExitCode: Integer; Owned: String;
begin
  OwnedPathToRemove := '';
  if RegQueryStringValue(HKCU, 'Software\agent-bios', 'OwnedPath', Owned) then
    if CompareText(GetShortName(Owned), GetShortName(ExpandConstant('{app}'))) = 0 then
      OwnedPathToRemove := Owned;
  Log('Owned PATH entry selected before removal: ' + OwnedPathToRemove);
  Result := Exec(ExpandConstant('{app}\agent-bios.exe'), 'uninstall --dry-run', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  if Result then Result := ExitCode = 0;
  if not Result then
    SuppressibleMsgBox('agent-bios could not safely detach its private runtime. Run agent-bios uninstall in a terminal, resolve the reported issue, then retry.', mbError, MB_OK, IDOK);
end;
procedure CurStepChanged(CurStep: TSetupStep);
var P, Entry: String;
begin
  if CurStep = ssPostInstall then begin
    Entry := ExpandConstant('{app}');
    RegQueryStringValue(HKCU, 'Environment', 'Path', P);
    if Pos(';' + Lowercase(Entry) + ';', ';' + Lowercase(P) + ';') = 0 then begin
      if (P <> '') and (Copy(P, Length(P), 1) <> ';') then P := P + ';';
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', P + Entry);
      RegWriteStringValue(HKCU, 'Software\agent-bios', 'OwnedPath', Entry);
    end;
  end;
end;
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var P, Owned, Entry, Updated: String; I, ExitCode: Integer;
begin
  if CurUninstallStep = usUninstall then begin
    if not Exec(ExpandConstant('{app}\agent-bios.exe'), 'uninstall', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      RaiseException('Could not start private runtime removal; program files were not removed.');
    if ExitCode <> 0 then
      RaiseException('Private runtime removal failed; program files were not removed.');
  end;
  if CurUninstallStep = usPostUninstall then begin
    if RegQueryStringValue(HKCU, 'Software\agent-bios', 'OwnedPath', Owned) and
       (OwnedPathToRemove <> '') and (CompareText(Owned, OwnedPathToRemove) = 0) then begin
      RegQueryStringValue(HKCU, 'Environment', 'Path', P);
      Updated := '';
      while P <> '' do begin
        I := Pos(';', P);
        if I = 0 then begin Entry := P; P := ''; end
        else begin Entry := Copy(P, 1, I - 1); Delete(P, 1, I); end;
        if CompareText(Entry, Owned) <> 0 then begin
          if Updated <> '' then Updated := Updated + ';';
          Updated := Updated + Entry;
        end;
      end;
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Updated);
      RegDeleteValue(HKCU, 'Software\agent-bios', 'OwnedPath');
      Log('Removed owned PATH entry: ' + Owned);
    end;
  end;
end;
