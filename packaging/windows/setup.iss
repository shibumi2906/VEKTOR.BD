#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
[Setup]
AppId={{5E124DF5-0FBB-4EBF-B822-80E1D8B9F1C2}
AppName=PinuiRAG
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\PinuiRAG
DefaultGroupName=PinuiRAG
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=PinuiRAG-Setup-Windows-x64
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
UninstallDisplayIcon={app}\PinuiRAG.exe
CloseApplications=yes
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\PinuiRAG"; Filename: "{app}\PinuiRAG.exe"
Name: "{autodesktop}\PinuiRAG"; Filename: "{app}\PinuiRAG.exe"
[Run]
Filename: "{app}\PinuiRAG.exe"; Description: "Открыть PinuiRAG"; Flags: nowait postinstall skipifsilent
