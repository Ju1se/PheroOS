from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pheroos.governance.commit_state as commit_state
import pheroos.governance.distributed_commit as distributed_commit
import pheroos.governance.support_lease as support_lease


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "pheroos" / "governance"


PARENTS = {
    "_commit_state": commit_state,
    "_support": support_lease,
    "_distributed": distributed_commit,
}


PRIVATE_HELPER_OWNERS = {
    "_commit_state.invariants": (
        "_normalized_window_bindings",
        "_validate_bound_commit_policy",
        "_validate_commit_binding_values",
    ),
    "_commit_state._liveness_contract": (
        "_validate_assessment_lineage_roots",
        "_validate_sealed_heartbeat_lineage",
    ),
    "_commit_state._window_contract": (
        "_commit_window_authority_key",
        "_validate_window_threshold_snapshot",
        "_window_root",
    ),
    "_support.invariants": (
        "_canonical_fingerprints",
        "_normalized_bindings",
        "_validate_support_policy",
    ),
    "_distributed.invariants": (
        "_canonical_fingerprints",
        "_public_dataclass_payload",
        "_quorum_intersection_is_safe",
        "_validate_distributed_policy",
    ),
    "_distributed._membership_contract": (
        "_portable_member",
        "_validate_membership_policy",
        "_validate_portable_membership_snapshot",
    ),
    "_distributed._proposal_contract": (
        "_validate_proposal_certificate_lineage",
        "_validate_proposal_membership",
        "_validate_receipt_certificate_lineage",
    ),
    "_distributed._witness_contract": (
        "_attestation_matches",
        "_require_attestation_bindings",
        "_validate_witness_proposal_binding",
    ),
}


PUBLIC_OWNER_EXPORTS = {
    "_commit_state.records": (
        "DecisionProgress",
        "CommitReplayState",
        "ReplayReceipt",
        "commit_replay_state_matches",
        "decision_outcome_payload",
    ),
    "_commit_state.window": (
        "initialize_commit_window_state",
        "advance_commit_window_state",
        "restart_commit_window_epoch",
        "commit_window_seal_for_state",
    ),
    "_commit_state.replay": (
        "initialize_commit_replay_state",
        "record_commit_replay_receipts",
    ),
    "_commit_state.liveness": (
        "issue_commit_liveness_input",
        "reduce_commit_liveness",
        "select_terminal_outcome_kind",
    ),
    "_support.records": (
        "SupportLease",
        "SupportLeaseReplayState",
        "support_lease_fingerprint",
    ),
    "_support.membership": (
        "issue_eligible_principal_snapshot",
        "eligible_principal_snapshot_matches",
    ),
    "_support.replay": (
        "initialize_support_lease_replay_state",
        "support_lease_replay_state_is_current",
    ),
    "_support.lease": (
        "issue_support_lease",
        "revoke_support_lease",
        "support_lease_status",
    ),
    "_support.evaluation": ("evaluate_support_leases",),
    "_distributed.membership": (
        "PortableMembershipSnapshot",
        "portable_membership_snapshot_from_eligible",
        "portable_membership_snapshot_payload",
    ),
    "_distributed.proposal": (
        "DistributedCommitProposal",
        "issue_distributed_commit_proposal",
        "verify_distributed_commit_proposal",
    ),
    "_distributed.witness": (
        "QuorumWitness",
        "WitnessVerification",
        "verify_quorum_witness",
        "verify_portable_witness_verification",
    ),
    "_distributed.state": (
        "DistributedCommitState",
        "initialize_distributed_commit_state",
        "record_witness_verifications",
    ),
    "_distributed.certificate": (
        "DistributedCommitCertificate",
        "issue_distributed_commit_certificate",
        "verify_distributed_commit_certificate",
    ),
    "_distributed.epoch": (
        "EpochTransitionCertificate",
        "issue_epoch_transition_certificate",
        "transition_distributed_commit_epoch",
    ),
    "_distributed.finality": (
        "DistributedFinalityDecision",
        "evaluate_distributed_finality",
    ),
}


def _definitions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _owner_path(relative_module: str) -> Path:
    return GOVERNANCE / Path(*relative_module.split(".")).with_suffix(".py")


def test_public_lifecycle_exports_have_one_static_owner() -> None:
    all_owner_definitions = {
        module: _definitions(_owner_path(module)) for module in PUBLIC_OWNER_EXPORTS
    }
    for relative_module, names in PUBLIC_OWNER_EXPORTS.items():
        owner = importlib.import_module(f"pheroos.governance.{relative_module}")
        parent = PARENTS[relative_module.split(".", 1)[0]]
        parent_definitions = _definitions(Path(parent.__file__).resolve())
        for name in names:
            assert name in all_owner_definitions[relative_module]
            assert name not in parent_definitions
            assert getattr(parent, name) is getattr(owner, name)
            occurrences = sum(
                name in definitions for definitions in all_owner_definitions.values()
            )
            assert occurrences == 1


