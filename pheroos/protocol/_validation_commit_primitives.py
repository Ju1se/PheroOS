from __future__ import annotations

from typing import cast

from pheroos.protocol.commit_models import MAX_AUTHORITY_INTEGER


def authority_integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_AUTHORITY_INTEGER


def authority_integer_in_range(
    value: object,
    minimum: int,
    maximum: int,
) -> bool:
    return authority_integer(value) and minimum <= cast(int, value) <= maximum
