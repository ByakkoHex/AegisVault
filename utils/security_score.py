"""
security_score.py - Kalkulator bezpieczeństwa haseł
=====================================================
Wynik 0-100 oparty na:
  40 pkt — siła haseł (średnia)
  30 pkt — brak wygasłych / wygasających
  30 pkt — unikalność (brak duplikatów)
"""

from utils.password_strength import check_strength


def calculate_from_entries(entries, crypto) -> dict:
    """Wersja calculate() przyjmująca gotowe entries (thread-safe).

    Przyjmuje już pobrane entries zamiast db+user, dzięki czemu można
    wywołać z wątku roboczego bez ryzyka race-condition na SQLAlchemy Session.
    """
    total = len(entries)
    if total == 0:
        return {"score": 0, "total": 0, "weak": 0,
                "expired": 0, "soon": 0, "duplicates": 0}

    strength_sum = 0
    weak         = 0
    expired      = 0
    soon         = 0
    seen: dict[str, int] = {}

    for entry in entries:
        try:
            plaintext = crypto.decrypt(entry.encrypted_password)
            result    = check_strength(plaintext)
            pct       = result["percent"]
            strength_sum += pct
            if result["score"] < 2:
                weak += 1
            seen[plaintext] = seen.get(plaintext, 0) + 1
        except Exception:
            strength_sum += 0
            weak += 1
            seen["__err__"] = seen.get("__err__", 0) + 1

        status = entry.expiry_status
        if status == "expired":
            expired += 1
        elif status == "soon":
            soon += 1

    duplicates = sum(1 for p, cnt in seen.items() if cnt > 1 and p != "__err__")
    strength_score   = (strength_sum / total) * 0.40
    expiry_score     = max(0, 30 - expired * 8 - soon * 3)
    uniqueness_score = max(0, 30 - duplicates * 6)
    score = int(strength_score + expiry_score + uniqueness_score)
    score = max(0, min(100, score))

    return {"score": score, "total": total, "weak": weak,
            "expired": expired, "soon": soon, "duplicates": duplicates}


def calculate(db, crypto, user) -> dict:
    """
    Oblicza Security Score synchronicznie (wywołuj w wątku roboczym!).

    Zwraca:
        score       — int 0-100
        total       — liczba haseł
        weak        — hasła słabe (score < 2)
        expired     — wygasłe
        soon        — wygasają w ciągu 7 dni
        duplicates  — liczba zduplikowanych haseł
    """
    entries = db.get_all_passwords(user)
    return calculate_from_entries(entries, crypto)
