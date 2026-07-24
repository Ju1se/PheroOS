"""Small Unicode scalar-value checks shared by portable ABI boundaries."""

from __future__ import annotations


def contains_surrogate_code_point(value: str) -> bool:
    """Return whether *value* contains a non-scalar Unicode surrogate."""

    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


__all__ = ["contains_surrogate_code_point"]
