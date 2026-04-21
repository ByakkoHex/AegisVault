# AegisVault — Roadmap

Poniżej rozpisane kierunki rozwoju projektu po wersji 1.0.

---

## 1. Natywna wersja macOS

Aplikacja działa jako `.app` bundle (PyInstaller), ale wymaga dopracowania przed publiczną dystrybucją.

### Problemy do rozwiązania

- [ ] **Gatekeeper** — aplikacja blokowana jako „nieznany deweloper"; docelowo podpisanie kodu (Apple Developer ID) + notaryzacja
- [ ] Tymczasowe obejście: skrypt `.command` „Zezwól na uruchomienie" — zastąpić właściwym codesigning
- [ ] Wygląd UI — fonty, odstępy i zaokrąglenia wyglądają inaczej niż na Windows; wymaga testów i korekty
- [ ] HiDPI / Retina — skalowanie ikon i hexagonów do weryfikacji na ekranach 2×
- [ ] Windows Hello → zastąpić **Touch ID** (`LocalAuthentication` framework)
- [ ] Autostart → `LaunchAgent` plist zamiast rejestru Windows
- [ ] Tray icon — `pystray` na macOS wymaga oddzielnego wątku dla `AppKit`
- [ ] Przetestować na macOS 13 Ventura, 14 Sonoma, 15 Sequoia
- [ ] DMG z tłem graficznym + animacją „przeciągnij do Applications"
- [ ] Podpisanie kodu (Apple Developer ID) — wymagane do normalnej dystrybucji poza App Store

---

## 2. Wtyczka przeglądarkowa *(szkielet gotowy — w trakcie dopracowania)*

Szkielet już istnieje w `extension/` i `native_host/`, ale nie był jeszcze rozwijany.

### Co do zrobienia

**Native Messaging Host** (`native_host/`)
- [ ] Protokół JSON komunikacji host ↔ rozszerzenie (stdin/stdout)
- [ ] Metody: `get_credentials(url)`, `fill_credentials(url, login, password)`, `list_entries()`
- [ ] Szyfrowanie połączenia między hostem a przeglądarką (nonce + klucz sesji)
- [ ] Auto-lock hosta gdy aplikacja desktop jest zablokowana

**Rozszerzenie** (`extension/`)
- [ ] Popup z listą pasujących haseł dla aktywnej domeny
- [ ] Autouzupełnianie formularzy logowania (login + hasło)
- [ ] Ikona w pasku z licznikiem zapisanych haseł dla domeny
- [ ] Obsługa stron z niestandardowymi selektorami (np. wieloetapowy login)
- [ ] Generator haseł bezpośrednio w popup
- [ ] Zapis nowych danych logowania po wykryciu wypełnionego formularza

**Wsparcie przeglądarek**
- [ ] Chrome / Edge (manifest v3)
- [ ] Firefox (manifest v2 → v3 migration)

---

## 3. Aplikacja mobilna

Nowa aplikacja, niezależna od desktopa — synchronizacja przez wspólny serwer.

### Stack

| Warstwa | Technologia |
|---|---|
| Framework | Flutter (iOS + Android z jednego kodu) |
| Krypto | `cryptography` via Dart FFI lub `flutter_sodium` |
| Baza lokalna | SQLite (`sqflite`) |
| Sync | REST API / WebSocket do serwera AegisVault |
| Biometria | `local_auth` (Face ID, odcisk palca) |

### Funkcje

**Podstawowe**
- [ ] Logowanie masterhasłem + 2FA (TOTP)
- [ ] Biometria jako szybki unlock (Face ID / fingerprint)
- [ ] Lista haseł z wyszukiwaniem i kategoriami
- [ ] Podgląd, kopiowanie, ukrywanie hasła
- [ ] Generator haseł

**Synchronizacja**
- [ ] Auto-sync z serwerem przy otwarciu aplikacji
- [ ] Sync w tle (push notification o zmianach)
- [ ] Tryb offline — pełna funkcjonalność bez internetu, sync przy reconnect
- [ ] Rozwiązywanie konfliktów (nowszy timestamp wygrywa)

**Zaawansowane**
- [ ] TOTP Authenticator wbudowany w aplikację (jak Google Authenticator)
- [ ] Udostępnianie haseł między urządzeniami (E2E encrypted)
- [ ] Apple Watch / Wear OS — szybkie kopiowanie haseł z zegarka
- [ ] Import z 1Password, Bitwarden, LastPass (już jest na desktopie)

---

## 4. Rejestracja przez email + weryfikacja SMS

Dotyczy zarówno serwera publicznego jak i self-hosted.

### Rejestracja emailem

**Flow**
1. Użytkownik wpisuje email + masterhasło (hash po stronie klienta, nigdy plaintext)
2. Serwer wysyła link aktywacyjny (JWT z TTL 24h)
3. Po kliknięciu konto aktywne
4. Opcjonalnie: weryfikacja przez SMS jako drugi czynnik przy aktywacji

