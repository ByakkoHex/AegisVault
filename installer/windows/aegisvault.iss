; aegisvault.iss — Inno Setup Installer Script
; ================================================
; Wymagania:
;   - Inno Setup 6.x  →  https://jrsoftware.org/isinfo.php
;   - Zbudowany PyInstaller output w dist\AegisVault\  (pyinstaller aegisvault.spec)
;
; Budowanie:
;   iscc /DAppVersion=1.0.1 installer\windows\aegisvault.iss
;   — lub —
;   powershell -File installer\build_all.ps1

#ifndef AppVersion
  #define AppVersion "1.1"
#endif

#define AppName        "AegisVault"
#define AppPublisher   "AegisVault"
#define AppURL         "https://github.com/twoj-nick/aegisvault"
#define AppExeName     "AegisVault.exe"
#define ProjectRoot    "..\..\"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instalacja per-user — nie wymaga UAC / uprawnień administratora
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#ProjectRoot}dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
; Ikona — użyj jeśli istnieje, pomiń jeśli nie
#if FileExists(ProjectRoot + "assets\icon.ico")
SetupIconFile={#ProjectRoot}assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
#endif
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=100
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64
; Python NIE jest wymagany — wszystko bundlowane przez PyInstaller

; ── Obsługa aktualizacji ───────────────────────────────────────────────────
; Ten sam AppId = Inno Setup wykrywa poprzednią instalację i ją nadpisuje
; zamiast instalować obok. Użytkownik dostaje "Wykryto poprzednią wersję —
; czy chcesz ją zaktualizować?" zamiast drugiej pozycji w Dodaj/Usuń programy.
AppMutex=AegisVaultRunning
; Zamknij aplikację przed aktualizacją jeśli jest uruchomiona
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no
; Nadpisuj pliki bez pytania (aktualizacja)
VersionInfoVersion={#AppVersion}

[Languages]
Name: "polish";   MessagesFile: "compiler:Languages\Polish.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";      Description: "Utwórz ikonę na pulpicie";                          GroupDescription: "Ikony:";                Flags: checkedonce
Name: "autostart";        Description: "Uruchamiaj AegisVault automatycznie po zalogowaniu"; GroupDescription: "Uruchamianie:";         Flags: unchecked
Name: "register_browser"; Description: "Zarejestruj wtyczkę przeglądarkową (autouzupełnianie)"; GroupDescription: "Integracja:";       Flags: unchecked

[Files]
; Główna aplikacja — cały bundle PyInstaller (Python + biblioteki wbudowane)
Source: "{#ProjectRoot}dist\AegisVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Native host — dla opcjonalnej integracji z przeglądarką
Source: "{#ProjectRoot}native_host\*";  DestDir: "{app}\native_host"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: register_browser
Source: "{#ProjectRoot}core\*";         DestDir: "{app}\core";        Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: register_browser
Source: "{#ProjectRoot}database\*";     DestDir: "{app}\database";    Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: register_browser
Source: "{#ProjectRoot}utils\*";        DestDir: "{app}\utils";       Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: register_browser

; Skrypt PowerShell do rejestracji native host (opcjonalny)
Source: "{#ProjectRoot}installer\windows\post_install.ps1";   DestDir: "{app}"; Flags: ignoreversion; Tasks: register_browser
; Skrypt czyszczenia przy deinstalacji (zawsze dołączany)
Source: "{#ProjectRoot}installer\windows\post_uninstall.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"
Name: "{group}\Odinstaluj {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
; Autostart — klucz rejestru HKCU (per-user, bez UAC)
Name: "{userstartup}\{#AppName}";      Filename: "{app}\{#AppExeName}"; Tasks: autostart

[Run]
; Rejestracja native messaging host (opcjonalna, tylko jeśli zaznaczono)
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -File ""{app}\post_install.ps1"" ""{app}"""; \
  Flags: runhidden waituntilterminated; \
  Tasks: register_browser; \
  StatusMsg: "Rejestrowanie integracji z przeglądarką..."

; Opcjonalne uruchomienie po instalacji
Filename: "{app}\{#AppExeName}"; \
  Description: "Uruchom {#AppName} teraz"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Uruchom skrypt czyszczący (native hosts, autostart, Credential Manager)
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -File ""{app}\post_uninstall.ps1"""; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "PostUninstallCleanup"

[Code]
var
  IsUpdate: Boolean;
  PreviousVersion: String;

function GetPreviousVersion(): String;
var
  RegKey: String;
begin
  RegKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}_is1';
  Result := '';
  if not RegQueryStringValue(HKCU, RegKey, 'DisplayVersion', Result) then
    RegQueryStringValue(HKLM, RegKey, 'DisplayVersion', Result);
end;

function InitializeSetup(): Boolean;
begin
  PreviousVersion := GetPreviousVersion();
  IsUpdate := PreviousVersion <> '';
  Result := True;
end;

procedure InitializeWizard();
begin
  if IsUpdate then
  begin
    WizardForm.Caption := 'Aktualizacja {#AppName} do wersji {#AppVersion}';
    WizardForm.WelcomeLabel1.Caption := 'Aktualizacja {#AppName}';
    WizardForm.WelcomeLabel2.Caption :=
      'Kreator zaktualizuje {#AppName} z wersji ' + PreviousVersion +
      ' do wersji {#AppVersion}.' + #13#10#13#10 +
      'Twoje hasła i ustawienia pozostaną niezmienione.' + #13#10#13#10 +
      'Kliknij Dalej, aby rozpocząć aktualizację.';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataPath: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    AppDataPath := ExpandConstant('{userappdata}\AegisVault');
    if DirExists(AppDataPath) then
    begin
      if MsgBox(
        'Czy usunąć dane aplikacji?' + #13#10 +
        '(baza haseł, ustawienia)' + #13#10 + #13#10 +
        'Lokalizacja: ' + AppDataPath + #13#10 + #13#10 +
        'Wybierz NIE, aby zachować dane przy ponownej instalacji.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(AppDataPath, True, True, True);
      end;
    end;
  end;
end;
