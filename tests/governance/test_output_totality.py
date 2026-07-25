from __future__ import annotations

from copy import copy
from hashlib import sha256
from typing import Any

import pytest

from pheroos.governance.certificate import local_commit_receipt_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance.output import (
    CommitOutputAction,
    CommitOutputAuthorization,
    _authorize_terminal_action,
    _bound_certificate,
    _commit_output_policy_matches,
    _commit_output_threshold_matches,
    _distributed_certificate_lineage_matches_outcome,
    _safe_distributed_conflict_root,
    _safe_distributed_state_ref,
    _safe_permission_ref,
    _safe_policy_ref,
    _safe_stop_ref,
    _safe_threshold_ref,
    authorize_terminal_publication,
    commit_output_authorization_payload,
    deliver_terminal_outcome,
)
from pheroos.protocol.commit_models import CommitAction, CommitAssurance
from tests.governance.test_commit_output_actions import (
    _action_authorities,
    _evidence_commit_outcome,
)
from tests.governance.test_distributed_commit import _public_portable_scenario


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


ROOT = _root("output-totality")
PROFILE = "pheroos-commit-integrity-v1"


def _authorization(**changes: object) -> CommitOutputAuthorization:
    values: dict[str, object] = {
        "action": CommitOutputAction.DELIVER,
        "authorized": False,
        "profile": PROFILE,
        "outcome_ref": "",
        "certificate_ref": "",
        "output_payload_fingerprint": "",
        "policy_ref": "",
        "threshold_ref": "",
        "stop_resolution_ref": "",
        "permission_ref": "",
        "distributed_state_ref": "",
        "distributed_conflict_root": "",
        "gates": {"gate": False},
        "reason_codes": ("gate",),
    }
    values.update(changes)
    return CommitOutputAuthorization(**values)  # type: ignore[arg-type]


def test_public_terminal_entry_points_fail_closed_on_malformed_inputs() -> None:
    delivery = deliver_terminal_outcome(
        object(),  # type: ignore[arg-type]
        output_payload_fingerprint="not-a-fingerprint",
    )
    assert not delivery.authorized
    assert delivery.action is CommitOutputAction.DELIVER

    publication = authorize_terminal_publication(
        object(),  # type: ignore[arg-type]
        commit_policy=object(),  # type: ignore[arg-type]
        threshold_snapshot=object(),  # type: ignore[arg-type]
        certificate=object(),  # type: ignore[arg-type]
        output_payload_fingerprint="not-a-fingerprint",
        stop_resolution=object(),  # type: ignore[arg-type]
        permission=object(),  # type: ignore[arg-type]
        current_step=-1,
    )
    assert not publication.authorized
    assert publication.action is CommitOutputAction.PUBLISH


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"authorized": 1}, "authorized must be boolean"),
        ({"gates": {}}, "gates are required"),
        ({"gates": {"": False}}, "gate name is invalid"),
        ({"gates": {"gate": 0}}, "gate value must be boolean"),
        (
            {"authorized": True, "gates": {"gate": True}},
            "requires outcome and payload refs",
        ),
        (
            {"distributed_state_ref": ROOT},
            "state and conflict roots must be bound together",
        ),
        (
            {"certificate_ref": ROOT},
            "delivery cannot claim publish/execute authority refs",
        ),
        (
            {
                "action": CommitOutputAction.PUBLISH,
                "authorized": True,
                "gates": {"gate": True},
                "outcome_ref": ROOT,
                "output_payload_fingerprint": ROOT,
            },
            "requires every authority ref",
        ),
    ),
)
def test_commit_output_authorization_constructor_guards_are_total(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        _authorization(**changes)


def test_commit_output_payload_requires_the_canonical_record() -> None:
    with pytest.raises(GovernanceError, match="canonical record"):
        commit_output_authorization_payload(object())  # type: ignore[arg-type]


def test_certificate_binding_totality_rejects_wrong_assurance_shapes() -> None:
    scenario, _, _, output_ref, _, outcome = _evidence_commit_outcome()
    common: dict[str, Any] = {
        "commit_policy": scenario.policy,
        "output_payload_fingerprint": output_ref,
        "trusted_issuer_attestations": None,
        "distributed_state": None,
        "portable_certificate": None,
        "trusted_witness_attestations": None,
    }

    assert _bound_certificate(None, object(), **common) == ("", False)

    certified = copy(outcome)
    object.__setattr__(certified, "assurance", CommitAssurance.CERTIFIED)
    assert _bound_certificate(certified, object(), **common) == ("", False)

    distributed = copy(outcome)
    object.__setattr__(distributed, "assurance", CommitAssurance.DISTRIBUTED)
    assert _bound_certificate(distributed, object(), **common) == ("", False)

    assert not _distributed_certificate_lineage_matches_outcome(
        object(),  # type: ignore[arg-type]
        outcome,
        output_payload_fingerprint=output_ref,
    )


def test_internal_action_guard_rejects_non_publication_action() -> None:
    with pytest.raises(GovernanceError, match="must be publish or execute"):
        _authorize_terminal_action(
            object(),  # type: ignore[arg-type]
            action=CommitAction.RECOVERY,
            commit_policy=object(),  # type: ignore[arg-type]
            threshold_snapshot=object(),  # type: ignore[arg-type]
            certificate=object(),  # type: ignore[arg-type]
            output_payload_fingerprint="",
            stop_resolution=object(),  # type: ignore[arg-type]
            permission=object(),  # type: ignore[arg-type]
            current_step=0,
            trusted_issuer_attestations=None,
            distributed_state=None,
            portable_certificate=None,
            trusted_witness_attestations=None,
        )


def test_safe_reference_helpers_fail_closed_on_corrupted_canonical_records() -> None:
    scenario, _, _, _, receipt, outcome = _evidence_commit_outcome()
    certificate_ref = local_commit_receipt_fingerprint(receipt)
    stop, permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=certificate_ref,
        issued_at_step=outcome.current_step,
        expires_at_step=outcome.current_step + 2,
    )

    invalid_outcome = copy(outcome)
    object.__setattr__(invalid_outcome, "profile", "")
    assert not _commit_output_policy_matches(scenario.policy, invalid_outcome)
    assert _safe_policy_ref(scenario.policy, invalid_outcome) == ""

    invalid_threshold = copy(scenario.threshold)
    object.__setattr__(invalid_threshold, "profile", "")
    assert not _commit_output_threshold_matches(invalid_threshold, outcome)
    assert _safe_threshold_ref(invalid_threshold) == ""

    invalid_stop = copy(stop)
    object.__setattr__(invalid_stop, "profile", "")
    assert _safe_stop_ref(invalid_stop) == ""

    invalid_permission = copy(permission)
    object.__setattr__(invalid_permission, "profile", "")
    assert _safe_permission_ref(invalid_permission) == ""

    distributed = _public_portable_scenario("output-totality-safe-reference")
    invalid_state = copy(distributed.state)
    object.__setattr__(invalid_state, "profile", "")
    assert _safe_distributed_state_ref(invalid_state) == ""
    assert _safe_distributed_conflict_root(invalid_state) == ""
