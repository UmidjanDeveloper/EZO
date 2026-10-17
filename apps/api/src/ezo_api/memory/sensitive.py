"""Detection of sensitive content that must not be memorized automatically."""

from __future__ import annotations

import re

from ezo_api.core.text import normalize

_KEYWORDS = re.compile(
    r"\b(password|passcode|parol|пароль|pin ?code|pin-kod|пин-код|cvv|cvc|secret key|"
    r"api key|api_key|token|токен|seed phrase|private key|shaxsiy kalit|"
    r"passport|pasport|паспорт|jshshir|pinfl|инн|tin raqam)"
)
_API_KEY = re.compile(r"\b(sk|pk|rk|ghp|gho|xox[abp]|AIza)[-_A-Za-z0-9]{16,}")
_PASSPORT_UZ = re.compile(r"\b[A-Z]{2}\s?\d{7}\b")
_DIGITS = re.compile(r"(?:\d[ -]?){13,19}")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")


def _luhn_ok(number: str) -> bool:
    digits = [int(ch) for ch in number if ch.isdigit()]
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def sensitive_reason(text: str) -> str | None:
    """Return why `text` looks sensitive, or None when it looks safe to remember."""
    if _API_KEY.search(text):
        return "credential"
    if _KEYWORDS.search(normalize(text)):
        return "sensitive_keyword"
    if _PASSPORT_UZ.search(text):
        return "identity_document"
    if _IBAN.search(text):
        return "bank_account"
    for match in _DIGITS.finditer(text):
        if _luhn_ok(match.group(0)):
            return "payment_card"
    return None
