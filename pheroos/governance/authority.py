from __future__ import annotations

from enum import IntEnum


class AuthorityLevel(IntEnum):
    OBSERVER = 1
    AGENT = 2
    TRUSTED_AGENT = 3
    GOVERNANCE = 4
    KERNEL = 5


def can_verify(level: AuthorityLevel) -> bool:
    return level >= AuthorityLevel.GOVERNANCE
