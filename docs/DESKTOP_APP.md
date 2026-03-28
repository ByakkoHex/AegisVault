# Dokumentacja aplikacji desktop — AegisVault

## Uruchomienie

```bash
py main.py          # Windows
python3 main.py     # macOS / Linux
```

---

## Okno logowania

### Rejestracja

1. Kliknij zakładkę **Zarejestruj**
2. Podaj nazwę użytkownika (min. 3 znaki)
3. Ustaw hasło główne — pasek siły pokazuje ocenę w czasie rzeczywistym:
   - Wymagana długość min. 8 znaków
   - Zalecana: wielkie litery, cyfry, znaki specjalne
4. (Opcjonalnie) Włącz **2FA**: kliknij "Włącz uwierzytelnianie dwuskładnikowe", zeskanuj QR aplikacją Authenticator, wpisz wygenerowany kod

### Kryteria siły hasła

| Kryterium | Punkty |
|-----------|--------|
| Długość ≥ 8 | wymagane |
| Długość ≥ 14 | bonus |
| Małe litery | +1 |
| Wielkie litery | +1 |
| Cyfry | +1 |
| Znaki specjalne | +1 |
| Kara: powtarzające się znaki | −1 |
| Kara: sekwencje (qwerty, 123, abc) | −1 |

Skala ocen: Bardzo słabe → Słabe → Średnie → Silne → Bardzo silne

### Logowanie z 2FA

Jeśli konto ma włączone 2FA:
1. Wpisz login i hasło główne → kliknij Zaloguj
2. Wyświetla się ekran 2FA — wpisz 6-cyfrowy kod z aplikacji Authenticator
3. Kod jest ważny 30 sekund (akceptowany z tolerancją ±30s)

---

## Główne okno

### Pasek boczny (lewy)

| Element | Funkcja |
|---------|---------|
| Logo AegisVault + nazwa użytkownika | Identyfikacja konta |
| Wszystkie | Pokaż wszystkie hasła |
| Social Media | Filtr kategorii |
| Praca | Filtr kategorii |
| Bankowość | Filtr kategorii |
| Rozrywka | Filtr kategorii |
| Inne | Filtr kategorii |
| Eksportuj | Eksport do zaszyfrowanego pliku `.aegis` |
| Importuj | Import z pliku `.aegis` |

### Pasek górny

| Przycisk | Funkcja |
|----------|---------|
| Pole wyszukiwania | Filtruje po tytule i URL w czasie rzeczywistym |
| + Dodaj hasło | Otwiera formularz nowego wpisu |
| Analiza | Otwiera okno audytu bezpieczeństwa |
| Synchronizuj | Otwiera okno synchronizacji |
| Menu użytkownika (⋮) | Ustawienia, wylogowanie |

### Lista haseł

Każdy wiersz zawiera:
- Avatar z inicjałem i kolorem kategorii
- Tytuł serwisu + login + URL
- Znacznik kategorii
- Przycisk **Kopiuj** — kopiuje hasło do schowka, odlicza 30s i automatycznie czyści
- Przycisk **Edytuj** — otwiera formularz edycji
- Przycisk **Usuń** — usuwa wpis po potwierdzeniu

### Formularz dodawania / edycji hasła

| Pole | Opis |
|------|------|
| Tytuł | Nazwa serwisu (wymagane) |
| Login | Nazwa użytkownika lub e-mail |
| Hasło | Szyfrowane hasło; pasek siły w czasie rzeczywistym |
| Generator | Generuje losowe hasło (domyślnie 20 znaków) |
| URL | Adres strony (używany przez wtyczkę do dopasowania) |
| Kategoria | Wybór z listy |
| Notatki | Dowolny tekst |

### Generator haseł

Domyślne ustawienia: 20 znaków, wielkie litery, małe litery, cyfry, znaki specjalne.
Generator używa `secrets.choice()` — kryptograficznie bezpieczny.

### Auto-lock

Po 5 minutach braku aktywności (kliknięcia, naciśnięcia klawisza) aplikacja wyświetla ekran re-logowania. Schowek jest czyszczony. Klucz AES zostaje usunięty z pamięci.

---

## Okno analizy bezpieczeństwa

Analizuje wszystkie hasła konta i wyświetla:

| Kategoria | Definicja |
|-----------|-----------|
| Słabe hasła | Wynik siły ≤ 1 (Bardzo słabe lub Słabe) |
| Zduplikowane | To samo hasło użyte dla różnych serwisów |
| Przestarzałe | Nie zmieniane od ponad 90 dni |
| Bezpieczne | Silne, unikalne, aktualne |

