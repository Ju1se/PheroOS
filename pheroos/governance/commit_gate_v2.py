"""Public Draft ABI for durable Commit Stop and Permission v2 authority.

Portable snapshots describe deterministic gate decisions only.  Authority
requires exact source reconstruction, a least-privilege authority session, and
atomic inclusion in the corresponding StateStore v2 fixed stream.
"""

from __future__ import annotations

from pheroos.governance._commit_gate_v2 import *  # noqa: F403
from pheroos.governance._commit_gate_v2 import __all__ as _PRIVATE_ALL


_PUBLIC_MODULE = __name__
for _name in _PRIVATE_ALL:
    _value = globals()[_name]
    if callable(_value) and getattr(_value, "__module__", "").startswith(
        "pheroos.governance._commit_gate_v2"
    ):
        _value.__module__ = _PUBLIC_MODULE
del _name, _value

__all__ = list(_PRIVATE_ALL)
