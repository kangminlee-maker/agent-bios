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
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\windows
OutputBaseFilename=agent-bios-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
UninstallDisplayIcon={app}\agent-bios.exe
[Files]
Source: "..\..\dist\windows\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\agent-bios"; Filename: "{app}\agent-bios.exe"; Parameters: "install"; WorkingDir: "{userprofile}"
Name: "{group}\Instructions Studio"; Filename: "{app}\agent-bios.exe"; Parameters: "instructions"; WorkingDir: "{userprofile}"
[Run]
Filename: "{app}\agent-bios.exe"; Parameters: "install"; Description: "Open agent-bios setup"; Flags: postinstall skipifsilent nowait
[UninstallRun]
Filename: "{app}\agent-bios.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated
[Code]
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
var P, Owned, Entry, Updated: String; I: Integer;
begin
  if CurUninstallStep = usPostUninstall then begin
    if RegQueryStringValue(HKCU, 'Software\agent-bios', 'OwnedPath', Owned) and
       (CompareText(Owned, ExpandConstant('{app}')) = 0) then begin
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
    end;
  end;
end;
