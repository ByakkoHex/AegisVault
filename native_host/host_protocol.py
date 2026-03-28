"""
host_protocol.py — Native Messaging Protocol
=============================================
Obsługuje komunikację stdin/stdout z 4-bajtowym prefixem długości.
Standard: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
"""

import json
import struct
import sys


def read_message() -> dict | None:
    """
    Czyta jedną wiadomość z stdin.
    Format: [4 bajty little-endian długość][JSON UTF-8]
    Zwraca None gdy stdin zostanie zamknięty (przeglądarka się rozłączyła).
    """
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None  # EOF — przeglądarka zamknęła połączenie

    message_length = struct.unpack("<I", raw_length)[0]
    raw_message = sys.stdin.buffer.read(message_length)
    if len(raw_message) < message_length:
        return None

    return json.loads(raw_message.decode("utf-8"))


def write_message(message: dict) -> None:
    """
    Zapisuje jedną wiadomość na stdout.
    Format: [4 bajty little-endian długość][JSON UTF-8]
    """
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    length = struct.pack("<I", len(encoded))
    sys.stdout.buffer.write(length + encoded)
    sys.stdout.buffer.flush()


def send_ok(request_id: str, data: dict) -> None:
    write_message({"request_id": request_id, "ok": True, "data": data})


def send_error(request_id: str, error: str) -> None:
    write_message({"request_id": request_id, "ok": False, "error": error})
