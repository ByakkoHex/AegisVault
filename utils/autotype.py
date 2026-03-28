"""
autotype.py - Auto-Type (automatyczne wpisywanie danych logowania)
=================================================================
Sekwencja wzorowana na KeePass: {USERNAME}{TAB}{PASSWORD}{ENTER}

Tokeny sekwencji:
  {USERNAME}  — wpisuje login
  {PASSWORD}  — wpisuje hasło
  {TAB}       — klawisz Tab
  {ENTER}     — klawisz Enter
  {DELAY=ms}  — pauza N milisekund

Używa pynput.keyboard.Controller:
  - Nie wymaga uprawnień administratora
  - Obsługuje znaki Unicode (polskie litery, symbole @#$%^&)
  - Hasło NIE trafia do schowka — wpisywane bezpośrednio
"""

import time
import threading

DEFAULT_SEQUENCE = "{USERNAME}{TAB}{PASSWORD}{ENTER}"
DEFAULT_DELAY_S  = 2.0


def auto_type(username: str, password: str,
              sequence: str = DEFAULT_SEQUENCE,
              on_done=None) -> None:
    """
    Wpisuje sekwencję w aktualnie aktywnym oknie systemu.

    Parametry:
        username  — login do wpisania (może być pusty)
        password  — hasło do wpisania
        sequence  — ciąg wpisywania z tokenami {TOKEN}
        on_done   — callback wywoływany po zakończeniu (opcjonalny)

    Uruchamia się w osobnym wątku — nie blokuje UI.
    """
    def _run():
        try:
            from pynput.keyboard import Key, Controller
        except ImportError:
            if on_done:
                on_done(error="pynput nie jest zainstalowane")
            return

        kb = Controller()
        i = 0
        seq = sequence or DEFAULT_SEQUENCE

        while i < len(seq):
            if seq[i] == '{':
                end = seq.find('}', i)
                if end == -1:
                    i += 1
                    continue
                token = seq[i + 1:end].upper()

                if token == 'USERNAME':
                    if username:
                        kb.type(username)
                elif token == 'PASSWORD':
                    if password:
                        kb.type(password)
                elif token == 'TAB':
                    time.sleep(0.06)
                    kb.press(Key.tab)
                    kb.release(Key.tab)
                    time.sleep(0.06)
                elif token == 'ENTER':
                    time.sleep(0.06)
                    kb.press(Key.enter)
                    kb.release(Key.enter)
                elif token.startswith('DELAY='):
                    try:
                        ms = int(token[6:])
                        time.sleep(max(0, ms) / 1000.0)
                    except ValueError:
                        pass
                i = end + 1
            else:
                kb.type(seq[i])
                i += 1

        if on_done:
            on_done()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