def test_private_helpers_have_static_owners_without_facade_definitions() -> None:
    for relative_module, names in PRIVATE_HELPER_OWNERS.items():
        owner_definitions = _definitions(_owner_path(relative_module))
        parent = PARENTS[relative_module.split(".", 1)[0]]
        parent_definitions = _definitions(Path(parent.__file__).resolve())
        for name in names:
            assert name in owner_definitions
            assert name not in parent_definitions


def test_aggregate_modules_are_alias_facades_with_one_compatibility_wrapper() -> None:
    assert _definitions(Path(commit_state.__file__).resolve()) == set()
    assert _definitions(Path(support_lease.__file__).resolve()) == set()
    assert _definitions(Path(distributed_commit.__file__).resolve()) == {
        "register_distributed_commit_certificate"
    }


def test_private_lifecycle_modules_never_import_public_parent_modules() -> None:
    forbidden = {
        "pheroos.governance.commit_state",
        "pheroos.governance.distributed_commit",
        "pheroos.governance.support_lease",
    }
    offenders: list[str] = []
    for directory in ("_commit_state", "_distributed", "_support"):
        for path in sorted((GOVERNANCE / directory).glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                    offenders.append(path.relative_to(ROOT).as_posix())
                elif isinstance(node, ast.Import) and any(
                    alias.name in forbidden for alias in node.names
                ):
                    offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_public_records_and_algorithms_keep_canonical_modules() -> None:
    assert commit_state.DecisionProgress.__module__ == commit_state.__name__
    assert commit_state.reduce_commit_liveness.__module__ == commit_state.__name__
    assert support_lease.SupportLease.__module__ == support_lease.__name__
    assert support_lease.evaluate_support_leases.__module__ == support_lease.__name__
    assert (
        distributed_commit.DistributedCommitProposal.__module__
        == distributed_commit.__name__
    )
    assert (
        distributed_commit.evaluate_distributed_finality.__module__
        == distributed_commit.__name__
    )


def test_distributed_wire_constants_are_direct_public_abi_literals() -> None:
    names = {
        "DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR",
        "DISTRIBUTED_COMMIT_CERTIFICATE_VERSION",
        "DISTRIBUTED_COMMIT_VALUE_VERSION",
        "DISTRIBUTED_FINALITY_DECISION_VERSION",
        "DISTRIBUTED_PROPOSAL_VERSION",
        "DISTRIBUTED_STATE_VERSION",
        "EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR",
        "EPOCH_TRANSITION_CERTIFICATE_VERSION",
        "QUORUM_WITNESS_VERSION",
        "WITNESS_VERIFICATION_VERSION",
    }
    tree = ast.parse(Path(distributed_commit.__file__).read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    assert set(assignments) == names
    assert all(isinstance(value, ast.Constant) for value in assignments.values())
    internal = importlib.import_module("pheroos.governance._distributed.constants")
    assert all(
        getattr(distributed_commit, name) == getattr(internal, name)
        for name in names
    )


def test_distributed_lifecycle_edges_follow_declared_layering() -> None:
    allowed = {
        "membership": {"invariants", "_membership_contract"},
        "proposal": {
            "constants",
            "invariants",
            "records",
            "membership",
            "_membership_contract",
            "_proposal_contract",
        },
        "witness": {
            "constants",
            "invariants",
            "records",
            "membership",
            "proposal",
            "_membership_contract",
            "_witness_contract",
        },
        "state": {
            "constants",
            "invariants",
            "records",
            "membership",
            "witness",
            "_membership_contract",
            "_state_contract",
        },
        "certificate": {
            "constants",
            "invariants",
            "records",
            "membership",
            "proposal",
            "witness",
            "state",
            "_membership_contract",
            "_state_contract",
            "_certificate_contract",
        },
        "epoch": {
            "constants",
            "invariants",
            "records",
            "membership",
            "state",
            "_membership_contract",
            "_state_contract",
            "_witness_contract",
            "_epoch_contract",
        },
        "finality": {
            "constants",
            "invariants",
            "records",
            "state",
            "certificate",
            "_certificate_contract",
            "_finality_contract",
        },
    }
    prefix = "pheroos.governance._distributed."
    for module, allowed_dependencies in allowed.items():
        path = GOVERNANCE / "_distributed" / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        dependencies = {
            node.module.removeprefix(prefix)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(prefix)
        }
        assert dependencies <= allowed_dependencies