**Co potrzebne**
- [ ] Endpoint `POST /auth/register` z walidacją emaila
- [ ] Endpoint `GET /auth/verify/{token}` — aktywacja konta
- [ ] Endpoint `POST /auth/resend-verification` — ponowne wysłanie maila
- [ ] Template HTML emaila (logo, przycisk aktywacji)
- [ ] Integracja SMTP: SendGrid / Mailgun / własny serwer

### Weryfikacja SMS (2FA przez kod)

**Flow**
1. Po zalogowaniu masterhasłem → serwer wysyła kod SMS (6 cyfr, TTL 5 min)
2. Użytkownik wpisuje kod w aplikacji
3. Opcja: "Zapamiętaj to urządzenie na 30 dni"

**Co potrzebne**
- [ ] Endpoint `POST /auth/sms/send` — wyślij kod na numer
- [ ] Endpoint `POST /auth/sms/verify` — zweryfikuj kod
- [ ] Integracja SMS gateway: Twilio / Vonage / SMSAPI (PL)
- [ ] Przechowywanie numerów telefonów (zaszyfrowane w bazie)
- [ ] Rate limiting — max 3 próby, cooldown 15 min po przekroczeniu
- [ ] Opcja w ustawieniach: włącz/wyłącz SMS 2FA, zmień numer

### Reset hasła

- [ ] `POST /auth/reset-password/request` — wyślij link resetujący
- [ ] `POST /auth/reset-password/confirm` — nowe masterhasło
- [ ] Ostrzeżenie: zmiana masterhasła = re-szyfrowanie całej bazy

---

## 5. Publiczny serwer AegisVault

Zamiast każdy hostuje lokalnie — jeden serwer w chmurze, każdy ma swoje konto.

### Architektura

```
[Klient desktop / mobile / extension]
            │  HTTPS + E2E encryption
            ▼
    [Load Balancer / Nginx]
            │
    [FastAPI App Servers]  ←── horizontal scaling
            │
    [PostgreSQL]  +  [Redis (cache/sessions)]
            │
    [S3-compatible storage]  ←── zaszyfrowane backupy
```

### Kluczowe zasady bezpieczeństwa

- **Zero-knowledge** — serwer nigdy nie widzi masterhasła ani plaintext haseł
- Szyfrowanie po stronie klienta (AES-256-GCM) przed wysłaniem
- Serwer przechowuje tylko zaszyfrowane blobs + metadane
- TLS 1.3 obowiązkowy, HSTS

### Co potrzebne po stronie serwera

**Infrastruktura**
- [ ] Migracja z SQLite → PostgreSQL
- [ ] Docker + docker-compose dla łatwego deploy
- [ ] Konfiguracja przez zmienne środowiskowe (`.env`)
- [ ] Health check endpoint `GET /health`
- [ ] Logi strukturalne (JSON) → Loki / CloudWatch

**Konta i auth**
- [ ] Rejestracja emailem (patrz sekcja 3)
- [ ] JWT access token (15 min) + refresh token (30 dni)
- [ ] Blacklista unieważnionych tokenów w Redis
- [ ] Limity kont: darmowy (do 100 haseł), premium (bez limitu)

**Sync i dane**
- [ ] Endpoint `GET /vault` — pobierz zaszyfrowany vault
- [ ] Endpoint `PUT /vault` — wyślij zaktualizowany vault (wersjonowanie)
- [ ] Obsługa konfliktów: vector clock lub last-write-wins
- [ ] Backupy automatyczne (codziennie, 30 dni historii)
- [ ] Eksport danych na żądanie (RODO)
- [ ] Usunięcie konta + wszystkich danych na żądanie

**Admin panel**
- [ ] Statystyki: liczba użytkowników, aktywność, błędy
- [ ] Zarządzanie kontami (ban, reset hasła, usunięcie)
- [ ] Aktualizacja `app_version.json` przez panel (wyzwala auto-update u klientów)

### Możliwy hosting

| Opcja | Koszt startowy | Skalowalność |
|---|---|---|
| VPS (Hetzner/OVH) | ~5-15 EUR/mies | Ręczna |
| Railway / Render | Free tier → pay-as-you-go | Automatyczna |
| AWS / GCP / Azure | Free tier → pay-per-use | Pełna |
| Własny serwer | Jednorazowy hardware | Ograniczona |

### Self-hosted vs publiczny

Zachować możliwość **self-hosted** dla zaawansowanych użytkowników — `server/` w repo + instrukcja Docker. Publiczny serwer jako domyślna opcja w ustawieniach.

---

## Priorytety (sugerowana kolejność)

```
[1] Serwer publiczny        ← podstawa dla wszystkiego poniżej
[2] Rejestracja emailem     ← żeby można było tworzyć konta online
[3] SMS 2FA                 ← bezpieczeństwo kont
[4] Wtyczka przeglądarkowa  ← największy wzrost użyteczności na desktopie
[5] Natywna wersja macOS    ← podpisanie kodu + dopracowanie UI
[6] Aplikacja mobilna       ← największy nakład pracy, ale i zasięgu
```
