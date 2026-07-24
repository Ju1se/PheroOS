"""Lazy namespace for Conformance check modules.

Importing one check must not execute every sibling check and, in particular,
must not initialize frozen v1 compatibility authority while loading a durable
v2 contract.
"""

from importlib import import_module
from types import ModuleType

__all__ = [
    "authority_ledger_contract",
    "authority_session_v2_contract",
    "authority_store_v2_contract",
    "baseline_output_v2_contract",
    "certificate_conflict_contract",
    "certificate_output_contract",
    "challenge_coverage_contract",
    "commit_authority_boundary",
    "commit_certificate_contract",
    "commit_certificate_v2_contract",
    "commit_channel_separation",
    "commit_decision_v2_contract",
    "commit_evidence_v2_contract",
    "commit_finality_v2_contract",
    "commit_gate_v2_contract",
    "commit_liveness_contract",
    "commit_metrics_contract",
    "commit_numeric_contract",
    "commit_policy_contract",
    "commit_replay_v2_contract",
    "commit_trace_contract",
    "commit_window_contract",
    "counterevidence_contract",
    "distributed_commit_v2_contract",
    "distributed_finality_contract",
    "driver_invocation_v2_contract",
    "hybrid_replay_v2_contract",
    "membership_snapshot_contract",
    "no_assurance_downgrade",
    "observation_binding_contract",
    "principal_attestation_contract",
    "risk_monotonicity_contract",
    "risk_v2_contract",
    "runtime_integration_v1_contract",
    "runtime_scope_contract",
    "scoped_trace_store_v2_contract",
    "support_v2_contract",
    "support_lease_contract",
    "trace_store_contract",
]


def __getattr__(name: str) -> ModuleType:
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