Ogólny wynik bezpieczeństwa: 0–100, obliczany proporcjonalnie do liczby bezpiecznych wpisów.

---

## Okno ustawień

### Zmiana hasła głównego

1. Podaj stare hasło główne
2. Podaj kod 2FA (jeśli włączone)
3. Podaj nowe hasło główne
4. System **ponownie szyfruje** wszystkie wpisy nowym kluczem
5. Hash i salt są aktualizowane w bazie

### Usunięcie konta

1. Podaj hasło główne + kod 2FA
2. Potwierdź decyzję
3. Wszystkie hasła i dane użytkownika są **trwale usuwane** z bazy danych

---

## Okno synchronizacji

### Wymagania

- Uruchomiony serwer synchronizacji (lokalnie lub zdalnie)
- Osobne konto na serwerze (niezależne od hasła głównego)

### Procedura

1. Wpisz adres serwera (domyślnie: `http://localhost:8000`)
2. Zaloguj się lub zarejestruj konto serwerowe
3. **Push** — wyślij lokalne hasła na serwer (szyfrowane przed wysłaniem)
4. **Pull** — pobierz hasła z serwera na urządzenie

### Deduplicacja

Pull pomija wpisy, których tytuł już istnieje lokalnie. Nie ma automatycznego merge'owania konfliktów.

---

## Eksport i import

### Eksport

1. Kliknij **Eksportuj** w lewym pasku
2. Wybierz lokalizację pliku `.aegis`
3. Plik jest zaszyfrowany kluczem AES użytkownika — bezpieczny do przechowywania w chmurze

Format wewnętrzny (po odszyfrowaniu):
```json
[
  {
    "title": "GitHub",
    "username": "jan@example.com",
    "password": "plaintext_password",
    "url": "https://github.com",
    "notes": "",
    "category": "Praca",
    "created_at": "2024-01-01T12:00:00",
    "updated_at": "2024-06-01T15:30:00"
  }
]
```

### Import

1. Kliknij **Importuj** w lewym pasku
2. Wskaż plik `.aegis`
3. System pomija wpisy z tytułami które już istnieją
4. Wyświetla podsumowanie: `Zaimportowano X, pominięto Y`

---

## Kategorie

| Kategoria | Kolor avatara |
|-----------|--------------|
| Social Media | Niebieski |
| Praca | Zielony |
| Bankowość | Pomarańczowy |
| Rozrywka | Fioletowy |
| Inne | Szary |

---

## Skróty klawiszowe

| Skrót | Akcja |
|-------|-------|
| `Enter` w polu wyszukiwania | Przejdź do pierwszego wyniku |
| `Escape` | Wyczyść wyszukiwanie |

---

## Moduły Python — opis techniczny

### `core/crypto.py`

```python
hash_master_password(password: str) -> bytes
    # bcrypt(password, rounds=12)

verify_master_password(password: str, hash: bytes) -> bool
    # bcrypt.checkpw(password, hash)

generate_salt() -> bytes
    # os.urandom(16)

derive_key(password: str, salt: bytes) -> bytes
    # PBKDF2-HMAC-SHA256, 480_000 iter, dklen=32

CryptoManager(master_password: str, salt: bytes)
    .encrypt(plaintext: str) -> bytes
    .decrypt(ciphertext: bytes) -> str
    .reencrypt(ciphertext: bytes, new_crypto: CryptoManager) -> bytes

generate_password(length=20, upper=True, lower=True, digits=True, special=True) -> str
    # secrets.choice() — kryptograficznie bezpieczny
```

### `core/totp.py`

```python
generate_totp_secret() -> str          # pyotp.random_base32()
verify_totp_code(secret, code) -> bool # valid_window=1 (±30s)
get_current_code(secret) -> str        # aktualny 6-cyfrowy kod
generate_qr_code(secret, username) -> PIL.Image
generate_qr_code_base64(secret, username) -> str  # base64 PNG
```

### `utils/password_strength.py`

```python
check_strength(password: str) -> {
    "score":       int,      # 0-4
    "label":       str,      # "Bardzo słabe" ... "Bardzo silne"
    "color":       str,      # HEX kolor
    "entropy":     float,    # bity entropii
    "checklist":   dict,     # length8, length14, lower, upper, digit, special
    "suggestions": list[str] # max 2 wskazówki
}
```
