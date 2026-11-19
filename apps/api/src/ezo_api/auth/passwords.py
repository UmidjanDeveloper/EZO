"""Password hashing with the standard library's scrypt (no extra dependency).

Stored as "scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>". Verification is constant-time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
MIN_LENGTH = 8
MAX_LENGTH = 200


class PasswordError(ValueError):
    pass


def check_strength(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise PasswordError(f"The password must be at least {MIN_LENGTH} characters long.")
    if len(password) > MAX_LENGTH:
        raise PasswordError("The password is too long.")
    if password.isdigit() or len(set(password)) < 4:
        raise PasswordError("The password is too simple.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${N}${R}${P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or len(password) > MAX_LENGTH:
        # Same work as a real check, so a missing account is not faster to probe.
        hashlib.scrypt(b"x", salt=b"0" * 16, n=N, r=R, p=P, dklen=32)
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(expected),
        )  # fmt: skip
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
