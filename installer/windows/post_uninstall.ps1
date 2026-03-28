# post_uninstall.ps1 — Sprzątanie po deinstalacji AegisVault
# Wywoływany automatycznie przez Inno Setup przed usunięciem plików.

$ErrorActionPreference = "Continue"

Write-Host "=== AegisVault — Czyszczenie po deinstalacji ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. Usuń native messaging hosty ze wszystkich przeglądarek ─────────────
$NativeHostKeys = @(
    "HKCU:\SOFTWARE\Google\Chrome\NativeMessagingHosts\com.aegisvault.host",
    "HKCU:\SOFTWARE\Chromium\NativeMessagingHosts\com.aegisvault.host",
    "HKCU:\SOFTWARE\Microsoft\Edge\NativeMessagingHosts\com.aegisvault.host",
    "HKCU:\SOFTWARE\Mozilla\NativeMessagingHosts\com.aegisvault.host"
)
foreach ($key in $NativeHostKeys) {
    if (Test-Path $key) {
        Remove-Item $key -Force -Recurse -ErrorAction SilentlyContinue
        Write-Host "[OK] Usunięto klucz przeglądarki: $key" -ForegroundColor Green
    }
}

# ── 2. Usuń wpis autostart (jeśli Inno Setup go nie posprzątał) ───────────
$AutostartPath = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $AutostartPath -Name "AegisVault" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $AutostartPath -Name "AegisVault" -ErrorAction SilentlyContinue
    Write-Host "[OK] Usunięto wpis autostart" -ForegroundColor Green
}

# ── 3. Wyczyść Windows Credential Manager (Windows Hello / keyring) ────────
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public class AegisCredClean {
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CredEnumerate(string filter, int flags, out int count, out IntPtr pCreds);
    [DllImport("advapi32.dll")]
    static extern void CredFree(IntPtr creds);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool CredDelete(string target, uint type, uint flags);

    public static void DeleteAll(string filter) {
        int count; IntPtr pCreds;
        if (!CredEnumerate(filter, 0, out count, out pCreds)) return;
        var targets = new List<string>();
        try {
            for (int i = 0; i < count; i++) {
                IntPtr pCred = Marshal.ReadIntPtr(pCreds, i * IntPtr.Size);
                // CREDENTIAL struct: Flags(4) + Type(4) = offset 8 => TargetName pointer
                IntPtr pTarget = Marshal.ReadIntPtr(pCred, 8);
                string target = Marshal.PtrToStringUni(pTarget);
                if (target != null) targets.Add(target);
            }
        } finally { CredFree(pCreds); }
        foreach (var t in targets) {
            CredDelete(t, 1, 0);
        }
    }
}
'@ -ErrorAction SilentlyContinue

try {
    [AegisCredClean]::DeleteAll("AegisVault*")
    Write-Host "[OK] Wyczyszczono Windows Credential Manager" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Nie udało się wyczyścić Credential Manager: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[OK] Czyszczenie zakończone." -ForegroundColor Green
