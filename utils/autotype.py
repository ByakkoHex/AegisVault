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

Na Windows używa SendInput + KEYEVENTF_UNICODE, co omija VkKeyScanW
i układ klawiatury — brak błędów C→!, i→!, b→n na polskim layoucie.
Na innych platformach fallback do pynput.keyboard.Controller.
Hasło NIE trafia do schowka — wpisywane bezpośrednio.
"""

import time
import threading
import sys

DEFAULT_SEQUENCE = "{USERNAME}{TAB}{PASSWORD}{ENTER}"
DEFAULT_DELAY_S  = 2.0

# --------------------------------------------------------------------------- #
# Windows SendInput helpers                                                     #
# --------------------------------------------------------------------------- #

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

    _KEYEVENTF_UNICODE = 0x0004
    _KEYEVENTF_KEYUP   = 0x0002
    _INPUT_KEYBOARD    = 1

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk",         ctypes.wintypes.WORD),
            ("wScan",       ctypes.wintypes.WORD),
            ("dwFlags",     ctypes.wintypes.DWORD),
            ("time",        ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("_pad", ctypes.c_byte * 28)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("union", _INPUT_UNION)]

    _extra     = ctypes.c_ulong(0)
    _extra_ptr = ctypes.cast(ctypes.pointer(_extra), ctypes.POINTER(ctypes.c_ulong))

    def _make_unicode_input(scan: int, key_up: bool) -> "_INPUT":
        inp = _INPUT()
        inp.type = _INPUT_KEYBOARD
        inp.union.ki.wVk = 0
        inp.union.ki.wScan = scan
        inp.union.ki.dwFlags = _KEYEVENTF_UNICODE | (_KEYEVENTF_KEYUP if key_up else 0)
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = _extra_ptr
        return inp

    def _type_string_win(text: str) -> None:
        """Wysyła każdy znak jako Unicode keypair (down+up) przez SendInput.

        Nie używa VkKeyScanW — układ klawiatury nie ma znaczenia.
        Obsługuje znaki spoza BMP (surrogate pairs).
        """
        for ch in text:
            code = ord(ch)
            if code > 0xFFFF:
                high = 0xD800 + ((code - 0x10000) >> 10)
                low  = 0xDC00 + ((code - 0x10000) & 0x3FF)
                scans = [high, low]
            else:
                scans = [code]

            for scan in scans:
                ctypes.windll.user32.SendInput(
                    1, ctypes.byref(_make_unicode_input(scan, False)), ctypes.sizeof(_INPUT))
                time.sleep(0.002)
                ctypes.windll.user32.SendInput(
                    1, ctypes.byref(_make_unicode_input(scan, True)), ctypes.sizeof(_INPUT))
                time.sleep(0.002)

    def _press_special_win(key_name: str) -> None:
        VK = {"tab": 0x09, "enter": 0x0D}
        vk = VK.get(key_name, 0)
        if not vk:
            return
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

def type_sequence_now(username: str, password: str,
                      sequence: str = DEFAULT_SEQUENCE) -> None:
    """Wpisuje sekwencję synchronicznie (blokuje wywołujący wątek).

    Przeznaczone do wywołania z wątku, który już obsłużył opóźnienie
    i zarządzanie oknem (minimize/SetForegroundWindow).
    """
    use_winapi = sys.platform == "win32"

    if not use_winapi:
        try:
            from pynput.keyboard import Key, Controller
            kb = Controller()
        except ImportError:
            return

    def _type_text(text: str) -> None:
        if use_winapi:
            _type_string_win(text)
        else:
            kb.type(text)

    def _press_special(key_name: str) -> None:
        if use_winapi:
            _press_special_win(key_name)
        else:
            from pynput.keyboard import Key
            k = Key.tab if key_name == "tab" else Key.enter
            kb.press(k)
            kb.release(k)

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
                    _type_text(username)
            elif token == 'PASSWORD':
                if password:
                    _type_text(password)
            elif token == 'TAB':
                time.sleep(0.06)
                _press_special("tab")
                time.sleep(0.06)
            elif token == 'ENTER':
                time.sleep(0.06)
                _press_special("enter")
            elif token.startswith('DELAY='):
                try:
                    ms = int(token[6:])
                    time.sleep(max(0, ms) / 1000.0)
                except ValueError:
                    pass
            i = end + 1
        else:
            _type_text(seq[i])
            i += 1


def auto_type(username: str, password: str,
              sequence: str = DEFAULT_SEQUENCE,
              on_done=None) -> None:
    """Wpisuje sekwencję w aktualnie aktywnym oknie systemu.

    Uruchamia się w osobnym wątku — nie blokuje UI.
    """
    def _run():
        try:
            type_sequence_now(username, password, sequence)
        finally:
            if on_done:
                on_done()

    threading.Thread(target=_run, daemon=True).start()
