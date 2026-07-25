"""Canonical binary64 leaves for the Hybrid Replay v2 wire.

This module deliberately does not provide a generic authority serializer.  A
Hybrid Replay record must project its own closed wire shape explicitly and use
these helpers only for fields whose ABI type is IEEE 754 binary64.
"""

from __future__ import annotations

from math import isfinite


HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2 = "pheroos-binary64-hex-v1"


def encode_binary64_v1(value: object, label: str) -> str:
    """Encode one exact, finite Python ``float`` in its canonical hex form.

    Python's exact ``float.hex()`` representation is the frozen textual wire
    for this profile.  Integers, booleans, float subclasses, and non-finite
    values are rejected instead of being silently coerced.
    """

    if type(value) is not float:
        raise TypeError(f"{label} must be an exact binary64 float")
    binary64 = value
    if not isfinite(binary64):
        raise ValueError(f"{label} must be a finite binary64 float")
    return binary64.hex()


def decode_binary64_v1(value: object, label: str) -> float:
    """Decode only the exact canonical text emitted by :func:`encode_binary64_v1`.

    ``float.fromhex`` accepts aliases, decimal-looking forms, case variants,
    and surrounding whitespace.  The round-trip equality check closes those
    spellings so one binary64 value has exactly one accepted wire form.
    """

    if type(value) is not str:
        raise TypeError(f"{label} must be exact canonical binary64 text")
    encoded = value
    if not encoded or any(character.isspace() for character in encoded):
        raise ValueError(f"{label} must be canonical binary64 hexadecimal text")
    try:
        binary64 = float.fromhex(encoded)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            f"{label} must be canonical binary64 hexadecimal text"
        ) from exc
    if not isfinite(binary64) or binary64.hex() != encoded:
        raise ValueError(f"{label} must be canonical binary64 hexadecimal text")
    return binary64


__all__ = [
    "HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2",
    "decode_binary64_v1",
    "encode_binary64_v1",
]
