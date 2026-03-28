"""
password_strength.py - Moduł oceny siły hasła
===============================================
Ocenia hasło w skali 0-4 i zwraca szczegółowe informacje
wraz z checklistą wymagań.
"""

import re
import math

# Pre-compiled patterns — kompilacja raz przy imporcie modułu
_RE_LOWER   = re.compile(r'[a-z]')
_RE_UPPER   = re.compile(r'[A-Z]')
_RE_DIGIT   = re.compile(r'\d')
_RE_SPECIAL = re.compile(r'[^a-zA-Z0-9]')
_RE_REPEAT  = re.compile(r'(.)\1{2,}')

_SEQUENCES  = ['0123456789', 'abcdefghijklmnopqrstuvwxyz', 'qwertyuiop', 'asdfghjkl']


def check_strength(password: str) -> dict:
    """
    Ocenia siłę hasła i zwraca szczegółowe informacje.

    Zwraca słownik:
        score:       0-4
        label:       opis słowny
        color:       kolor hex do UI
        percent:     0-100 do paska postępu
        entropy:     entropia w bitach
        checklist:   lista dict z wymaganiami (text, met: bool)
        suggestions: lista tekstowych wskazówek (max 2)
    """
    if not password:
        return {
            "score": 0, "label": "", "color": "gray",
            "percent": 0, "entropy": 0,
            "checklist": _build_checklist(password),
            "suggestions": []
        }

    checklist = _build_checklist(password)
    met_count = sum(1 for item in checklist if item["met"])
    score = 0
    suggestions = []

    length = len(password)

    # Punktacja na podstawie długości
    if length >= 8:
        score += 1
    if length >= 14:
        score += 1

    # Punktacja za różnorodność znaków
    has_lower   = bool(_RE_LOWER.search(password))
    has_upper   = bool(_RE_UPPER.search(password))
    has_digit   = bool(_RE_DIGIT.search(password))
    has_special = bool(_RE_SPECIAL.search(password))
    variety = sum([has_lower, has_upper, has_digit, has_special])

    if variety >= 3:
        score += 1
    if variety == 4:
        score += 1

    # Kary
    if _RE_REPEAT.search(password):
        score = max(0, score - 1)
        suggestions.append("Unikaj powtarzających się znaków (aaa, 111)")

    for seq in _SEQUENCES:
        for i in range(len(seq) - 2):
            if seq[i:i+3] in password.lower():
                score = max(0, score - 1)
                suggestions.append("Unikaj sekwencji (123, abc, qwerty)")
                break

    score = max(0, min(4, score))

    # Entropia
    charset_size = 0
    if has_lower:   charset_size += 26
    if has_upper:   charset_size += 26
    if has_digit:   charset_size += 10
    if has_special: charset_size += 32
    entropy = round(length * math.log2(charset_size), 1) if charset_size > 0 else 0

    # Dodaj sugestie z checklisty (niezaliczone wymagania)
    for item in checklist:
        if not item["met"] and len(suggestions) < 2:
            suggestions.append(item["hint"])

    labels   = ["Bardzo słabe", "Słabe", "Średnie", "Silne", "Bardzo silne"]
    colors   = ["#e53e3e", "#dd6b20", "#d69e2e", "#38a169", "#2b6cb0"]
    percents = [15, 35, 55, 78, 100]

    return {
        "score":       score,
        "label":       labels[score],
        "color":       colors[score],
        "percent":     percents[score],
        "entropy":     entropy,
        "checklist":   checklist,
        "suggestions": list(dict.fromkeys(suggestions))[:2],
    }


def _build_checklist(password: str) -> list[dict]:
    """
    Buduje checklistę wymagań dla hasła.
    Każdy element zawiera: text, hint, met (bool), icon.
    """
    length = len(password)

    requirements = [
        {
            "text": "Minimum 8 znaków",
            "hint": "Użyj co najmniej 8 znaków",
            "met":  length >= 8,
            "icon": "📏"
        },
        {
            "text": "Minimum 14 znaków (zalecane)",
            "hint": "Dla lepszego bezpieczeństwa użyj 14+ znaków",
            "met":  length >= 14,
            "icon": "📐"
        },
        {
            "text": "Małe litery (a-z)",
            "hint": "Dodaj małe litery",
            "met":  bool(_RE_LOWER.search(password)),
            "icon": "🔡"
        },
        {
            "text": "Wielkie litery (A-Z)",
            "hint": "Dodaj wielkie litery",
            "met":  bool(_RE_UPPER.search(password)),
            "icon": "🔠"
        },
        {
            "text": "Cyfry (0-9)",
            "hint": "Dodaj cyfry",
            "met":  bool(_RE_DIGIT.search(password)),
            "icon": "🔢"
        },
        {
            "text": "Znaki specjalne (!@#$...)",
            "hint": "Dodaj znaki specjalne np. !@#$%",
            "met":  bool(_RE_SPECIAL.search(password)),
            "icon": "✳️"
        },
    ]

    return requirements
