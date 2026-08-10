"""Password hashing compatible with Werkzeug 2.x and legacy scrypt hashes.

Werkzeug 2.2.3 (pinned) does not implement scrypt. Hashes produced by newer
Werkzeug (method ``scrypt:N:r:p$salt$hex``) raise ValueError on check.
Verify those with hashlib.scrypt; generate new hashes with pbkdf2:sha256.
"""
from __future__ import annotations

import hashlib
import hmac

from werkzeug.security import (
    check_password_hash as _werkzeug_check,
    generate_password_hash as _werkzeug_generate,
)

# Reliable on Windows / OpenSSL builds where scrypt is awkward via hmac.
PASSWORD_HASH_METHOD = 'pbkdf2:sha256'
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def generate_password_hash(password: str) -> str:
    return _werkzeug_generate(password, method=PASSWORD_HASH_METHOD)


def check_password_hash(pwhash: str, password: str) -> bool:
    if not pwhash or pwhash.count('$') < 2:
        return False

    method, salt, hashval = pwhash.split('$', 2)
    if method.startswith('scrypt:'):
        return _check_scrypt(method, salt, hashval, password)

    try:
        return _werkzeug_check(pwhash, password)
    except ValueError:
        return False


def _check_scrypt(method: str, salt: str, hashval: str, password: str) -> bool:
    try:
        parts = method.split(':')
        if len(parts) != 4:
            return False
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        derived = hashlib.scrypt(
            password.encode('utf-8'),
            salt=salt.encode('utf-8'),
            n=n,
            r=r,
            p=p,
            maxmem=_SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(derived.hex(), hashval)
    except (ValueError, TypeError, OverflowError, OSError):
        return False
