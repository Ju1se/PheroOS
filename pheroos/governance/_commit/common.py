from __future__ import annotations

from enum import StrEnum


class AuthorityScope(StrEnum):
    NONE = "none"
    GOVERNANCE_LOCAL = "governance_local"
    CERTIFIED = "certified"
    DISTRIBUTED = "distributed"
    DENIAL = "denial"


AuthorityScope.__module__ = "pheroos.governance.commit_state"


__all__ = ["AuthorityScope"]
