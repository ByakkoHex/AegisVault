"""
easing.py — Jednolite krzywe animacji dla AegisVault
=====================================================
Wszystkie funkcje przyjmują t ∈ [0, 1] i zwracają wartość ∈ [0, 1].

Użycie:
    from utils.easing import ease_out_cubic, ease_out_back

Dostępne krzywe:
    smoothstep(t)           — S-krzywa (obecny standard)
    ease_out_cubic(t)       — szybki start, wolne wejście — dobre dla slide-in
    ease_in_cubic(t)        — wolny start, szybkie wyjście — dobre dla dismiss
    ease_out_back(t)        — spring z overshootem — dobre dla liczników / ikon
    ease_in_out_quart(t)    — miękkie obustronne — dobre dla cross-fade

Stałe czasu trwania (ms):
    DURATION_MICRO  = 80    — ripple, flash, mini-feedback
    DURATION_SHORT  = 150   — hover, fade overlay, toast slide
    DURATION_MEDIUM = 220   — accordion, dialog slide_fade_in, row insert
    DURATION_LONG   = 400   — strength bar, dashboard slide, cross-fade widoku
"""

# ── Stałe czasu trwania ───────────────────────────────────────────────

DURATION_MICRO  = 80
DURATION_SHORT  = 150
DURATION_MEDIUM = 220
DURATION_LONG   = 400


# ── Krzywe ───────────────────────────────────────────────────────────

def smoothstep(t: float) -> float:
    """S-krzywa — obecny standard AegisVault."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out_cubic(t: float) -> float:
    """Szybki start, wolne dobieganie do celu. Dobry dla slide-in elementów."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    """Wolny start, szybkie wyjście. Dobry dla dismiss / slide-out."""
    t = max(0.0, min(1.0, t))
    return t ** 3


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    """Spring z overshootem powyżej 1.0. Dobry dla liczników i ikon.

    overshoot=1.70158 → ≈8% overshoot (domyślny CSS ease-out-back).
    """
    t = max(0.0, min(1.0, t))
    c1 = overshoot
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_out_quart(t: float) -> float:
    """Miękkie obustronne przejście. Dobry dla cross-fade widoku."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 8 * t ** 4
    return 1 - (-2 * t + 2) ** 4 / 2
