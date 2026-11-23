"""Password hashing, session tokens and IP hashing (stdlib only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from .config import get_settings

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


# Used to keep timing similar when the username doesn't exist.
DUMMY_HASH = hash_password(secrets.token_urlsafe(8))


def new_session_token() -> tuple[str, str]:
    """Returns (token for the cookie, hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """IPs are personal data: store only a salted hash, enough for rate limiting and audit."""
    if not ip:
        return None
    return hashlib.sha256((get_settings().ip_hash_salt + "|" + ip).encode()).hexdigest()[:32]


_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_public_ref() -> str:
    return "HS-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(8))
