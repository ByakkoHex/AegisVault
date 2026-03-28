# Dokumentacja wtyczki przeglądarkowej — AegisVault

## Przegląd

Wtyczka AegisVault to rozszerzenie WebExtension Manifest V3 działające w Chrome, Firefox i Edge z jednego kodu źródłowego. Komunikuje się z lokalną bazą danych przez Python Native Messaging Host — dane nigdy nie opuszczają urządzenia.

**Obsługiwane przeglądarki:**

| Przeglądarka | Wersja min | Status |
|--------------|-----------|--------|
| Google Chrome | 88+ | Pełna obsługa |
| Microsoft Edge | 88+ | Pełna obsługa |
| Mozilla Firefox | 109+ | Pełna obsługa (MV3) |

---

## Instalacja

Szczegółowa instrukcja instalacji: [INSTALLATION.md](INSTALLATION.md#instalacja-wtyczki-przeglądarkowej)

Skrócony przebieg:
1. Pobierz `browser-polyfill.js` → `extension/lib/`
2. Załaduj folder `extension/` w przeglądarce (tryb deweloperski)
3. Uruchom `py native_host/install/install.py --extension-id <ID>`

---

## Struktura plików

```
extension/
├── manifest.json                   # Deklaracja rozszerzenia (MV3)
├── background/
│   └── service_worker.js           # Service Worker — zarządzanie sesją i hostem
├── content/
│   ├── content_script.js           # Wykrywanie formularzy, chip autofill
│   └── content_style.css           # Placeholder CSS (style w Shadow DOM)
├── popup/
│   ├── popup.html                  # Struktura interfejsu (3 widoki)
│   ├── popup.js                    # Logika interfejsu
│   └── popup.css                   # Ciemny motyw, 360px szerokości
├── lib/
│   └── browser-polyfill.js         # webextension-polyfill (do pobrania)
└── icons/
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

---

## Architektura i przepływ komunikacji

```
┌─────────────────────────────────────────────────────────────┐
│  PRZEGLĄDARKA                                               │
│                                                             │
│  ┌─────────────────┐     ┌──────────────────────────────┐  │
│  │  Popup          │     │  Strona internetowa           │  │
│  │  (popup.js)     │     │  ┌────────────────────────┐   │  │
│  └────────┬────────┘     │  │ content_script.js      │   │  │
│           │              │  │ (chip autofill)        │   │  │
│           │              │  └──────────┬─────────────┘   │  │
│           └──────────────┴─────────────┘                 │  │
│                          │ chrome.runtime.sendMessage     │  │
│           ┌──────────────▼─────────────────────────────┐ │  │
│           │  service_worker.js                         │ │  │
│           │  (stan sesji, routing)                     │ │  │
│           └──────────────┬─────────────────────────────┘ │  │
│                          │ chrome.runtime.connectNative   │  │
└──────────────────────────│─────────────────────────────────┘
                           │ stdio (4-byte length-prefixed JSON)
┌──────────────────────────▼─────────────────────────────────┐
│  NATYWNY HOST (Python)                                      │
│                                                             │
│  aegisvault_host.py                                         │
│  host_session.py  (CryptoManager w RAM)                     │
│  ↕ importuje bezpośrednio                                   │
│  core/crypto.py + database/db_manager.py                    │
│  ↕ odczytuje                                                │
│  aegisvault.db  (ta sama baza co aplikacja desktop)         │
└─────────────────────────────────────────────────────────────┘
```

---

## Service Worker (`background/service_worker.js`)

### Odpowiedzialności

- Utrzymuje połączenie z Native Host (`chrome.runtime.connectNative`)
- Zarządza stanem sesji w `chrome.storage.session`
- Routuje wiadomości między popup/content script a hostem
- Aktualizuje badge ikony (🔒 = zablokowany)
- Sprawdza wygaśnięcie sesji co minutę (Chrome Alarms)

### Stan sesji (`chrome.storage.session`)

```js
{
  unlocked: boolean,                // czy sesja aktywna
  username: string | null,          // zalogowany użytkownik
  session_expires_at: string | null // ISO-8601, sliding 5 min
}
```

`chrome.storage.session` jest automatycznie czyszczone przy zamknięciu przeglądarki i nie jest synchronizowane między urządzeniami.

### Obsługiwane typy wiadomości

| Typ | Kierunek | Opis |
|-----|----------|------|
| `CHECK_SESSION` | popup → SW | Sprawdź stan sesji |
| `UNLOCK` | popup → SW → host | Zaloguj z hasłem głównym (+ opcjonalnie TOTP) |
| `LOCK` | popup → SW → host | Zablokuj sesję |
| `GET_ALL_CREDENTIALS` | popup → SW → host | Pobierz listę wpisów (bez haseł) |
| `GET_CREDENTIAL_BY_ID` | popup/CS → SW → host | Pobierz wpis z odszyfrowanym hasłem |
| `GET_CREDENTIALS_FOR_URL` | CS → SW → host | Dopasuj wpisy do aktualnego URL |
| `FILL_FORM` | popup → SW → CS | Wypełnij formularz na aktywnej karcie |
| `PING` | SW → host | Sprawdź czy host żyje |

---

## Content Script (`content/content_script.js`)

### Wykrywanie formularzy

Algorytm wykrywania:
1. Szuka wszystkich `<input type="password">` widocznych na stronie
2. Dla każdego pola hasła szuka skojarzonego pola loginu w obrębie wspólnego przodka (`<form>` lub 5 poziomów wyżej)
3. Kandydaci na login: `type="email"`, `type="text"` z atrybutem `name/id/autocomplete/placeholder` pasującym do wzorca `username|email|login|user|mail`
4. Wybiera kandydata najbliższego w DOM pola hasła

### Chip autofill

Chip renderowany jest w **closed Shadow DOM** — strona internetowa nie ma do niego dostępu.

```
┌──────────────────────────────────┐
│ [AV]  Uzupełnij przez AegisVault │
├──────────────────────────────────┤
│ [G]  GitHub                      │
│      jan@example.com          →  │
├──────────────────────────────────┤
│ [G]  GitHub (konto firmowe)      │
│      firma@example.com        →  │
└──────────────────────────────────┘
```

Chip pojawia się gdy:
- Sesja jest aktywna (zalogowany w popupie)
- Istnieje co najmniej jeden wpis z URL pasującym do domeny strony
- Użytkownik kliknie lub skupi pole hasła/loginu

### Dopasowanie URL

```
request URL: https://login.github.com/session
request host: login.github.com

entry URL: https://github.com
entry host: github.com

Match: login.github.com endsWith .github.com ✓
```

Logika w native hoście (`aegisvault_host.py`, `handle_get_credentials_for_url`).

### Wypełnianie pól

Kompatybilność z React, Vue, Angular — symulacja natywnych zdarzeń:

```js
// Używa natywnego settera z prototype — omija React synthetic events
Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
      .set.call(element, value);

element.dispatchEvent(new Event('input',  { bubbles: true }));
element.dispatchEvent(new Event('change', { bubbles: true }));
```

### MutationObserver (SPA)

Obserwuje `document.body` pod kątem dynamicznie dodawanych pól `<input type="password">`. Po wykryciu nowych elementów uruchamia ponowne skanowanie z 100ms opóźnieniem (stabilizacja DOM).

---

## Popup (`popup/`)

### Widok A — Zablokowany

```
┌─────────────────────────────────┐
│  [AV]  AegisVault               │
│        Menedżer haseł           │
│                                 │
│  Nazwa użytkownika              │
│  ┌─────────────────────────────┐│
│  │ login                       ││
│  └─────────────────────────────┘│
│  Hasło główne                   │
│  ┌──────────────────────── 👁 ┐ │
│  │ ••••••••••••••••••          ││
│  └─────────────────────────────┘│
│  [Kod 2FA - jeśli wymagany]     │
│  ┌─────────────────────────────┐│
│  │ 000000                      ││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │        Odblokuj             ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
```

### Widok B — Lista wpisów

```
┌─────────────────────────────────┐
│ [AV] jan           🔒 za 5 min  │
├─────────────────────────────────┤
│ 🔍 Szukaj...                    │
├─────────────────────────────────┤
│ [G]  GitHub              ›     │
│      jan@example.com            │
├─────────────────────────────────┤
│ [F]  Facebook            ›     │
│      jan.kowalski               │
├─────────────────────────────────┤
│  Uzupełnij: github.com  [Uzupełnij stronę] │
└─────────────────────────────────┘
```

- Wyszukiwanie filtruje po tytule, loginie i URL
- Fill Bar pojawia się gdy aktywna karta ma pasujące wpisy
- Timer sesji odświeżany co 5 sekund

### Widok C — Szczegóły wpisu

```
┌─────────────────────────────────┐
│ ← Wróć    GitHub                │
├─────────────────────────────────┤
│ Login    jan@example.com    📋  │
│ Hasło    ••••••••         👁 📋 │
│ URL      https://github.com     │
│ Notatki  Konto prywatne         │
│ Kategoria Praca                 │
│                                 │
│  ┌─────────────────────────────┐│
│  │     Uzupełnij stronę        ││
│  └─────────────────────────────┘│
└─────────────────────────────────┘
```

---

## Native Messaging Host (`native_host/`)

### Protokół komunikacji

Format: `[4 bajty little-endian długość][JSON UTF-8]`

Każda wiadomość zawiera `request_id` (UUID v4) do korelacji żądanie ↔ odpowiedź.

#### Żądania (extension → host)

```json
{ "type": "UNLOCK", "request_id": "uuid",
  "username": "jan", "master_password": "secret", "totp_code": null }

{ "type": "LOCK", "request_id": "uuid" }

{ "type": "GET_CREDENTIALS_FOR_URL", "request_id": "uuid",
  "url": "https://github.com/login" }

{ "type": "GET_ALL_CREDENTIALS", "request_id": "uuid", "search": null }

{ "type": "GET_CREDENTIAL_BY_ID", "request_id": "uuid", "id": 42 }

{ "type": "PING", "request_id": "uuid" }
```

#### Odpowiedzi (host → extension)

```json
// Sukces UNLOCK
{ "request_id": "uuid", "ok": true,
  "data": { "username": "jan", "has_totp": true,
            "session_expires_at": "2025-01-01T12:05:00" } }

// Błąd — nieprawidłowe hasło
{ "request_id": "uuid", "ok": false, "error": "INVALID_CREDENTIALS" }

// Wymagany TOTP
{ "request_id": "uuid", "ok": false, "error": "TOTP_REQUIRED" }

// Lista wpisów (bez haseł)
{ "request_id": "uuid", "ok": true,
  "data": { "credentials": [
    { "id": 1, "title": "GitHub", "username": "jan@...",
      "url": "https://github.com", "category": "Praca" }
  ] } }

// Wpis z hasłem (tylko GET_CREDENTIAL_BY_ID i GET_CREDENTIALS_FOR_URL)
{ "request_id": "uuid", "ok": true,
  "data": { "id": 1, "title": "GitHub", "username": "jan@...",
            "password": "plaintext_password", "url": "...",
            "notes": "", "category": "Praca" } }

// Wygaśnięcie sesji
{ "request_id": "uuid", "ok": false, "error": "SESSION_EXPIRED" }
```

#### Kody błędów

| Kod | Opis |
|-----|------|
| `INVALID_CREDENTIALS` | Zły login lub hasło główne |
| `TOTP_REQUIRED` | Konto ma 2FA — wymagany kod |
| `INVALID_TOTP` | Podany kod 2FA jest nieprawidłowy |
| `SESSION_EXPIRED` | Sesja wygasła (5 min bezczynności) |
| `NOT_FOUND` | Wpis o podanym ID nie istnieje |
| `DECRYPT_ERROR` | Błąd deszyfrowania (uszkodzone dane?) |
| `NATIVE_HOST_UNAVAILABLE` | Host nie uruchomiony / nie zarejestrowany |
| `HOST_TIMEOUT` | Brak odpowiedzi hosta w 15s |

### Sesja hosta (`host_session.py`)

- Klucz AES (`CryptoManager`) żyje w zmiennych modułu — nigdy na dysku
- Sliding expiry: każde uwierzytelnione żądanie przesuwa czas wygaśnięcia
- `destroy_session()` zeruje referencje — klucz eligible for GC

---

## Uprawnienia rozszerzenia

```json
"permissions": [
  "nativeMessaging",  // połączenie z hostem Python
  "activeTab",        // odczyt URL aktywnej karty
  "storage",          // stan sesji (chrome.storage.session)
  "scripting",        // fallback injection
  "alarms"            // sprawdzanie wygaśnięcia sesji
],
"host_permissions": [
  "http://*/*",
  "https://*/*"       // content script na wszystkich stronach
]
```

---

## Skróty klawiszowe

| Skrót | Akcja |
|-------|-------|
| `Alt+Shift+F` | Wywołaj autofill na aktywnej stronie |
| `Escape` | Zamknij chip autofill |

Skrót można zmienić w ustawieniach przeglądarki (`chrome://extensions/shortcuts`).

---

## Znane ograniczenia

| Ograniczenie | Szczegóły |
|--------------|-----------|
| Formularze w iframes | Nie obsługiwane (planowane) |
| Strony HTTPS wymagane | Na stronach HTTP chip pojawia się, ale przeglądarka może blokować dostęp |
| Firefox tymczasowy | Rozszerzenie w Firefox znika po restarcie przeglądarki (wymaga podpisania lub `about:config`) |
| Jeden użytkownik | Wtyczka loguje się do jednego konta jednocześnie |
