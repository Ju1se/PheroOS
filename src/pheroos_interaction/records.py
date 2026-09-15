"""Local execution records, extracted from runtime/store.py (MIT).

Only the four concrete exceptions/lease fields used by current execution remain.
A run identity is added to fence leases between separate local sessions.
"""
from dataclasses import dataclass


class StateError(RuntimeError):
    pass


class BudgetExceeded(StateError):
    pass


class LeaseLost(StateError):
    pass


@dataclass(frozen=True)
class Lease:
    task_id: str
    version: int
    owner: str
    epoch: int
    run_id: str
