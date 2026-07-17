"""Small shared validators for canonical protocol-core digests."""

from __future__ import annotations

from typing import TypeGuard


SHA256_FINGERPRINT_PREFIX = "sha256:"
SHA256_HEX_LENGTH = 64
SHA256_FINGERPRINT_LENGTH = len(SHA256_FINGERPRINT_PREFIX) + SHA256_HEX_LENGTH


def is_canonical_sha256_fingerprint(value: object) -> TypeGuard[str]:
    """Return whether *value* is one lowercase, fixed-width SHA-256 digest."""

    if not isinstance(value, str):
        return False
    # Read the built-in value directly so a ``str`` subclass cannot alter the
    # result through an overridden slice, length, or prefix operation.
    text = str.__str__(value)
    if len(text) != SHA256_FINGERPRINT_LENGTH or not text.startswith(
        SHA256_FINGERPRINT_PREFIX
    ):
        return False
    digest = text[len(SHA256_FINGERPRINT_PREFIX) :]
    if digest != digest.lower():
        return False
    try:
        decoded = bytes.fromhex(digest)
    except ValueError:
        return False
    return len(decoded) == SHA256_HEX_LENGTH // 2


__all__ = [
    "SHA256_FINGERPRINT_LENGTH",
    "SHA256_FINGERPRINT_PREFIX",
    "SHA256_HEX_LENGTH",
    "is_canonical_sha256_fingerprint",
]
