from __future__ import annotations

import copy
from dataclasses import replace
import inspect
import json
import math
import pickle
from types import SimpleNamespace
from types import MappingProxyType
from typing import Any, cast

import pytest

import pheroos.governance._pheromone.legacy_normalization as legacy_pheromone
import pheroos.governance._pheromone.diffusion as pheromone_diffusion
import pheroos.governance._pheromone.policy_validation as pheromone_policy_validation
import pheroos.governance._pheromone.scoring as pheromone_scoring
import pheroos.governance._risk_v2.contracts as risk_contracts
import pheroos.governance._risk_v2.operations as risk_operations
import pheroos.governance._risk_v2.resources as risk_resources
import pheroos.governance._risk_v2.source as risk_source
import pheroos.governance._risk_v2.state_support as risk_state_support
import pheroos.governance._risk.chain as legacy_risk_chain
import pheroos.governance._risk.records as legacy_risk_records
import pheroos.governance._schema.commit as commit_schema
import pheroos.governance._schema.common as schema_common
import pheroos.governance._schema.foundation as foundation_schema
import pheroos.governance._schema.hybrid as hybrid_schema
import pheroos.governance._schema.distributed as distributed_schema
import pheroos.governance._support.evaluation as legacy_support_evaluation
import pheroos.governance._support.lease as legacy_support_lease
import pheroos.governance._support.membership as legacy_support_membership
import pheroos.governance._support_v2.common as support_common
import pheroos.governance._support_v2.membership_contracts as membership_contracts
import pheroos.governance._support_v2.membership_operations as membership_operations
import pheroos.governance._support_v2.membership_source as membership_source_module
import pheroos.governance._support_v2.membership_state as membership_state_module
import pheroos.governance._support_v2.principal_verification_operations as verification_operations
import pheroos.governance._support_v2.principal_verification_state as verification_state_module
import pheroos.governance._support_v2.support_evaluation_engine as support_evaluation_engine
import pheroos.governance._support_v2.support_operations as support_operations
import pheroos.governance._support_v2.support_projection as support_projection
import pheroos.governance._support_v2.support_request_contracts as support_request_contracts
import pheroos.governance._support_v2.support_snapshot_contracts as support_snapshot_contracts
import pheroos.governance._support_v2.support_source_binding as support_source_binding
import pheroos.governance._support_v2.support_source_proof as support_source_proof
import pheroos.governance._support_v2.support_state_access as support_state_access
import pheroos.governance._support_v2.support_state_handle as support_state_handle
import pheroos.governance._support_v2.support_state_load as support_state_load
import pheroos.governance._support_v2.support_verification as support_verification
import pheroos.governance._swarm.pipeline as swarm_pipeline
import pheroos.governance._swarm.replay as swarm_replay
import pheroos.governance._swarm.scoring as swarm_scoring
import pheroos.governance._swarm.signals as swarm_signals
import pheroos.governance._swarm.trace as swarm_trace
from pheroos.governance._risk_v2.contracts import (
    RiskAssessmentRecordV2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
    risk_state_stream_ref_v2,
)
from pheroos.governance._risk_v2.operations import VerifiedRiskStateV2
from pheroos.governance._risk_v2.source import VerifiedRiskSourceV2
from pheroos.governance.risk_v2 import rehydrate_risk_state_v2
from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import (
    PheromoneBudgetState,
    PheromoneDiffusionPolicy,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    _reject_duplicate_trail_events,
    diffuse_pheromone_trails_with_records,
    evaporate_trails_with_records,
    is_expired,
    validate_pheromone_budget_state,
)
from pheroos.governance.collective import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
)
from pheroos.governance._support_v2.support_evaluation_engine import (
    _group_equivocation,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _assurance as support_assurance,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
    canonical_support_leases_v2,
)
from pheroos.governance._support_v2.support_projection import (
    _current_projection,
)
from pheroos.governance._support_v2.support_request_contracts import (
    SupportAdvanceRequestV2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    MAX_SUPPORT_EVICTIONS_V2,
    support_mutation_delta_root_v2,
)
from pheroos.protocol.commit_models import MAX_AUTHORITY_INTEGER
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.protocol.models import PheromoneKindProfile
from tests.governance.test_hybrid_pheromone_hardening import (
    candidates as pheromone_candidates,
)
from tests.governance.test_hybrid_pheromone_hardening import (
    policy as pheromone_policy,
)
from tests.governance.test_hybrid_pheromone_hardening import (
    trail as pheromone_trail,
)
from tests.governance.test_collective_decision import (
    declared_candidates as collective_candidates,
)
from tests.governance.test_collective_decision import (
    policy as collective_policy,
)
from tests.governance.test_hybrid_authority import (
    candidates as hybrid_candidates,
)
from tests.governance.test_hybrid_authority import (
    policy as hybrid_policy,
)
from tests.governance.test_risk_v2_owner import (
    _advance as risk_advance,
)
from tests.governance.test_risk_v2_owner import (
    _context as risk_context,
)
from tests.governance.test_risk_v2_owner import (
    _request as risk_request,
)
from tests.governance.test_risk_v2_owner import (
    _manifest as risk_manifest,
)
from tests.governance.test_commit_risk import (
    RiskBand as LegacyRiskBand,
)
from tests.governance.test_commit_risk import (
    initialize_chain as legacy_initialize_risk_chain,
)
from tests.governance.test_commit_risk import (
    issue_assessment as legacy_issue_risk_assessment,
)
from tests.governance.test_commit_risk import (
    policy as legacy_risk_policy,
)
from tests.governance.test_commit_risk import (
    threshold as legacy_risk_threshold,
)
from tests.governance.test_support_lease import (
    commit_policy as legacy_support_policy,
)
from tests.governance.test_support_lease import (
    issue_lease as legacy_issue_support_lease,
)
from tests.governance.test_support_lease import (
    membership as legacy_support_membership_snapshot,
)
from tests.governance.test_support_lease import (
    observation as legacy_support_observation,
)
from tests.governance.test_support_lease import (
    principal as legacy_support_principal,
)
from tests.governance.test_support_lease import (
    proposal as legacy_support_proposal,
)
from tests.governance.test_support_lease import (
    replay_state as legacy_support_replay_state,
)
from tests.governance.test_support_v2_public_semantics import (
    ISSUER_REF as SUPPORT_ISSUER_REF,
)
from tests.governance.test_support_v2_public_semantics import (
    _advance_support,
    _capability as support_capability,
    _commit_verification,
    _initialize as support_initialize,
    _ledger as support_ledger,
    _observation as support_observation,
    _prepare_issue as support_prepare_issue,
    _prepare_membership,
    _prepare_switch as support_prepare_switch,
    _prepare_verification,
    _proposal as support_proposal,
    _support_state,
    _upstream as support_upstream,
)


@pytest.fixture(scope="module")
def support_scenario() -> SimpleNamespace:
    ledger = support_ledger("totality-regression")
    upstream = support_upstream(ledger, label="totality-regression")
    initialized, initialized_source = support_initialize(
        ledger,
        label="totality-regression",
    )
    initialized_attempt = _advance_support(ledger, initialized, initialized_source)
    assert initialized_attempt.committed_transition is not None
    initialized_state = _support_state(ledger, initialized)
    issued, issued_source = support_prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:alpha",
        claim_root="sha256:" + "a" * 64,
        principal_ref="principal:alpha",
        label="totality-regression",
        current_step=4,
    )
    issued_attempt = _advance_support(ledger, issued, issued_source)
    assert issued_attempt.committed_transition is not None
    issued_state = _support_state(ledger, issued)
    switched, switched_source = support_prepare_switch(
        ledger,
        issued_state,
        upstream.membership_state,
        prior_lease_root=issued.snapshot.leases[0].lease_root,
        candidate_ref="candidate:beta",
        claim_root="sha256:" + "a" * 64,
        principal_ref="principal:alpha",
        label="totality-regression",
        current_step=5,
    )
    return SimpleNamespace(
        ledger=ledger,
        upstream=upstream,
        initialized=initialized,
        initialized_source=initialized_source,
        initialized_state=initialized_state,
        issued=issued,
        issued_source=issued_source,
        issued_state=issued_state,
        switched=switched,
        switched_source=switched_source,
    )


@pytest.fixture(scope="module")
def risk_scenario() -> SimpleNamespace:
    context = risk_context(scope_ref="scope:risk-v2:totality-handles")
    request, source = risk_request(
        context,
        advance_ref="advance:risk-v2:totality-handles",
    )
    attempt, session = risk_advance(context, request, source)
    assert attempt.committed_transition is not None
    state = rehydrate_risk_state_v2(
        json.loads(request.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    return SimpleNamespace(
        context=context,
        request=request,
        source=source,
        attempt=attempt,
        session=session,
        state=state,
    )


def _risk_values() -> tuple[
    RiskAssessmentRecordV2,
    RiskThresholdSnapshotV2,
    RiskStateSnapshotV2,
]:
    context = risk_context(scope_ref="scope:risk-v2:totality")
    request, _ = risk_request(context, advance_ref="advance:risk-v2:totality")
    return request.snapshot.assessment, request.snapshot.threshold, request.snapshot


def _forged_dataclass(value: Any, **changes: object) -> Any:
    forged = object.__new__(type(value))
    for field in type(value).__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(forged, field, getattr(value, field))
    for field, replacement in changes.items():
        object.__setattr__(forged, field, replacement)
    return forged


def _shallow_committed_view(
    request: Any,
    *,
    events: tuple[object, ...] = (),
    **receipt_changes: object,
) -> SimpleNamespace:
    receipt_values = {
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "revision": request.snapshot.revision,
        "parent_root": "sha256:" + "1" * 64,
        "head_root": "sha256:" + "2" * 64,
    }
    receipt_values.update(receipt_changes)
    return SimpleNamespace(
        disposition=support_state_load.GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        position_observation=object(),
        committed_transition=SimpleNamespace(
            receipt=SimpleNamespace(**receipt_values),
            batch=SimpleNamespace(
                transition=SimpleNamespace(state_records=()),
                read_set=SimpleNamespace(entries=(), root=lambda: "read-set"),
                trace_batch=SimpleNamespace(events=events),
            ),
        ),
    )


@pytest.fixture(scope="module")
def legacy_support_scenario() -> SimpleNamespace:
    policy = legacy_support_policy()
    verification = legacy_support_principal(
        "principal:totality",
        "cluster:totality",
        index=91,
        policy=policy,
    )
    membership, membership_state = legacy_support_membership_snapshot(
        (verification,),
        policy=policy,
    )
    observation = legacy_support_observation(
        verification,
        candidate_id="candidate:alpha",
        index=91,
        policy=policy,
    )
    proposal = legacy_support_proposal(
        verification,
        observation,
        candidate_id="candidate:alpha",
        index=91,
        policy=policy,
    )
    initial_replay = legacy_support_replay_state()
    lease, replay = legacy_issue_support_lease(
        verification,
        observation,
        membership,
        membership_state,
        initial_replay,
        candidate_id="candidate:alpha",
        index=91,
        current_step=4,
        policy=policy,
    )
    return SimpleNamespace(
        policy=policy,
        verification=verification,
        membership=membership,
        membership_state=membership_state,
        observation=observation,
        proposal=proposal,
        initial_replay=initial_replay,
        lease=lease,
        replay=replay,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"risk_band": cast(Any, "LOW")}, "risk assessment band is invalid"),
        ({"expires_at_step": 2}, "risk assessment expiry must be after issuance"),
        (
            {"window_reset_required": cast(Any, 1)},
            "window_reset_required must be an exact bool",
        ),
        (
            {"window_reset_required": True},
            "initial risk assessment cannot require a window reset",
        ),
    ],
)
def test_risk_assessment_contract_rejects_noncanonical_values(
    changes: dict[str, object],
    message: str,
) -> None:
    assessment, _, _ = _risk_values()

    with pytest.raises((TypeError, ValueError), match=message):
        replace(assessment, assessment_root="", **changes)


def test_risk_assessment_wire_methods_and_unsupported_enum() -> None:
    assessment, _, _ = _risk_values()

    assert assessment.canonical_bytes()
    assert assessment.root() == assessment.assessment_root
    payload = assessment.to_dict()
    payload["risk_band"] = "EXTREME"
    with pytest.raises(ValueError, match="risk assessment band is unsupported"):
        RiskAssessmentRecordV2.from_dict(payload)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"risk_band": cast(Any, "LOW")}, "risk threshold band is invalid"),
        ({"minimum_positive_evidence": 0}, "positive minima must be positive"),
        (
            {"maximum_counterevidence_ratio_ppm": 1_000_001},
            "counterevidence ratio exceeds one",
        ),
        ({"minimum_support_ratio_ppm": 0}, "support ratio is outside its bound"),
        (
            {"minimum_assurance": cast(Any, "evidence_bound")},
            "minimum assurance is invalid",
        ),
    ],
)
def test_risk_threshold_contract_rejects_noncanonical_values(
    changes: dict[str, object],
    message: str,
) -> None:
    _, threshold, _ = _risk_values()

    with pytest.raises((TypeError, ValueError), match=message):
        replace(threshold, threshold_root="", **changes)


def test_risk_threshold_wire_methods_and_unsupported_enum() -> None:
    _, threshold, _ = _risk_values()

    assert threshold.canonical_bytes()
    assert threshold.root() == threshold.threshold_root
    for field in ("risk_band", "minimum_assurance"):
        payload = threshold.to_dict()
        payload[field] = "unsupported"
        with pytest.raises(
            ValueError, match="risk threshold enum value is unsupported"
        ):
            RiskThresholdSnapshotV2.from_dict(payload)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"assurance": cast(Any, "evidence_bound")}, "snapshot assurance is invalid"),
        ({"revision": 2}, "revision continuity is invalid"),
        ({"parent_epoch": 1}, "genesis parent epoch must be null"),
        (
            {"parent_transition_id": "transition:forged"},
            "genesis parent transition is mismatched",
        ),
        (
            {"parent_snapshot_root": "sha256:" + "f" * 64},
            "genesis parent root is mismatched",
        ),
        ({"assessment": cast(Any, object())}, "snapshot assessment is invalid"),
        ({"threshold": cast(Any, object())}, "snapshot threshold is invalid"),
    ],
)
def test_risk_snapshot_contract_rejects_noncanonical_values(
    changes: dict[str, object],
    message: str,
) -> None:
    _, _, snapshot = _risk_values()

    with pytest.raises((TypeError, ValueError), match=message):
        replace(snapshot, snapshot_root="", **changes)


def test_risk_snapshot_binding_freshness_identity_and_wire_methods() -> None:
    assessment, threshold, snapshot = _risk_values()

    with pytest.raises(ValueError, match="assessment/threshold binding is mismatched"):
        replace(
            snapshot,
            threshold=replace(
                threshold,
                assessment_root="sha256:" + "a" * 64,
                threshold_root="",
            ),
            snapshot_root="",
        )
    with pytest.raises(ValueError, match="assessment is not fresh"):
        future_assessment = replace(
            assessment,
            issued_at_step=snapshot.current_step + 1,
            expires_at_step=snapshot.current_step + 2,
            assessment_root="",
        )
        replace(
            snapshot,
            assessment=future_assessment,
            threshold=replace(
                threshold,
                assessment_root=future_assessment.assessment_root,
                threshold_root="",
            ),
            snapshot_root="",
        )
    with pytest.raises(ValueError, match="stream or transition identity is mismatched"):
        replace(snapshot, stream_ref="stream:forged", snapshot_root="")

    assert snapshot.canonical_bytes()
    assert snapshot.root() == snapshot.snapshot_root
    payload = snapshot.to_dict()
    payload["assurance"] = "unsupported"
    with pytest.raises(ValueError, match="risk snapshot assurance is unsupported"):
        RiskStateSnapshotV2.from_dict(payload)


def test_risk_stream_rejects_non_enum_assurance() -> None:
    _, threshold, snapshot = _risk_values()

    with pytest.raises(TypeError, match="risk stream assurance is invalid"):
        risk_state_stream_ref_v2(
            snapshot.scope_ref,
            snapshot.profile,
            cast(Any, "evidence_bound"),
            snapshot.manifest_root,
            snapshot.commit_policy_root,
            threshold.risk_policy_root,
            snapshot.protocol_ref,
            snapshot.run_ref,
            snapshot.target_ref,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"enabled": 1}, "enabled must be boolean"),
        ({"feedback_enabled": 1}, "feedback_enabled must be boolean"),
        ({"exploration_enabled": 1}, "exploration_enabled must be boolean"),
        ({"require_provenance": 1}, "requirements must be boolean"),
        ({"evaporation_rate": 2.0}, "evaporation_rate must be between"),
        ({"decay_model": "unknown"}, "unsupported pheromone decay model"),
        (
            {"min_strength": 2.0, "max_strength": 1.0},
            "min_strength must not exceed",
        ),
        ({"exploration_floor": 2.0}, "exploration_floor must be between"),
        (
            {"min_strength": 2.0, "per_source_cap": 1.0},
            "minimum strength must fit",
        ),
        ({"novelty_decay_rate": 2.0}, "novelty_decay_rate must be between"),
        ({"min_source_diversity": 0}, "min_source_diversity must be"),
        ({"response_model": "unknown"}, "unsupported pheromone response model"),
        ({"competition_mode": "unknown"}, "unsupported pheromone competition mode"),
        (
            {"scored_subject_types": ("candidate", "candidate")},
            "must not contain duplicates",
        ),
    ],
)
def test_pheromone_policy_rejects_invalid_scalar_boundaries(
    changes: dict[str, object],
    message: str,
) -> None:
    selected = pheromone_policy(**changes)

    with pytest.raises(GovernanceError, match=message):
        pheromone_policy_validation.validate_pheromone_policy_rules(
            selected,
            finite_number=lambda value, _: float(value),
            non_negative_number=lambda value, _: float(value),
            non_negative_step=lambda value, _: int(value),
        )


@pytest.mark.parametrize(
    ("kind", "profile", "message"),
    [
        ("invalid", PheromoneKindProfile(), "unsupported pheromone kind profile"),
        ("positive", cast(Any, object()), "kind profile has invalid type"),
        (
            "positive",
            PheromoneKindProfile(evaporation_rate=2.0),
            "evaporation_rate must be between",
        ),
        (
            "positive",
            PheromoneKindProfile(response_model="unknown"),
            "unsupported pheromone kind profile response model",
        ),
        (
            "positive",
            PheromoneKindProfile(priority=-1),
            "priority must be a non-negative integer",
        ),
        (
            "positive",
            PheromoneKindProfile(can_suppress_positive=cast(Any, 1)),
            "can_suppress_positive must be boolean",
        ),
        (
            "positive",
            PheromoneKindProfile(scored_subject_types=("candidate", "candidate")),
            "subject types must not contain duplicates",
        ),
        (
            "stale",
            PheromoneKindProfile(weight=1.0),
            "stale pheromone kind profile must remain no-score",
        ),
    ],
)
def test_pheromone_kind_profile_rejects_invalid_boundaries(
    kind: str,
    profile: object,
    message: str,
) -> None:
    selected = pheromone_policy(
        kind_profiles=MappingProxyType({kind: profile}),
    )

    with pytest.raises(GovernanceError, match=message):
        pheromone_policy_validation.validate_pheromone_policy_rules(
            selected,
            finite_number=lambda value, _: float(value),
            non_negative_number=lambda value, _: float(value),
            non_negative_step=lambda value, _: int(value),
        )


def test_risk_resource_guards_reject_exact_type_and_limit_violations() -> None:
    with pytest.raises(ValueError, match="outside the authority integer bound"):
        risk_resources._require_count(True, "count")
    with pytest.raises(TypeError, match="exact JSON object"):
        risk_resources._require_exact_mapping([], frozenset(), "mapping")
    with pytest.raises(ValueError, match="canonical non-blank text"):
        risk_resources._require_bounded_text(1, "text")
    with pytest.raises(ValueError, match="exceeds the Risk v2 text bound"):
        risk_resources._require_bounded_text(
            "x" * (risk_resources.MAX_RISK_TEXT_BYTES_V2 + 1),
            "text",
        )


def test_risk_contract_private_guards_remain_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise dominated defensive guards as explicit regression alarms."""

    _, threshold, snapshot = _risk_values()
    non_genesis = object.__new__(RiskStateSnapshotV2)
    for field in RiskStateSnapshotV2.__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(non_genesis, field, getattr(snapshot, field))
    object.__setattr__(non_genesis, "revision", 2)
    object.__setattr__(non_genesis, "parent_revision", 1)
    object.__setattr__(non_genesis, "parent_epoch", None)
    with pytest.raises(ValueError, match="parent_epoch is invalid"):
        risk_contracts._validate_risk_snapshot_shape(non_genesis)

    monkeypatch.setattr(
        risk_contracts,
        "MAX_RISK_SNAPSHOT_BYTES_V2",
        len(snapshot.canonical_bytes()) - 1,
    )
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        replace(snapshot, snapshot_root="")

    forged = object.__new__(RiskStateSnapshotV2)
    for field in RiskStateSnapshotV2.__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(forged, field, getattr(snapshot, field))
    object.__setattr__(forged, "threshold", threshold)
    object.__setattr__(forged, "snapshot_root", "")
    assert forged.threshold is threshold


def test_risk_v2_request_contract_root_and_snapshot_type() -> None:
    context = risk_context(scope_ref="scope:risk-v2:request-contract")
    request, _ = risk_request(context, advance_ref="advance:request-contract")

    assert request.root() == request.request_root
    with pytest.raises(TypeError, match="requires exact snapshot v2"):
        replace(request, snapshot=cast(Any, object()), request_root="")


def test_risk_v2_opaque_source_and_state_contracts(
    risk_scenario: SimpleNamespace,
) -> None:
    source = risk_scenario.source
    state = risk_scenario.state

    with pytest.raises(TypeError, match="VerifiedRiskSourceV2 is final"):
        type("RiskSourceSubclass", (VerifiedRiskSourceV2,), {})
    with pytest.raises(AttributeError, match="immutable"):
        source.value = "forbidden"
    assert copy.copy(source) is source
    assert copy.deepcopy(source) is source
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        source.__getstate__()
    assert repr(source) == "<VerifiedRiskSourceV2 redacted>"

    with pytest.raises(TypeError, match="VerifiedRiskStateV2 is final"):
        type("RiskStateSubclass", (VerifiedRiskStateV2,), {})
    with pytest.raises(AttributeError, match="immutable"):
        state.value = "forbidden"
    assert copy.copy(state) is state
    assert copy.deepcopy(state) is state
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        state.__getstate__()
    assert repr(state) == "<VerifiedRiskStateV2 redacted>"
    assert state.transition_id == risk_scenario.request.transition_id
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(state)


def test_risk_v2_resource_totality_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="portable input contains a cycle"):
        risk_resources._preflight_portable_resources_v2(cyclic)

    assert risk_resources._require_bounded_text("", "optional", allow_empty=True) == ""
    with monkeypatch.context() as patch:
        patch.setattr(risk_resources, "_require_text", lambda _value, _label: "\ud800")
        with pytest.raises(ValueError, match="must be valid UTF-8"):
            risk_resources._require_bounded_text("placeholder", "risk text")

    with pytest.raises(ValueError, match="fields are invalid"):
        risk_resources._require_exact_mapping({"extra": 1}, frozenset(), "mapping")
    with pytest.raises(TypeError, match="object keys must be exact text"):
        risk_resources._require_exact_json_wire_v2({1: "value"}, "wire")
    with pytest.raises(TypeError, match="contains a non-JSON wire value"):
        risk_resources._require_exact_json_wire_v2((), "wire")
    with pytest.raises(ValueError, match="is unsupported"):
        risk_resources._require_exact_version("v1", "v2", "version")
    with pytest.raises(TypeError, match="must be an array"):
        risk_resources._canonical_texts("text", "texts", limit=2)
    with pytest.raises(ValueError, match="must not be empty"):
        risk_resources._canonical_texts((), "texts", limit=2)
    with pytest.raises(ValueError, match="contains a duplicate"):
        risk_resources._canonical_texts(("same", "same"), "texts", limit=2)
    with pytest.raises(TypeError, match="must be an array"):
        risk_resources._canonical_roots("sha256:" + "0" * 64, "roots", limit=2)


def test_risk_v2_source_handle_material_guards(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TypeError, match="source verification requires exact request"):
        risk_source.verify_risk_state_request_source_v2(
            cast(Any, object()),
            source=risk_scenario.source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(TypeError, match="risk source proof is invalid"):
        risk_source._verified_source(object())

    malformed = object.__new__(VerifiedRiskSourceV2)
    with pytest.raises(TypeError, match="risk source proof is incomplete"):
        risk_source._verified_source(malformed)

    object.__setattr__(malformed, "_request", object())
    object.__setattr__(malformed, "_binding", object())
    object.__setattr__(malformed, "_manifest", object())
    with pytest.raises(TypeError, match="risk source proof material is invalid"):
        risk_source._verified_source(malformed)

    object.__setattr__(malformed, "_request", risk_scenario.request)
    object.__setattr__(
        malformed,
        "_binding",
        object.__getattribute__(risk_scenario.source, "_binding"),
    )
    object.__setattr__(malformed, "_manifest", object())
    with monkeypatch.context() as patch:
        patch.setattr(risk_source, "_verified_source", lambda _value: None)
        with pytest.raises(TypeError, match="risk source proof manifest is invalid"):
            risk_source._verified_source_manifest_v2(malformed)


def test_risk_v2_source_temporal_and_parent_guards() -> None:
    context = risk_context(scope_ref="scope:risk-v2:source-guards")
    with pytest.raises(TypeError, match="band must use exact RiskBand"):
        risk_request(
            context,
            advance_ref="advance:invalid-band",
            risk_band=cast(Any, "LOW"),
        )
    with pytest.raises(ValueError, match="assessment is not fresh"):
        risk_request(
            context,
            advance_ref="advance:not-fresh",
            current_step=2,
            issued_at_step=3,
            expires_at_step=4,
        )

    parent_request, _ = risk_request(context, advance_ref="advance:parent")
    parent = parent_request.snapshot
    with pytest.raises(ValueError, match="current_step cannot move backwards"):
        risk_source._require_parent_progression(
            parent,
            current_step=parent.current_step - 1,
            issued_at_step=parent.assessment.issued_at_step + 1,
            expires_at_step=parent.assessment.expires_at_step,
            risk_band=parent.assessment.risk_band,
            epoch=parent.epoch,
        )
    with pytest.raises(ValueError, match="expiry must be after issuance"):
        risk_source._validated_parent(
            None,
            issued_at_step=2,
            expires_at_step=2,
            current_step=2,
            risk_band=parent.assessment.risk_band,
            epoch=parent.epoch,
        )
    with pytest.raises(TypeError, match="parent must be exact"):
        risk_source._validated_parent(
            object(),
            issued_at_step=3,
            expires_at_step=4,
            current_step=3,
            risk_band=parent.assessment.risk_band,
            epoch=parent.epoch,
        )
    with pytest.raises(ValueError, match="parent context is mismatched"):
        risk_source._validated_parent(
            parent,
            issued_at_step=3,
            expires_at_step=20,
            current_step=3,
            risk_band=parent.assessment.risk_band,
            epoch=parent.epoch,
            domain_root="sha256:" + "f" * 64,
            scope_ref=parent.scope_ref,
            manifest_root=parent.manifest_root,
            commit_policy_root=parent.commit_policy_root,
            risk_policy_root=parent.risk_policy_root,
            profile=parent.profile,
            assurance=parent.assurance,
            protocol_ref=parent.protocol_ref,
            run_ref=parent.run_ref,
            target_ref=parent.target_ref,
        )


def test_risk_v2_source_policy_and_binding_regression_alarms(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = risk_context(scope_ref="scope:risk-v2:source-policy-guards")

    with monkeypatch.context() as patch:

        class _DifferentRiskBandPolicy:
            pass

        patch.setattr(risk_source, "RiskBandPolicy", _DifferentRiskBandPolicy)
        with pytest.raises(TypeError, match="selected band is not a RiskBandPolicy"):
            risk_request(context, advance_ref="advance:bad-band-policy")

    no_policy = replace(risk_manifest(), collective_commit_policy=None)
    with pytest.raises(ValueError, match="has no collective commit policy"):
        risk_request(
            context,
            advance_ref="advance:no-policy",
            manifest=no_policy,
        )

    policy = risk_manifest().collective_commit_policy
    assert policy is not None
    invalid_assurance = replace(
        risk_manifest(),
        collective_commit_policy=replace(policy, assurance="unsupported"),
    )
    with pytest.raises(ValueError, match="manifest assurance is unsupported"):
        risk_request(
            context,
            advance_ref="advance:bad-assurance",
            manifest=invalid_assurance,
        )

    binding = object.__getattribute__(risk_scenario.source, "_binding")
    manifest = object.__getattribute__(risk_scenario.source, "_manifest")
    with monkeypatch.context() as patch:
        patch.setattr(risk_source, "_compute_root", lambda *_args, **_kwargs: "forged")
        with pytest.raises(ValueError, match="context construction is inconsistent"):
            risk_source._issue_source(risk_scenario.request, binding, manifest)

    with pytest.raises(ValueError, match="risk source parent is mismatched"):
        risk_source.verify_risk_state_request_source_v2(
            risk_scenario.request,
            source=risk_scenario.source,
            committed_parent_snapshot=risk_scenario.request.snapshot,
        )

    forged_source = object.__new__(VerifiedRiskSourceV2)
    object.__setattr__(forged_source, "_request", risk_scenario.request)
    object.__setattr__(
        forged_source,
        "_binding",
        replace(binding, source_context_root="sha256:" + "f" * 64),
    )
    object.__setattr__(forged_source, "_manifest", manifest)
    forged_binding = object.__getattribute__(forged_source, "_binding")
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_source,
            "_verified_source",
            lambda _value: (risk_scenario.request, forged_binding),
        )
        with pytest.raises(ValueError, match="risk source context is mismatched"):
            risk_source.verify_risk_state_request_source_v2(
                risk_scenario.request,
                source=forged_source,
                committed_parent_snapshot=None,
            )

    no_policy_source = object.__new__(VerifiedRiskSourceV2)
    object.__setattr__(no_policy_source, "_request", risk_scenario.request)
    object.__setattr__(no_policy_source, "_binding", binding)
    object.__setattr__(
        no_policy_source,
        "_manifest",
        replace(manifest, collective_commit_policy=None),
    )
    with pytest.raises(ValueError, match="manifest policy is unavailable"):
        risk_source._verified_source(no_policy_source)


def _risk_successor(suffix: str) -> SimpleNamespace:
    context = risk_context(scope_ref=f"scope:risk-v2:successor:{suffix}")
    parent, parent_source = risk_request(
        context,
        advance_ref=f"advance:parent:{suffix}",
    )
    parent_attempt, _ = risk_advance(context, parent, parent_source)
    assert parent_attempt.committed_transition is not None
    request, source = risk_request(
        context,
        advance_ref=f"advance:child:{suffix}",
        parent=parent.snapshot,
        current_step=3,
        issued_at_step=3,
        expires_at_step=20,
    )
    session = risk_operations.open_risk_authority_session_v2(
        context.capability,
        request,
    )
    return SimpleNamespace(
        context=context,
        parent=parent,
        request=request,
        source=source,
        session=session,
    )


def test_risk_v2_operation_dependency_failures_map_exact_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _risk_successor("dependency-failures")
    request = scenario.request
    session_state, failure = risk_operations._validated_session_or_failure(
        scenario.session,
        request,
    )
    assert session_state is not None
    assert failure is None

    with monkeypatch.context() as patch:
        patch.setattr(
            risk_operations,
            "_governance_authority_session_state_v2",
            lambda _candidate: (_ for _ in ()).throw(TypeError("controlled")),
        )
        _, invalid_session = risk_operations._validated_session_or_failure(
            object(),
            request,
        )
    assert invalid_session is not None
    assert invalid_session.failure is not None
    assert invalid_session.failure.path == "/authority_session"

    with monkeypatch.context() as patch:
        patch.setattr(
            risk_operations,
            "_risk_issuer_matches_session",
            lambda _request, _session: False,
        )
        _, issuer_failure = risk_operations._validated_session_or_failure(
            scenario.session,
            request,
        )
    assert issuer_failure is not None
    assert issuer_failure.failure is not None
    assert issuer_failure.failure.path == "/snapshot/assessment/issuer_ref"

    with monkeypatch.context() as patch:
        patch.setattr(risk_operations, "_reconcile", lambda *_args, **_kwargs: None)
        patch.setattr(
            risk_operations,
            "_risk_source_failure",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            risk_operations,
            "_current_session_grant_failure",
            lambda _session: (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/grant",
            ),
        )
        attempt = risk_operations.advance_risk_state_v2(
            request,
            source=scenario.source,
            authority_session=scenario.session,
        )
    assert attempt.failure is not None
    assert attempt.failure.path == "/grant"

    with monkeypatch.context() as patch:
        patch.setattr(risk_operations, "_reconcile", lambda *_args, **_kwargs: None)
        patch.setattr(
            risk_operations,
            "_risk_source_failure",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            risk_operations,
            "_current_session_grant_failure",
            lambda _session: None,
        )
        patch.setattr(
            risk_operations,
            "_current_session_lifecycle_failure",
            lambda _session: None,
        )
        patch.setattr(
            risk_operations,
            "_continuity_failure",
            lambda _request, _parent: (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot/revision",
            ),
        )
        attempt = risk_operations.advance_risk_state_v2(
            request,
            source=scenario.source,
            authority_session=scenario.session,
        )
    assert attempt.failure is not None
    assert attempt.failure.path == "/snapshot/revision"


def test_risk_v2_committed_parent_load_totalizes_store_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _risk_successor("parent-load")

    class _MissingStore:
        def load_commit_view_v2(self, *_args: object) -> object:
            raise KeyError("controlled missing parent")

    missing = risk_operations._load_committed_parent(
        cast(Any, _MissingStore()),
        scenario.context.domain,
        scenario.request,
    )
    assert hasattr(missing, "failure")
    assert cast(Any, missing).failure.path == "/snapshot/parent_transition_id"

    finality = SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=None,
        committed_transition=None,
        position_observation=None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_operations,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: finality,
        )
        result = risk_operations._load_committed_parent(
            cast(Any, SimpleNamespace(load_commit_view_v2=lambda *_args: finality)),
            scenario.context.domain,
            scenario.request,
        )
    assert cast(Any, result).failure.path == "/snapshot/parent_transition_id"

    invalid = SimpleNamespace(
        disposition=object(),
        failure=None,
        committed_transition=None,
        position_observation=None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_operations,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: invalid,
        )
        result = risk_operations._load_committed_parent(
            cast(Any, SimpleNamespace(load_commit_view_v2=lambda *_args: invalid)),
            scenario.context.domain,
            scenario.request,
        )
    assert cast(Any, result).failure.path == "/snapshot/parent_transition_id"

    committed = SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=object(),
        position_observation=object(),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_operations,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: committed,
        )
        patch.setattr(
            risk_operations,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("controlled")),
        )
        result = risk_operations._load_committed_parent(
            cast(Any, SimpleNamespace(load_commit_view_v2=lambda *_args: committed)),
            scenario.context.domain,
            scenario.request,
        )
    assert cast(Any, result).failure.path == "/snapshot/parent_transition_id"

    forged_snapshot = object.__new__(RiskStateSnapshotV2)
    for field in RiskStateSnapshotV2.__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(
            forged_snapshot,
            field,
            getattr(scenario.request.snapshot, field),
        )
    object.__setattr__(
        forged_snapshot,
        "parent_snapshot_root",
        "sha256:" + "f" * 64,
    )
    forged_request = object.__new__(type(scenario.request))
    for field in type(scenario.request).__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(forged_request, field, getattr(scenario.request, field))
    object.__setattr__(forged_request, "snapshot", forged_snapshot)
    result = risk_operations._load_committed_parent(
        scenario.context.store,
        scenario.context.domain,
        forged_request,
    )
    assert cast(Any, result).failure.path == "/snapshot/parent_snapshot_root"


def test_risk_v2_continuity_and_stored_record_guards(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = risk_scenario.request
    snapshot = request.snapshot
    forged_assessment = _forged_dataclass(
        snapshot.assessment,
        previous_assessment_root="sha256:" + "f" * 64,
    )
    forged_snapshot = _forged_dataclass(snapshot, assessment=forged_assessment)
    forged_request = _forged_dataclass(request, snapshot=forged_snapshot)
    assert risk_state_support._continuity_failure(forged_request, None) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/snapshot",
    )

    successor = _risk_successor("continuity-records")
    parent = successor.parent.snapshot
    child = successor.request.snapshot
    cross_bound = _forged_dataclass(child, run_ref="run:cross-bound")
    assert risk_state_support._continuity_failure(
        _forged_dataclass(successor.request, snapshot=cross_bound),
        parent,
    ) == (AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot")
    backwards = _forged_dataclass(child, epoch=parent.epoch - 1)
    assert risk_state_support._continuity_failure(
        _forged_dataclass(successor.request, snapshot=backwards),
        parent,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/snapshot/epoch",
    )
    bad_revision = _forged_dataclass(child, revision=parent.revision + 2)
    assert risk_state_support._continuity_failure(
        _forged_dataclass(successor.request, snapshot=bad_revision),
        parent,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/snapshot/assessment",
    )

    session_state, failure = risk_operations._validated_session_or_failure(
        risk_scenario.session,
        request,
    )
    assert session_state is not None
    assert failure is None
    binding = risk_state_support._session_binding(session_state)
    records = risk_state_support._state_records(request, binding)

    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_portable_projection",
            lambda _value: [],
        )
        with pytest.raises(TypeError, match="committed state must be an exact object"):
            risk_state_support._decode_state_records(
                records, risk_scenario.context.domain
            )

    with pytest.raises(ValueError, match="committed state fields are invalid"):
        risk_state_support._decode_state_records({}, risk_scenario.context.domain)

    wrong_domain = dict(records)
    wrong_domain["domain_root"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="committed state domain is mismatched"):
        risk_state_support._decode_state_records(
            wrong_domain,
            risk_scenario.context.domain,
        )

    wrong_payload = dict(records)
    wrong_payload["transition_id"] = "transition:forged"
    with pytest.raises(ValueError, match="committed state payload is mismatched"):
        risk_state_support._decode_state_records(
            wrong_payload,
            risk_scenario.context.domain,
        )

    with pytest.raises(ValueError, match="session binding fields are invalid"):
        risk_state_support._validate_stored_session_binding({}, request)
    wrong_binding = dict(binding)
    wrong_binding["request_root"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="stored session binding is mismatched"):
        risk_state_support._validate_stored_session_binding(wrong_binding, request)
    bad_grant = dict(binding)
    bad_grant["grant_ref"] = ""
    with pytest.raises(ValueError, match="stored grant binding is invalid"):
        risk_state_support._validate_stored_session_binding(bad_grant, request)


def _risk_shallow_view(
    request: Any,
    *,
    transition: object = object(),
    receipt_revision: int | None = None,
    events: tuple[object, ...] = (),
    entries: tuple[object, ...] = (),
) -> SimpleNamespace:
    receipt = SimpleNamespace(
        revision=request.snapshot.revision
        if receipt_revision is None
        else receipt_revision,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        parent_root="sha256:" + "0" * 64,
    )
    read_set = SimpleNamespace(
        entries=entries,
        root=lambda: "sha256:" + "1" * 64,
    )
    batch = SimpleNamespace(
        transition=transition,
        read_set=read_set,
        trace_batch=SimpleNamespace(events=events),
    )
    return SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.COMMITTED,
        committed_transition=SimpleNamespace(receipt=receipt, batch=batch),
        position_observation=object(),
        failure=None,
    )


def test_risk_v2_committed_view_lineage_guards(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = risk_scenario.request
    domain = risk_scenario.context.domain
    session_state, failure = risk_operations._validated_session_or_failure(
        risk_scenario.session,
        request,
    )
    assert session_state is not None
    assert failure is None
    binding = risk_state_support._session_binding(session_state)

    invalid = SimpleNamespace(
        disposition=object(),
        committed_transition=None,
        position_observation=None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: invalid,
        )
        with pytest.raises(Exception) as exc_info:
            risk_state_support._decode_committed_view(
                cast(Any, invalid),
                domain,
                reader=None,
            )
    assert getattr(exc_info.value, "path") == "/transition_id"

    no_transition = _risk_shallow_view(request, transition=None)
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: no_transition,
        )
        with pytest.raises(ValueError, match="batch has no transition"):
            risk_state_support._decode_committed_view(
                cast(Any, no_transition),
                domain,
                reader=None,
            )

    receipt_mismatch = _risk_shallow_view(
        request,
        transition=SimpleNamespace(state_records={}),
        receipt_revision=99,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: receipt_mismatch,
        )
        patch.setattr(
            risk_state_support,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, binding),
        )
        with pytest.raises(ValueError, match="committed receipt is mismatched"):
            risk_state_support._decode_committed_view(
                cast(Any, receipt_mismatch),
                domain,
                reader=None,
            )

    trace_mismatch = _risk_shallow_view(
        request,
        transition=SimpleNamespace(state_records={}),
        events=("observed",),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: trace_mismatch,
        )
        patch.setattr(
            risk_state_support,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, binding),
        )
        patch.setattr(
            risk_state_support,
            "_validate_committed_read_set",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            risk_state_support,
            "_risk_events",
            lambda *_args, **_kwargs: ("expected",),
        )
        with pytest.raises(ValueError, match="trace lineage is mismatched"):
            risk_state_support._decode_committed_view(
                cast(Any, trace_mismatch),
                domain,
                reader=None,
            )

    continuity = _risk_shallow_view(
        request,
        transition=SimpleNamespace(state_records={}),
        events=("expected",),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: continuity,
        )
        patch.setattr(
            risk_state_support,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, binding),
        )
        patch.setattr(
            risk_state_support,
            "_validate_committed_read_set",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            risk_state_support,
            "_risk_events",
            lambda *_args, **_kwargs: ("expected",),
        )
        patch.setattr(
            risk_state_support,
            "_load_parent_from_reader",
            lambda *_args, **_kwargs: object(),
        )
        patch.setattr(
            risk_state_support,
            "_continuity_failure",
            lambda *_args, **_kwargs: (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot",
            ),
        )
        with pytest.raises(ValueError, match="historical continuity is invalid"):
            risk_state_support._decode_committed_view(
                cast(Any, continuity),
                domain,
                reader=cast(Any, object()),
            )

    duplicate_entry = SimpleNamespace(
        stream_ref=request.stream_ref,
        expected_revision=0,
        expected_root="sha256:" + "0" * 64,
    )
    duplicates = _risk_shallow_view(
        request,
        entries=(duplicate_entry, duplicate_entry),
    )
    with pytest.raises(ValueError, match="read set contains duplicate streams"):
        risk_state_support._validate_committed_read_set(
            cast(Any, duplicates),
            request,
            binding,
        )
    empty = _risk_shallow_view(request)
    with pytest.raises(ValueError, match="authority read set is mismatched"):
        risk_state_support._validate_committed_read_set(
            cast(Any, empty),
            request,
            binding,
        )


def test_risk_v2_verified_view_and_historical_parent_fail_closed(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = risk_scenario.request
    domain = risk_scenario.context.domain
    session_state, failure = risk_operations._validated_session_or_failure(
        risk_scenario.session,
        request,
    )
    assert session_state is not None
    assert failure is None
    assert not risk_state_support._committed_view_matches_request(
        cast(Any, object()),
        request,
        session_state,
    )

    view = SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
    )
    reader = cast(
        Any, SimpleNamespace(load_commit_view_v2=lambda *_args, **_kwargs: view)
    )
    binding_error = risk_operations.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: view,
        )
        patch.setattr(
            risk_state_support,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(binding_error),
        )
        with pytest.raises(type(binding_error)) as exc_info:
            risk_state_support._load_verified_request_view(
                reader,
                domain,
                request,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/transition_id"

    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: view,
        )
        patch.setattr(
            risk_state_support,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("controlled")),
        )
        with pytest.raises(type(binding_error)) as exc_info:
            risk_state_support._load_verified_request_view(
                reader,
                domain,
                request,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/transition_id"

    other_request = _forged_dataclass(request, advance_ref="advance:other")
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: view,
        )
        patch.setattr(
            risk_state_support,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (other_request, {}),
        )
        with pytest.raises(type(binding_error)) as exc_info:
            risk_state_support._load_verified_request_view(
                reader,
                domain,
                request,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/request_root"

    successor = _risk_successor("historical-parent")

    class _MissingReader:
        def load_commit_view_v2(self, *_args: object, **_kwargs: object) -> object:
            raise KeyError("controlled missing history")

    with pytest.raises(ValueError, match="historical parent is unavailable"):
        risk_state_support._load_parent_from_reader(
            cast(Any, _MissingReader()),
            successor.context.domain,
            successor.request,
        )

    finality = SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: finality,
        )
        with pytest.raises(type(binding_error)) as exc_info:
            risk_state_support._load_parent_from_reader(
                cast(
                    Any,
                    SimpleNamespace(
                        load_commit_view_v2=lambda *_args, **_kwargs: finality
                    ),
                ),
                successor.context.domain,
                successor.request,
            )
    assert exc_info.value.path == "/snapshot/parent_transition_id"

    forged_parent_snapshot = _forged_dataclass(
        successor.parent.snapshot,
        snapshot_root="sha256:" + "f" * 64,
    )
    forged_parent = _forged_dataclass(
        successor.parent,
        snapshot=forged_parent_snapshot,
    )
    committed = SimpleNamespace(
        disposition=risk_operations.GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            risk_state_support,
            "_canonical_commit_view_v2",
            lambda *_args, **_kwargs: committed,
        )
        patch.setattr(
            risk_state_support,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (forged_parent, {}),
        )
        with pytest.raises(ValueError, match="historical parent binding is mismatched"):
            risk_state_support._load_parent_from_reader(
                cast(
                    Any,
                    SimpleNamespace(
                        load_commit_view_v2=lambda *_args, **_kwargs: committed
                    ),
                ),
                successor.context.domain,
                successor.request,
            )


def test_legacy_risk_chain_temporal_head_and_record_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = legacy_risk_policy()
    with pytest.raises(GovernanceError, match="expiry must be after initialization"):
        legacy_initialize_risk_chain(
            policy,
            initialized_at_step=2,
            expires_at_step=2,
        )

    assessment, state = legacy_issue_risk_assessment(
        policy,
        LegacyRiskBand.LOW,
    )
    invalid_reset = _forged_dataclass(
        assessment,
        previous_assessment_fingerprint="",
        window_reset_required=True,
    )
    with pytest.raises(GovernanceError, match="cannot require a risk reset"):
        legacy_risk_records._validate_risk_assessment_shape(invalid_reset)

    threshold = legacy_risk_threshold(assessment, state, policy)
    with pytest.raises(GovernanceError, match="chain revision must be positive"):
        legacy_risk_records._validate_threshold_identity(
            _forged_dataclass(threshold, risk_chain_revision=0)
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_risk_chain,
            "_risk_assessment_is_head_of_state",
            lambda *_args, **_kwargs: False,
        )
        with pytest.raises(GovernanceError, match="not the chain head"):
            legacy_issue_risk_assessment(
                policy,
                LegacyRiskBand.LOW,
                previous=assessment,
                chain_state=state,
                issued_at_step=3,
                assessment_id="risk:not-head",
            )

    invalid_expiry = _forged_dataclass(
        state,
        expires_at_step=state.initialized_at_step,
    )
    with pytest.raises(GovernanceError, match="expiry must be after initialization"):
        legacy_risk_records._validate_risk_assessment_chain_state_shape(invalid_expiry)

    invalid_empty = _forged_dataclass(
        state,
        revision=0,
        latest_assessment_fingerprint="",
        latest_risk_band="",
        previous_state_fingerprint="",
        last_issued_at_step=state.initialized_at_step + 1,
    )
    with pytest.raises(
        GovernanceError,
        match="empty risk assessment chain issuance step is invalid",
    ):
        legacy_risk_records._validate_risk_assessment_chain_state_shape(invalid_empty)


def test_schema_remaining_semantic_guard_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(
            hybrid_schema,
            "commit_payload_fingerprint",
            lambda *_args, **_kwargs: "composition",
        )
        errors = hybrid_schema._validate_hybrid_commit_step_semantics(
            {
                "attention": {},
                "binding_profile": {},
                "composition_root": "composition",
                "commit": {
                    "profile": "profile",
                    "assurance": "advisory",
                    "commit_truth_root": "root",
                    "commit_assessment_fingerprint": "root",
                    "assessment_status": "invalid",
                    "unique_leader": False,
                    "leader_ready_for_stability": False,
                    "leader_candidate_id": "candidate:forged",
                },
            },
            "profile",
        )
    assert errors == [
        "$.payload.commit.assurance: profile/assurance mismatch",
        "$.payload.commit.leader_candidate_id: non-unique step names leader",
    ]

    with monkeypatch.context() as patch:
        patch.setattr(
            hybrid_schema,
            "_validate_evaluation_diagnostics",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            hybrid_schema,
            "_validate_evaluation_roots",
            lambda *_args, **_kwargs: None,
        )
        errors = hybrid_schema._validate_hybrid_commit_evaluation_semantics(
            {
                "authoritative": False,
                "status": "progress",
                "terminal": False,
                "progress_ref": "",
                "outcome_ref": "",
            }
        )
    assert errors == [
        "$.payload: non-authoritative evaluation must be terminal invalid"
    ]

    membership = {
        "profile": "wrong",
        "assurance": "evidence_bound",
        "manifest_root": "manifest",
        "commit_policy_root": "policy",
        "protocol_id": "protocol",
        "run_id": "run",
        "target": "target",
        "epoch": 2,
        "snapshot_fingerprint": "snapshot",
        "membership_root": "membership",
    }
    payload = {
        "new_membership_snapshot": membership,
        "new_epoch": 2,
        "previous_epoch": 1,
        "declared_recovery_ref": "",
        "recovery_stop_root": "",
        "recovery_permission_root": "",
        "recovery_required": False,
        "profile": "profile",
        "assurance": "evidence_bound",
        "manifest_root": "manifest",
        "commit_policy_root": "policy",
        "protocol_id": "protocol",
        "run_id": "run",
        "target": "target",
        "new_membership_snapshot_root": "snapshot",
        "new_membership_root": "membership",
        "issuer_attestation_refs": (),
        "certificate_body_root": "root",
        "certificate_root": "root",
    }
    with monkeypatch.context() as patch:
        patch.setattr(
            distributed_schema,
            "_validate_portable_membership_semantics",
            lambda *_args, **_kwargs: [],
        )
        patch.setattr(
            distributed_schema,
            "commit_payload_fingerprint",
            lambda *_args, **_kwargs: "root",
        )
        errors = distributed_schema._validate_epoch_transition_semantics(
            payload,
            "profile",
        )
    assert (
        "$.payload.new_membership_snapshot.profile: transition binding mismatch"
        in errors
    )


def test_legacy_support_membership_totality_guards(
    legacy_support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = legacy_support_scenario
    verification = scenario.verification
    normalized = {
        name: getattr(verification, name)
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        )
    }

    with pytest.raises(GovernanceError, match="canonical principal verifications"):
        legacy_support_membership._eligible_principal_clusters(
            (cast(Any, object()),),
            normalized=cast(Any, normalized),
            issued=2,
            expires=20,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_membership,
            "principal_verification_matches",
            lambda *_args, **_kwargs: False,
        )
        with pytest.raises(GovernanceError, match="stale or has a binding mismatch"):
            legacy_support_membership._eligible_principal_clusters(
                (verification,),
                normalized=cast(Any, normalized),
                issued=2,
                expires=20,
            )

    second = legacy_support_principal(
        "principal:totality:second",
        "cluster:totality:second",
        index=92,
        policy=scenario.policy,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_membership,
            "principal_verification_matches",
            lambda *_args, **_kwargs: True,
        )
        patch.setattr(
            legacy_support_membership,
            "principal_verification_fingerprint",
            lambda _verification: "sha256:" + "9" * 64,
        )
        with pytest.raises(GovernanceError, match="repeats a verification"):
            legacy_support_membership._eligible_principal_clusters(
                (verification, second),
                normalized=cast(Any, normalized),
                issued=2,
                expires=20,
            )

    cursor = scenario.membership._epoch_cursor
    with monkeypatch.context() as patch:
        patch.setattr(cursor, "state", object())
        with pytest.raises(
            GovernanceError,
            match="current state is unavailable",
        ):
            legacy_support_membership_snapshot(
                (verification,),
                policy=scenario.policy,
            )


def test_legacy_support_evaluation_scope_totality_guards(
    legacy_support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = legacy_support_scenario
    state_root = legacy_support_evaluation.eligible_membership_epoch_state_fingerprint(
        scenario.membership_state
    )

    forged = _forged_dataclass(scenario.lease)
    with pytest.raises(GovernanceError, match="forged lease"):
        legacy_support_evaluation._validate_support_lease_scope(
            forged,
            membership_snapshot=scenario.membership,
            membership_state_fingerprint=state_root,
            replay_state=scenario.replay,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_evaluation,
            "support_lease_is_authoritative",
            lambda _lease: True,
        )
        with pytest.raises(GovernanceError, match="binding mismatch"):
            legacy_support_evaluation._validate_support_lease_scope(
                _forged_dataclass(scenario.lease, profile="profile:other"),
                membership_snapshot=scenario.membership,
                membership_state_fingerprint=state_root,
                replay_state=scenario.replay,
            )

        patch.setattr(
            legacy_support_evaluation,
            "_same_commit_scope",
            lambda *_args, **_kwargs: True,
        )
        with pytest.raises(GovernanceError, match="membership root mismatch"):
            legacy_support_evaluation._validate_support_lease_scope(
                _forged_dataclass(
                    scenario.lease,
                    membership_root="sha256:" + "f" * 64,
                ),
                membership_snapshot=scenario.membership,
                membership_state_fingerprint=state_root,
                replay_state=scenario.replay,
            )
        with pytest.raises(GovernanceError, match="epoch state mismatch"):
            legacy_support_evaluation._validate_support_lease_scope(
                scenario.lease,
                membership_snapshot=scenario.membership,
                membership_state_fingerprint="sha256:" + "e" * 64,
                replay_state=scenario.replay,
            )
        with pytest.raises(GovernanceError, match="replay authority mismatch"):
            legacy_support_evaluation._validate_support_lease_scope(
                scenario.lease,
                membership_snapshot=scenario.membership,
                membership_state_fingerprint=state_root,
                replay_state=_forged_dataclass(
                    scenario.replay,
                    authority_key="authority:other",
                ),
            )


def test_legacy_support_replay_cursor_and_collision_totality(
    legacy_support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = legacy_support_scenario
    receipt = scenario.replay.receipts[0]
    invalid_replay = _forged_dataclass(scenario.replay)
    object.__setattr__(invalid_replay, "_cursor", object())
    arguments = {
        "replay_collision": receipt,
        "replay_state": invalid_replay,
        "proposal": scenario.proposal,
        "principal_verification": scenario.verification,
        "membership_snapshot": scenario.membership,
        "membership_epoch_state": scenario.membership_state,
        "normalized_observations": scenario.lease.positive_observation_fingerprints,
        "normalized_prior_lease_fingerprint": "",
        "lease_id": scenario.lease.lease_id,
        "normalized_issuer": scenario.lease.issuer_id,
        "authority": scenario.lease.authority,
        "current_step": 4,
        "issuance_provenance": scenario.lease.issuance_provenance,
        "issuance_trace_event_id": scenario.lease.issuance_trace_event_id,
    }
    with pytest.raises(GovernanceError, match="replay cursor is invalid"):
        legacy_support_lease._support_lease_key_replay_result(**arguments)

    arguments["replay_state"] = scenario.replay
    arguments["lease_id"] = "lease:mismatched"
    with pytest.raises(GovernanceError, match="replay is a safety violation"):
        legacy_support_lease._support_lease_key_replay_result(**arguments)

    cursor = scenario.replay._cursor
    with monkeypatch.context() as patch:
        patch.setitem(
            cursor.transitions,
            "parent:unavailable",
            ("request:stable", object(), object()),
        )
        with pytest.raises(GovernanceError, match="result is no longer available"):
            legacy_support_lease._support_lease_stale_transition_result(
                cursor,
                parent_state_fingerprint="parent:unavailable",
                request_fingerprint="request:stable",
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_lease,
            "_support_lease_stale_transition_result",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            legacy_support_lease,
            "_support_lease_receipt_collision_result",
            lambda *_args, **_kwargs: (scenario.lease, scenario.replay),
        )
        assert legacy_support_lease._record_support_lease(
            scenario.lease,
            replay_state=scenario.replay,
            prior_leases=(),
            current_step=4,
        ) == (scenario.lease, scenario.replay)

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_lease,
            "_support_replay_collision_receipt",
            lambda *_args, **_kwargs: _forged_dataclass(
                receipt,
                lease_fingerprint="sha256:" + "f" * 64,
            ),
        )
        with pytest.raises(GovernanceError, match="conflicts with local authority"):
            legacy_support_lease._support_lease_receipt_collision_result(
                cursor,
                lease=scenario.lease,
                replay_state=scenario.replay,
                current_step=4,
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_lease,
            "_support_replay_collision_receipt",
            lambda *_args, **_kwargs: receipt,
        )
        assert legacy_support_lease._support_lease_receipt_collision_result(
            cursor,
            lease=scenario.lease,
            replay_state=scenario.replay,
            current_step=4,
        ) == (scenario.lease, scenario.replay)


def test_legacy_support_principal_and_switch_branch_totality(
    legacy_support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = legacy_support_scenario
    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_lease,
            "eligible_principal_snapshot_matches",
            lambda *_args, **_kwargs: True,
        )
        patch.setattr(
            legacy_support_lease,
            "principal_verification_matches",
            lambda *_args, **_kwargs: False,
        )
        with pytest.raises(
            GovernanceError,
            match="principal verification is forged",
        ):
            legacy_support_lease._validate_support_lease_principal(
                scenario.proposal,
                principal_verification=scenario.verification,
                membership_snapshot=scenario.membership,
                membership_epoch_state=scenario.membership_state,
                current_step=4,
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            legacy_support_lease,
            "support_lease_is_authoritative",
            lambda _lease: True,
        )
        patch.setattr(
            legacy_support_lease,
            "support_lease_revocation_matches",
            lambda *_args, **_kwargs: False,
        )
        with pytest.raises(GovernanceError, match="revocation is forged"):
            legacy_support_lease._validate_support_lease_switch(
                scenario.proposal,
                principal_verification=scenario.verification,
                prior_lease=scenario.lease,
                prior_revocation=cast(Any, object()),
                current_step=4,
            )

        patch.setattr(
            legacy_support_lease,
            "support_lease_revocation_matches",
            lambda *_args, **_kwargs: True,
        )
        with pytest.raises(GovernanceError, match="at the same step"):
            legacy_support_lease._validate_support_lease_switch(
                scenario.proposal,
                principal_verification=scenario.verification,
                prior_lease=scenario.lease,
                prior_revocation=cast(
                    Any,
                    SimpleNamespace(revoked_at_step=5),
                ),
                current_step=4,
            )


def test_risk_v2_state_handle_and_reader_guards(
    risk_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(Exception) as exc_info:
        risk_operations._verified_state_view(object())
    assert getattr(exc_info.value, "path") == ""

    malformed = object.__new__(VerifiedRiskStateV2)
    with pytest.raises(Exception) as exc_info:
        risk_operations._verified_state_view(malformed)
    assert getattr(exc_info.value, "path") == ""

    malformed_bound = object.__new__(VerifiedRiskStateV2)
    object.__setattr__(malformed_bound, "_reader", risk_scenario.context.store)
    object.__setattr__(malformed_bound, "_domain", risk_scenario.context.domain)
    object.__setattr__(malformed_bound, "_request", object())
    object.__setattr__(malformed_bound, "_receipt_root", "receipt")
    with pytest.raises(Exception) as exc_info:
        risk_operations._verified_state_view(malformed_bound)
    assert getattr(exc_info.value, "path") == "/request_root"

    for function, value, message in (
        (
            risk_operations._require_request,
            object(),
            "risk operation requires exact advance request",
        ),
        (
            risk_operations._require_domain,
            object(),
            "risk rehydration requires exact AuthorityDomainV2",
        ),
    ):
        with pytest.raises(TypeError, match=message):
            function(value)

    with pytest.raises(TypeError, match="risk rehydration requires StateReader v2"):
        risk_operations._require_state_reader(object())

    monkeypatch.setattr(
        risk_operations,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )
    with pytest.raises(TypeError, match="risk rehydration requires StateReader v2"):
        risk_operations._require_state_reader(object())

    with pytest.raises(ValueError, match="risk parent has no committed transition"):
        risk_operations._head_from_view(
            cast(Any, SimpleNamespace(committed_transition=None)),
            risk_scenario.context.domain,
        )


def test_schema_metadata_recursion_rejects_each_nonportable_leaf() -> None:
    bounded_errors: list[str] = []
    schema_common._validate_non_authoritative_integer(
        0,
        path="$.bounded",
        errors=bounded_errors,
    )
    assert bounded_errors == []

    errors = schema_common._validate_noncritical_envelope_extensions(
        {
            "schema": "ignored",
            "x-list": [
                MAX_AUTHORITY_INTEGER + 1,
                math.inf,
                "e\u0301",
                {"": "invalid-key"},
            ],
            "x-object": {1: "invalid"},
        }
    )

    assert errors == [
        "$.x-list[0]: integer exceeds portable Commit bound",
        "$.x-list[1]: non-authoritative metadata must be finite JSON",
        "$.x-list[2]: metadata string must use NFC normalization",
        "$.x-list[3]: metadata object keys must be canonical strings",
        "$.x-object: metadata object keys must be canonical strings",
    ]


def test_schema_contract_constructor_and_adapter_fail_closed() -> None:
    with pytest.raises(TypeError, match="profiles must be non-empty text"):
        schema_common.CommitWireContract(
            schema_name="schema",
            payload_schema=lambda: {},
            validator=lambda _payload, _profile: [],
            profiles=("",),
        )

    def validate(payload: object) -> list[str]:
        return [] if payload == {"ok": True} else ["invalid"]

    adapted = schema_common.profile_agnostic(validate)
    assert adapted({"ok": True}, "ignored") == []
    assert adapted.__name__ == "validate"


def test_foundation_schema_semantic_boundaries_are_explicit() -> None:
    assert foundation_schema._validate_action_certificate_semantics(
        {"action": "publish", "certificate_ref": ""}
    ) == ["$.payload.certificate_ref: publish/execute requires certificate binding"]
    progress = {
        "terminal": True,
        "next_required_inputs": (),
        "unmet_gates": (),
        "sealed_window": False,
        "seal_ref": "",
        "sealed_at_step": 0,
        "previous_progress_ref": "",
        "heartbeat_sequence": 0,
        "heartbeat_continuous": False,
        "current_step": 0,
    }
    assert foundation_schema._validate_progress_semantics(progress) == [
        "$.payload.terminal: progress must be non-terminal",
        "$.payload: progress must identify an input or unmet gate",
        "$.payload.heartbeat_continuous: progress must be continuous",
    ]

    errors: list[str] = []
    foundation_schema._validate_evidence_commit_outcome(
        {
            "assurance": "advisory",
            "authority_scope": "wrong",
            "authoritative_commit": False,
            "epistemically_committed": False,
            "candidate_id": "",
            "assessment_ref": "",
            "certificate_ref": "",
            "sealed_window": False,
            "heartbeat_continuous": False,
        },
        errors=errors,
    )
    assert errors == [
        "$.payload.assurance: advisory cannot evidence-commit",
        "$.payload.authority_scope: assurance scope mismatch",
        "$.payload: evidence commit lacks commit authority",
        "$.payload: evidence commit lacks candidate or assessment",
        "$.payload.certificate_ref: evidence commit requires proof",
        "$.payload: evidence commit requires continuous seal authority",
    ]
    errors = []
    foundation_schema._validate_noncommit_outcome(
        {
            "authoritative_commit": True,
            "epistemically_committed": True,
            "execution_eligible": True,
        },
        errors=errors,
    )
    foundation_schema._validate_outcome_authority_scope(
        kind="blocked",
        authority_scope="none",
        errors=errors,
    )
    foundation_schema._validate_outcome_authority_scope(
        kind="safe_fallback",
        authority_scope="denial",
        errors=errors,
    )
    assert errors == [
        "$.payload: non-commit outcome claims commit authority",
        "$.payload.execution_eligible: non-commit cannot execute",
        "$.payload.authority_scope: blocked outcome requires denial",
        "$.payload.authority_scope: non-commit outcome requires none",
    ]


def test_commit_and_hybrid_schema_semantic_guards_are_diagnostic() -> None:
    assert commit_schema._validate_commit_finality_verification_semantics(
        {"assurance": "certified", "certificate_kind": "local_commit_receipt"}
    ) == ["$.payload.certificate_kind: kind does not match assurance"]

    progress = {
        "status": "progress",
        "terminal": True,
        "progress_ref": "",
        "outcome_ref": "outcome",
        "deliver_authorization_ref": "delivery",
    }
    errors: list[str] = []
    hybrid_schema._validate_authoritative_evaluation_status(progress, errors=errors)
    assert errors == [
        "$.payload: authoritative progress is inconsistent",
        "$.payload.deliver_authorization_ref: progress cannot deliver",
    ]
    errors = []
    hybrid_schema._validate_authoritative_evaluation_status(
        {
            "status": "terminal",
            "terminal": False,
            "progress_ref": "progress",
            "outcome_ref": "",
            "deliver_authorization_ref": "",
        },
        errors=errors,
    )
    assert errors == ["$.payload: authoritative terminal outcome is inconsistent"]
    errors = []
    hybrid_schema._validate_authoritative_evaluation_status(
        {
            "status": "terminal",
            "terminal": True,
            "progress_ref": "",
            "outcome_ref": "outcome",
            "deliver_authorization_ref": "",
        },
        errors=errors,
    )
    assert errors == [
        "$.payload.deliver_authorization_ref: terminal evaluation must deliver"
    ]


@pytest.mark.parametrize(
    ("trail", "updates", "message"),
    [
        (
            cast(Any, object()),
            {},
            "legacy pheromone trail must be a PheromoneTrail",
        ),
        (
            PheromoneTrail(
                "",
                1.0,
                subject_type="candidate",
                subject_id="candidate:b",
            ),
            {},
            "candidate pheromone subject must match candidate_id",
        ),
        (
            PheromoneTrail("candidate:a", 1.0),
            {"source_role": " "},
            "source_role must be non-blank",
        ),
        (
            PheromoneTrail("candidate:a", 1.0, source_role="role:a"),
            {"source_role": "role:b"},
            "source_role conflicts",
        ),
        (
            PheromoneTrail(
                "candidate:a",
                1.0,
                subject_type="candidate",
                subject_id=" ",
            ),
            {},
            "subject_id must be non-blank",
        ),
        (
            PheromoneTrail(
                "candidate:a",
                1.0,
                subject_type="candidate",
                subject_id="candidate:b",
                route_id="route:a",
            ),
            {},
            "subject binding is inconsistent",
        ),
    ],
)
def test_legacy_pheromone_normalization_closes_every_binding_guard(
    trail: PheromoneTrail,
    updates: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        legacy_pheromone.normalize_legacy_pheromone_trail_impl(
            trail,
            target="target:a",
            source_id="source:a",
            provenance="urn:test",
            trace_event_id="trace:a",
            **updates,
        )


def test_pheromone_budget_and_lifecycle_temporal_guards() -> None:
    selected = pheromone_policy()
    with pytest.raises(GovernanceError, match="caps do not match active policy"):
        validate_pheromone_budget_state(
            PheromoneBudgetState(
                round_cap=selected.per_round_deposit_cap,
                per_source_cap=selected.per_source_cap + 1.0,
            ),
            selected,
        )
    with pytest.raises(
        GovernanceError,
        match="round and source usage do not reconstruct",
    ):
        validate_pheromone_budget_state(
            PheromoneBudgetState(
                round_cap=selected.per_round_deposit_cap,
                per_source_cap=selected.per_source_cap,
                round_used=2.0,
                source_used={"source:a": 1.0},
            ),
            selected,
        )

    future = PheromoneTrail(
        candidate_id="candidate:a",
        strength=1.0,
        subject_type="candidate",
        subject_id="candidate:a",
        target="target:a",
        source_id="source:a",
        provenance="urn:test",
        trace_event_id="trace:future",
        updated_at_step=2,
    )
    with pytest.raises(
        GovernanceError, match="must not precede pheromone updated step"
    ):
        evaporate_trails_with_records([future], selected, current_step=1)

    duplicate = replace(future, updated_at_step=2)
    with pytest.raises(GovernanceError, match="duplicate pheromone evaporation"):
        _reject_duplicate_trail_events(
            [future, duplicate],
            lifecycle="evaporation",
        )

    with pytest.raises(
        GovernanceError, match="must not precede pheromone updated step"
    ):
        is_expired(future, 1)
    assert not is_expired(future, 2)


def test_pheromone_scoring_and_diffusion_defensive_arithmetic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = pheromone_policy()
    future = pheromone_trail(updated_at_step=2)
    with pytest.raises(
        GovernanceError, match="must not precede pheromone updated step"
    ):
        pheromone_scoring.collect_pheromone_source_diversity(
            candidate_set=pheromone_candidates(),
            trails=[future],
            policy=selected,
            current_step=1,
        )

    with pytest.raises(
        GovernanceError,
        match="dimension breakdown must remain finite",
    ):
        pheromone_scoring.add_dimension_breakdown(
            {"candidate:a": {"dimension": 1e308}},
            "candidate:a",
            "dimension",
            1e308,
        )

    topology = PheromoneNeighborhood(
        subjects=(
            PheromoneSubject(
                "candidate",
                "candidate:alpha",
                "candidate:alpha",
                "decision:active",
            ),
            PheromoneSubject(
                "route",
                "route:a",
                "candidate:alpha",
                "decision:active",
            ),
        ),
    )
    untargeted = pheromone_trail(target="")
    result = diffuse_pheromone_trails_with_records(
        [untargeted],
        topology,
        selected,
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=pheromone_candidates(),
    )
    assert result.trails

    explosive_edge = SimpleNamespace(
        target_subject_type="route",
        target_subject_id="route:a",
        attenuation=math.inf,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            pheromone_diffusion,
            "outgoing_edges",
            lambda _topology: {("candidate", "candidate:alpha"): [explosive_edge]},
        )
        with pytest.raises(
            GovernanceError,
            match="diffused pheromone strength must remain finite",
        ):
            diffuse_pheromone_trails_with_records(
                [pheromone_trail()],
                topology,
                selected,
                PheromoneDiffusionPolicy(
                    enabled=True,
                    max_hops=1,
                    attenuation=0.5,
                ),
                candidate_set=pheromone_candidates(),
            )


@pytest.mark.parametrize(
    ("divergent_call", "message"),
    [
        (2, "kind breakdown does not reconstruct"),
        (3, "subject breakdown does not reconstruct"),
    ],
)
def test_pheromone_scoring_reconstruction_guards(
    divergent_call: int,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fsum = math.fsum
    calls = 0

    def divergent_fsum(values: object) -> float:
        nonlocal calls
        calls += 1
        result = original_fsum(cast(Any, values))
        return result + 1.0 if calls == divergent_call else result

    monkeypatch.setattr(pheromone_scoring.math, "fsum", divergent_fsum)
    with pytest.raises(GovernanceError, match=message):
        pheromone_scoring.score_pheromone_trails_result(
            candidate_set=pheromone_candidates(),
            trails=[],
            policy=pheromone_policy(),
        )


@pytest.mark.parametrize(
    ("report", "target", "verified", "message"),
    [
        (
            ScoutReport(
                "scout:a",
                "candidate:alpha",
                "evidence:a",
                "urn:test",
                target="target:other",
            ),
            "target:active",
            False,
            "targets target:other",
        ),
        (
            ScoutReport(
                "scout:a",
                "candidate:alpha",
                "evidence:a",
                "urn:test",
            ),
            "target:active",
            True,
            "must declare the active target",
        ),
        (
            ScoutReport(
                "scout:a",
                "candidate:alpha",
                "evidence:a",
                "urn:test",
                target="target:active",
            ),
            "target:active",
            True,
            "trace_event_id is required",
        ),
    ],
)
def test_swarm_scout_signal_target_and_trace_guards(
    report: ScoutReport,
    target: str,
    verified: bool,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        swarm_signals.validate_scout_report(
            report,
            target=target,
            require_verification=verified,
            maximum_strength=1.0,
        )


@pytest.mark.parametrize(
    ("signal", "target", "verified", "message"),
    [
        (
            RecruitmentSignal(
                "source:a",
                "candidate:alpha",
                target="target:other",
            ),
            "target:active",
            False,
            "targets target:other",
        ),
        (
            RecruitmentSignal("source:a", "candidate:alpha"),
            "target:active",
            True,
            "must declare the active target",
        ),
        (
            RecruitmentSignal(
                "source:a",
                "candidate:alpha",
                target="target:active",
                provenance="urn:test",
            ),
            "target:active",
            True,
            "trace_event_id is required",
        ),
        (
            RecruitmentSignal(
                "source:a",
                "candidate:alpha",
                target="target:active",
                provenance="urn:test",
                trace_event_id="trace:a",
            ),
            "target:active",
            True,
            "not governance-verified",
        ),
    ],
)
def test_swarm_collective_signal_target_trace_and_authority_guards(
    signal: RecruitmentSignal,
    target: str,
    verified: bool,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        swarm_signals.validate_collective_signal(
            signal,
            target=target,
            require_verification=verified,
            signal_name="recruitment",
            maximum_strength=1.0,
        )


def test_swarm_scoring_targetless_and_duplicate_signal_branches() -> None:
    candidates = collective_candidates()
    recruitment = RecruitmentSignal("source:a", "candidate:alpha")
    inhibition = InhibitionSignal("source:b", "candidate:beta")
    state = swarm_scoring.score_candidates(
        candidate_set=candidates,
        policy=collective_policy(
            mode="quorum",
            recruitment_enabled=True,
            inhibition_enabled=True,
        ),
        target=None,
        scout_reports=[],
        recruitment_signals=[recruitment],
        inhibition_signals=[inhibition],
    )
    assert state.scores["candidate:alpha"] == 1.0
    assert state.scores["candidate:beta"] == -1.0

    with pytest.raises(GovernanceError, match="duplicate recruitment source"):
        swarm_scoring.score_candidates(
            candidate_set=candidates,
            policy=collective_policy(
                mode="quorum",
                recruitment_enabled=True,
            ),
            target=None,
            scout_reports=[],
            recruitment_signals=[recruitment, recruitment],
        )
    with pytest.raises(GovernanceError, match="duplicate inhibition source"):
        swarm_scoring.score_candidates(
            candidate_set=candidates,
            policy=collective_policy(
                mode="quorum",
                inhibition_enabled=True,
            ),
            target=None,
            scout_reports=[],
            inhibition_signals=[inhibition, inhibition],
        )


def test_swarm_numeric_score_and_signal_branch_totality() -> None:
    candidates = collective_candidates()
    state = swarm_scoring.score_candidates(
        candidate_set=candidates,
        policy=collective_policy(mode="quorum"),
        target="decision:collective",
        scout_reports=[],
    )
    with pytest.raises(GovernanceError, match="candidate score must be finite"):
        swarm_scoring.validate_score_breakdown(
            replace(
                state,
                scores={**state.scores, "candidate:alpha": True},
            )
        )
    with pytest.raises(GovernanceError, match="non-finite value"):
        swarm_scoring.validate_score_breakdown(
            replace(
                state,
                score_breakdown={
                    **state.score_breakdown,
                    "candidate:alpha": {"controlled": True},
                },
            )
        )
    with pytest.raises(GovernanceError, match="must be a finite number"):
        swarm_signals.require_finite_non_negative(True, "controlled signal")


def test_hybrid_pipeline_early_contract_and_state_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full = hybrid_policy()
    candidates = hybrid_candidates()
    with pytest.raises(GovernanceError, match="current_step must be a non-negative"):
        swarm_pipeline._evaluate_hybrid_collective_step(
            candidate_set=candidates,
            policy=full,
            target="decision:hybrid",
            scout_reports=[],
            topology=cast(Any, object()),
            protocol_id="protocol:test",
            current_step=-1,
            require_legacy_replay_authority=False,
            issue_legacy_result=False,
        )
    with monkeypatch.context() as patch:
        patch.setattr(
            swarm_pipeline,
            "validate_collective_runtime_policy",
            lambda _policy: None,
        )
        with pytest.raises(
            GovernanceError, match="requires the complete declared Hybrid path"
        ):
            swarm_pipeline._evaluate_hybrid_collective_step(
                candidate_set=candidates,
                policy=replace(full, pheromone_enabled=False),
                target="decision:hybrid",
                scout_reports=[],
                topology=cast(Any, object()),
                protocol_id="protocol:test",
                current_step=0,
                require_legacy_replay_authority=False,
                issue_legacy_result=False,
            )
    with pytest.raises(GovernanceError, match="requires declared pheromone topology"):
        swarm_pipeline._evaluate_hybrid_collective_step(
            candidate_set=candidates,
            policy=full,
            target="decision:hybrid",
            scout_reports=[],
            topology=None,
            protocol_id="protocol:test",
            current_step=0,
            require_legacy_replay_authority=False,
            issue_legacy_result=False,
        )

    unsafe = _forged_dataclass(
        candidates.require_declared("candidate:fallback"),
        safe_fallback=False,
    )
    unsafe_candidates = SimpleNamespace(
        candidates=candidates.candidates,
        require_declared_for_target=lambda *_args, **_kwargs: unsafe,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            swarm_pipeline,
            "resolve_collective_fallback_id",
            lambda **_kwargs: "candidate:fallback",
        )
        with pytest.raises(
            GovernanceError, match="fallback candidate is not marked safe"
        ):
            swarm_pipeline._evaluate_hybrid_collective_step(
                candidate_set=cast(Any, unsafe_candidates),
                policy=full,
                target="decision:hybrid",
                scout_reports=[],
                topology=cast(Any, object()),
                protocol_id="protocol:test",
                current_step=0,
                require_legacy_replay_authority=False,
                issue_legacy_result=False,
            )


def test_hybrid_pipeline_replay_candidate_and_trail_totality_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full = hybrid_policy()
    candidates = hybrid_candidates()
    target = "decision:hybrid"
    topology = PheromoneNeighborhood(
        subjects=tuple(
            PheromoneSubject("candidate", candidate.id, candidate.id, target)
            for candidate in candidates.candidates
        )
    )

    with pytest.raises(GovernanceError, match="state projection is malformed"):
        swarm_pipeline._evaluate_hybrid_collective_step(
            candidate_set=candidates,
            policy=full,
            target=target,
            scout_reports=[],
            topology=topology,
            protocol_id="protocol:test",
            current_step=0,
            replay_state=cast(Any, object()),
            require_legacy_replay_authority=False,
            issue_legacy_result=False,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            swarm_pipeline,
            "_hybrid_replay_state_bindings_match",
            lambda *_args, **_kwargs: True,
        )
        with pytest.raises(GovernanceError, match="active protocol and target"):
            swarm_pipeline._evaluate_hybrid_collective_step(
                candidate_set=candidates,
                policy=full,
                target=target,
                scout_reports=[],
                topology=topology,
                protocol_id="protocol:test",
                current_step=0,
                replay_state=cast(
                    Any,
                    SimpleNamespace(
                        protocol_id="protocol:other",
                        target=target,
                    ),
                ),
                require_legacy_replay_authority=False,
                issue_legacy_result=False,
            )

    safe = SimpleNamespace(id="candidate:fallback", safe_fallback=True)
    empty_candidates = SimpleNamespace(
        candidates=(),
        require_declared_for_target=lambda *_args, **_kwargs: safe,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            swarm_pipeline,
            "resolve_collective_fallback_id",
            lambda **_kwargs: "candidate:fallback",
        )
        with pytest.raises(
            GovernanceError, match="no candidates for the active target"
        ):
            swarm_pipeline._evaluate_hybrid_collective_step(
                candidate_set=cast(Any, empty_candidates),
                policy=full,
                target=target,
                scout_reports=[],
                topology=topology,
                protocol_id="protocol:test",
                current_step=0,
                require_legacy_replay_authority=False,
                issue_legacy_result=False,
            )

    unbound = pheromone_trail(
        "",
        subject_type="route",
        subject_id="route:unbound",
        target=target,
        trace_id="trace:hybrid:unbound",
    )
    with pytest.raises(GovernanceError, match="must bind a declared candidate"):
        swarm_pipeline._evaluate_hybrid_collective_step(
            candidate_set=candidates,
            policy=full,
            target=target,
            scout_reports=[],
            existing_trails=[unbound],
            topology=topology,
            protocol_id="protocol:test",
            current_step=0,
            require_legacy_replay_authority=False,
            issue_legacy_result=False,
        )

    duplicate = pheromone_trail(
        "candidate:alpha",
        target=target,
        trace_id="trace:hybrid:duplicate",
    )
    with pytest.raises(GovernanceError, match="duplicate active pheromone"):
        swarm_pipeline._evaluate_hybrid_collective_step(
            candidate_set=candidates,
            policy=full,
            target=target,
            scout_reports=[],
            existing_trails=[duplicate, duplicate],
            topology=topology,
            protocol_id="protocol:test",
            current_step=0,
            require_legacy_replay_authority=False,
            issue_legacy_result=False,
        )


def test_hybrid_trace_skips_unprocessed_adjustment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adjustment = SimpleNamespace(
        layer_id="learned",
        source_id="source:controlled",
        trace_event_id="trace:adjustment:unprocessed",
    )
    empty_batch = SimpleNamespace(
        accepted_trace_event_ids=(),
        processed_trace_event_ids=(),
    )
    empty_result = SimpleNamespace(records=())
    with monkeypatch.context() as patch:
        patch.setattr(
            swarm_trace,
            "_input_trace_events",
            lambda **_kwargs: [],
        )
        patch.setattr(
            swarm_trace,
            "_pheromone_lifecycle_trace_events",
            lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("controlled after adjustment filtering")
            ),
        )
        with pytest.raises(RuntimeError, match="controlled after adjustment"):
            swarm_trace._hybrid_step_trace_events(
                protocol_id="protocol:controlled",
                target="decision:hybrid",
                candidate_set=cast(Any, object()),
                policy=cast(
                    Any,
                    SimpleNamespace(
                        recruitment_enabled=False,
                        inhibition_enabled=False,
                    ),
                ),
                pheromone_policy=cast(Any, object()),
                scout_reports=[],
                recruitment_signals=[],
                inhibition_signals=[],
                deposit_inputs=[],
                deposit_result=cast(Any, empty_result),
                deposit_replay_receipts={},
                diffusion_replay_receipts={},
                feedback_replay_receipts={},
                adjustment_replay_receipts={},
                evaporation_records=(),
                pre_diffusion_trails=(),
                diffusion_result=cast(Any, empty_result),
                feedback=[],
                reinforcement_result=cast(Any, empty_result),
                post_reinforcement_expiration_records=(),
                active_trails=(),
                observations=(),
                layer_proposals=[],
                performance_snapshots=[],
                strategy_biases=[],
                layer_state=cast(Any, object()),
                adjustment_proposals=[cast(Any, adjustment)],
                adjustment_batch=cast(Any, empty_batch),
                state=cast(Any, object()),
                decision=cast(Any, object()),
                current_step=0,
            )


def test_hybrid_replay_and_collective_state_defensive_guards() -> None:
    malformed_step = object.__new__(swarm_replay.HybridCollectiveStep)
    object.__setattr__(malformed_step, "_issuance", ("invalid",))
    with pytest.raises(GovernanceError, match="step issuance is malformed"):
        swarm_replay._replay_state_from_verified_hybrid_step(malformed_step)
    with pytest.raises(GovernanceError, match="authority bindings are invalid"):
        swarm_replay._issue_hybrid_replay_state(
            cast(Any, object()),
            protocol_id="protocol:test",
            target="target:test",
        )
    assert swarm_replay._canonical_replay_value({2, 1}) == (1, 2)

    candidates = collective_candidates()
    state = swarm_scoring.score_candidates(
        candidate_set=candidates,
        policy=collective_policy(mode="quorum"),
        scout_reports=[],
        target="decision:collective",
    )
    incomplete = replace(
        state,
        scores={"candidate:alpha": 0.0},
    )
    with pytest.raises(GovernanceError, match="cover exactly the active target"):
        swarm_pipeline._decide_collective_state(
            candidate_set=candidates,
            policy=collective_policy(mode="quorum"),
            target="decision:collective",
            state=incomplete,
        )
    invalid_scout = replace(
        state,
        independent_scouts={
            **state.independent_scouts,
            "candidate:alpha": frozenset({""}),
        },
    )
    with pytest.raises(GovernanceError, match="invalid scout identity"):
        swarm_pipeline._decide_collective_state(
            candidate_set=candidates,
            policy=collective_policy(mode="quorum"),
            target="decision:collective",
            state=invalid_scout,
        )


def test_support_v2_portable_methods_and_array_bounds(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = support_scenario.issued
    switched = support_scenario.switched
    lease = issued.snapshot.leases[0]
    revocation = switched.revoked_lease
    assert revocation is not None

    assert lease.canonical_bytes()
    assert revocation.canonical_bytes()

    membership = support_scenario.upstream.membership_state.snapshot
    observation = support_observation(
        support_scenario.ledger,
        membership,
        candidate_ref="candidate:proposal",
        claim_root="sha256:" + "b" * 64,
        principal_ref="principal:alpha",
        label="totality-proposal",
        current_step=4,
    )
    proposal = support_proposal(
        support_scenario.ledger,
        membership,
        observation,
        candidate_ref="candidate:proposal",
        claim_root="sha256:" + "b" * 64,
        principal_ref="principal:alpha",
        label="totality-proposal",
        current_step=4,
    )
    assert proposal.canonical_bytes()

    with pytest.raises(ValueError, match="active lease projection exceeds its bound"):
        canonical_support_leases_v2((lease,) * (MAX_SUPPORT_LEASES_V2 + 1))

    values = issued.to_dict()
    values["evicted_lease_roots"] = ()
    monkeypatch.setattr(
        support_common,
        "_preflight_support_resources_v2",
        lambda _value: None,
    )
    with pytest.raises(TypeError, match="must be an exact array"):
        support_request_contracts.SupportAdvanceRequestV2.from_dict(values)


def test_support_v2_remaining_contract_size_and_revocation_bytes(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    membership = support_scenario.upstream.membership_state.snapshot
    monkeypatch.setattr(
        membership_contracts,
        "MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2",
        len(membership.canonical_bytes()) - 1,
    )
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        replace(membership, snapshot_root="")

    revocation = support_scenario.switched.revocation
    assert revocation is not None
    assert revocation.canonical_bytes()


def test_support_v2_utf8_snapshot_and_eviction_regression_alarms(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(
            support_common,
            "_require_text",
            lambda _value, _label: "\ud800",
        )
        with pytest.raises(ValueError, match="must be valid UTF-8"):
            support_common._require_bounded_text_v2("placeholder", "support text")

    snapshot = support_scenario.initialized.snapshot
    monkeypatch.setattr(
        support_snapshot_contracts,
        "MAX_SUPPORT_SNAPSHOT_BYTES_V2",
        len(snapshot.canonical_bytes()) - 1,
    )
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        replace(snapshot, snapshot_root="")

    with pytest.raises(ValueError, match="eviction count exceeds"):
        support_mutation_delta_root_v2(
            mutation_kind=support_scenario.issued.mutation_kind,
            transition_id=support_scenario.issued.transition_id,
            mutation_issuer_ref=SUPPORT_ISSUER_REF,
            observed_epoch=support_scenario.issued.observed_epoch,
            current_step=support_scenario.issued.snapshot.current_step,
            mutation_provenance_root="sha256:" + "1" * 64,
            mutation_trace_roots=("sha256:" + "2" * 64,),
            issued_lease_root="",
            revoked_lease_root="",
            revocation_root="",
            evicted_lease_roots=tuple(
                "sha256:" + f"{index:064x}"
                for index in range(MAX_SUPPORT_EVICTIONS_V2 + 1)
            ),
            membership_stream_ref="",
            membership_transition_id="",
            membership_snapshot_root="",
        )


def test_support_v2_projection_time_and_equivocation_guards(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = support_scenario.issued.snapshot
    with pytest.raises(ValueError, match="time moves backwards"):
        _current_projection(parent, current_step=parent.current_step - 1)

    future_parent = SimpleNamespace(
        current_step=parent.current_step,
        leases=(
            SimpleNamespace(
                issued_at_step=parent.current_step + 1,
                expires_at_step=parent.current_step + 2,
            ),
        ),
    )
    with pytest.raises(ValueError, match="parent contains a future lease"):
        _current_projection(cast(Any, future_parent), current_step=parent.current_step)

    lease = support_scenario.issued.snapshot.leases[0]
    assert (
        _group_equivocation(
            support_scenario.issued.snapshot,
            (lease, lease),
            current_step=lease.issued_at_step,
        )
        is None
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_evaluation_engine,
            "_conflict_segments",
            lambda _intervals: ((lease.issued_at_step, lease.issued_at_step + 1),),
        )
        assert (
            _group_equivocation(
                support_scenario.issued.snapshot,
                (lease, lease),
                current_step=lease.issued_at_step,
            )
            is None
        )


def test_support_v2_projection_delta_totality_guards(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = support_scenario.issued
    switched = support_scenario.switched
    parent = support_scenario.issued.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(
            support_projection,
            "_validate_support_mutation_semantics_v2",
            lambda _request: None,
        )
        cross_bound_snapshot = _forged_dataclass(
            issued.snapshot,
            run_ref="run:other",
        )
        with pytest.raises(ValueError, match="child context is mismatched"):
            support_projection._validate_transition_delta(
                _forged_dataclass(issued, snapshot=cross_bound_snapshot),
                support_scenario.initialized.snapshot,
            )

        revoked = switched.revoked_lease
        assert revoked is not None
        with pytest.raises(ValueError, match="does not remove its exact prior lease"):
            support_projection._validate_transition_delta(
                _forged_dataclass(
                    switched,
                    revoked_lease=_forged_dataclass(
                        revoked,
                        lease_root="sha256:" + "f" * 64,
                    ),
                ),
                parent,
            )

        with pytest.raises(ValueError, match="issuance collides"):
            support_projection._validate_transition_delta(
                _forged_dataclass(
                    switched,
                    revoked_lease=None,
                    issued_lease=parent.leases[0],
                ),
                parent,
            )


def test_support_v2_source_binding_and_upstream_material_guards(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = support_scenario.issued
    binding = support_source_binding._source_binding_from_request(issued)
    forged_snapshot = _forged_dataclass(
        issued.snapshot,
        source_context_root="sha256:" + "f" * 64,
    )
    with pytest.raises(ValueError, match="source context root is mismatched"):
        support_source_binding._source_binding_from_request(
            _forged_dataclass(issued, snapshot=forged_snapshot)
        )

    parameters = inspect.signature(
        support_source_binding._build_source_binding
    ).parameters
    arguments = {
        name: getattr(binding, name) for name in parameters if name != "issued_lease"
    }
    arguments["mutation_kind"] = issued.mutation_kind
    arguments["issued_lease"] = None
    with pytest.raises(ValueError, match="issued lease material is incomplete"):
        support_source_binding._build_source_binding(**arguments)

    without_lease = _forged_dataclass(issued, issued_lease=None)
    with monkeypatch.context() as patch:
        patch.setattr(
            support_source_proof,
            "_validate_transition_delta",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            support_source_proof,
            "_support_parent",
            lambda _state: (support_scenario.initialized.snapshot, None),
        )
        patch.setattr(
            support_source_proof,
            "_membership_parent",
            lambda _state: (
                support_scenario.upstream.membership_state.snapshot,
                None,
            ),
        )
        with pytest.raises(ValueError, match="has no issued lease material"):
            support_source_proof._validate_source_upstreams(
                without_lease,
                manifest=support_scenario.ledger.manifest,
                parent_state=support_scenario.initialized_state,
                membership_state=support_scenario.upstream.membership_state,
                proposal=object(),
                observations=object(),
            )


def test_support_v2_manifest_and_membership_parent_context_guards(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = support_scenario.ledger.manifest
    snapshot = support_scenario.initialized.snapshot
    forged_policy = _forged_dataclass(
        manifest.collective_commit_policy,
        target="target:other",
    )
    detached = _forged_dataclass(
        manifest,
        collective_commit_policy=forged_policy,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_verification.ScopedProtocolManifestV2,
            "from_dict",
            classmethod(lambda _cls, _payload: detached),
        )
        with pytest.raises(ValueError, match="commit policy target is mismatched"):
            support_verification._validated_support_manifest_context_v2(
                manifest,
                profile=snapshot.profile,
                target_ref=snapshot.target_ref,
            )

    parent = support_scenario.upstream.membership_state.snapshot
    context = membership_source_module.durable_support_context_v2(
        manifest,
        profile=parent.profile,
        assurance=parent.assurance,
        target_ref=parent.target_ref,
    )
    common = {
        "context": context,
        "scope_ref": parent.scope_ref,
        "run_ref": parent.run_ref,
        "epoch": parent.epoch + 1,
        "current_step": parent.issued_at_step + 1,
    }
    with pytest.raises(ValueError, match="parent is cross-bound"):
        membership_source_module._validate_parent_context(
            parent,
            domain_root="sha256:" + "f" * 64,
            **common,
        )
    with pytest.raises(ValueError, match="must advance"):
        membership_source_module._validate_parent_context(
            parent,
            domain_root=parent.domain_root,
            **{
                **common,
                "epoch": parent.epoch,
            },
        )


def test_support_v2_invalid_assurance_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="assurance is unsupported"):
        support_assurance("unsupported", "support proposal")


class _ExplodingInstanceCheck(type):
    def __instancecheck__(cls, instance: object) -> bool:
        del cls, instance
        raise RuntimeError("controlled protocol instance check failure")


class _ExplodingReaderProtocol(metaclass=_ExplodingInstanceCheck):
    pass


@pytest.mark.parametrize(
    ("module", "function", "message"),
    [
        (
            membership_operations,
            membership_operations._require_reader,
            "membership requires StateReader v2",
        ),
        (
            verification_operations,
            verification_operations._require_reader,
            "principal verification requires StateReader v2",
        ),
        (
            support_operations,
            support_operations._require_state_reader,
            "support rehydration requires StateReader v2",
        ),
        (
            support_state_handle,
            support_state_handle._require_state_reader,
            "support state requires StateReader v2",
        ),
    ],
)
def test_support_v2_reader_protocol_exceptions_are_fail_closed(
    module: Any,
    function: Any,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "GovernanceStateReaderV2", _ExplodingReaderProtocol)
    with pytest.raises(TypeError, match=message):
        function(object())


def test_support_membership_handle_reader_protocol_exception_is_fail_closed(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        support_state_access,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )
    with pytest.raises(TypeError, match="membership StateReader v2 is invalid"):
        support_state_access._membership_handle_fields(
            support_scenario.upstream.membership_state
        )


def test_support_v2_operation_maps_issuer_and_source_mismatch(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    mismatched_issuer, source = support_initialize(
        ledger,
        label="totality-issuer-mismatch",
    )
    session = support_operations.open_support_authority_session_v2(
        support_capability(ledger, mismatched_issuer.observed_epoch),
        mismatched_issuer,
    )
    forged = object.__new__(SupportAdvanceRequestV2)
    for field in SupportAdvanceRequestV2.__dataclass_fields__:
        if field.startswith("_"):
            continue
        object.__setattr__(forged, field, getattr(mismatched_issuer, field))
    object.__setattr__(forged, "mutation_issuer_ref", "issuer:other")
    session_state, session_failure = support_operations._validated_session_or_failure(
        session,
        mismatched_issuer,
    )
    assert session_state is not None
    assert session_failure is None
    with monkeypatch.context() as patch:
        patch.setattr(
            support_operations,
            "_validated_session_or_failure",
            lambda _candidate, _request: (session_state, None),
        )
        attempt = support_operations.advance_support_state_v2(
            forged,
            source=source,
            authority_session=session,
        )
    assert attempt.failure is not None
    assert attempt.failure.path == "/mutation_issuer_ref"

    request, expected_source = support_initialize(
        ledger,
        label="totality-source-expected",
    )
    _, wrong_source = support_initialize(
        ledger,
        label="totality-source-wrong",
    )
    session = support_operations.open_support_authority_session_v2(
        support_capability(ledger, request.observed_epoch),
        request,
    )
    attempt = support_operations.advance_support_state_v2(
        request,
        source=wrong_source,
        authority_session=session,
    )
    assert expected_source is not wrong_source
    assert attempt.failure is not None
    assert attempt.failure.path == "/source/request_root"


def test_support_v2_operation_totality_paths(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    upstream = support_scenario.upstream

    membership_request, membership_source_value = _prepare_membership(
        ledger,
        upstream.verification_state,
        label="totality-membership-source-policy",
        epoch=upstream.verification_request.snapshot.epoch,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_operations,
            "_scoped_manifest_authority_matches_domain_v2",
            lambda *_args, **_kwargs: False,
        )
        failure = membership_operations._membership_source_failure(
            membership_request,
            membership_source_value,
            ledger.domain,
        )
    assert failure is not None
    assert failure.failure is not None
    assert failure.failure.path == "/manifest/authority_policy"

    binding_error = membership_operations.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/snapshot/verification_transition_id",
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_operations,
            "_validate_verification_inclusion",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(binding_error),
        )
        failure = membership_operations._load_current_verification_head(
            ledger.store,
            ledger.domain,
            membership_request,
        )
    assert failure.failure is not None
    assert failure.failure.path == "/snapshot/verification_transition_id"

    with monkeypatch.context() as patch:
        patch.setattr(
            membership_operations,
            "_governance_authority_session_state_v2",
            lambda _candidate: (_ for _ in ()).throw(TypeError("controlled")),
        )
        state, failure = membership_operations._validated_session(
            object(),
            membership_request,
        )
    assert state is None
    assert failure is not None
    assert failure.failure is not None
    assert failure.failure.path == "/authority_session"

    verification_request, verification_source = _prepare_verification(
        ledger,
        label="totality-verification-source-policy",
        epoch=2,
        parent=upstream.verification_request.snapshot,
    )
    verification_session = (
        verification_operations.open_principal_verification_authority_session_v2(
            support_capability(ledger, verification_request.observed_epoch),
            verification_request,
        )
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            verification_operations,
            "_scoped_manifest_authority_matches_domain_v2",
            lambda *_args, **_kwargs: False,
        )
        verification_failure = (
            verification_operations.advance_principal_verification_set_v2(
                verification_request,
                source=verification_source,
                authority_session=verification_session,
            )
        )
    assert verification_failure.failure is not None
    assert verification_failure.failure.path == "/manifest/authority_policy"

    with monkeypatch.context() as patch:
        patch.setattr(
            verification_operations,
            "_governance_authority_session_state_v2",
            lambda _candidate: (_ for _ in ()).throw(TypeError("controlled")),
        )
        state, failure = verification_operations._validated_session(
            object(),
            verification_request,
        )
    assert state is None
    assert failure is not None
    assert failure.failure is not None
    assert failure.failure.path == "/authority_session"

    support_request, support_source = support_initialize(
        ledger,
        label="totality-write-head-failure",
    )
    support_session = support_operations.open_support_authority_session_v2(
        support_capability(ledger, support_request.observed_epoch),
        support_request,
    )
    session_state, session_failure = support_operations._validated_session_or_failure(
        support_session,
        support_request,
    )
    assert session_state is not None
    assert session_failure is None
    material, source_failure = support_operations._validated_source_or_failure(
        session_state,
        support_request,
        support_source,
        ledger.domain,
    )
    assert material is not None
    assert source_failure is None
    write_failure = support_operations._failure_attempt(
        support_request,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/snapshot/parent_revision",
        support_operations.GovernanceFailureStageV2.VALIDATION,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_operations,
            "_validated_session_or_failure",
            lambda *_args, **_kwargs: (session_state, None),
        )
        patch.setattr(
            support_operations,
            "_validated_source_or_failure",
            lambda *_args, **_kwargs: (material, None),
        )
        patch.setattr(
            support_operations,
            "_write_head_or_failure",
            lambda *_args, **_kwargs: (None, write_failure),
        )
        attempt = support_operations.advance_support_state_v2(
            support_request,
            source=support_source,
            authority_session=support_session,
        )
    assert attempt is write_failure

    with monkeypatch.context() as patch:
        patch.setattr(
            support_operations,
            "_governance_authority_session_state_v2",
            lambda _candidate: (_ for _ in ()).throw(TypeError("controlled")),
        )
        state, failure = support_operations._validated_session_or_failure(
            object(),
            support_request,
        )
    assert state is None
    assert failure is not None
    assert failure.failure is not None
    assert failure.failure.path == "/authority_session"


def test_support_v2_membership_state_totality_paths(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    request = support_scenario.upstream.membership_request
    view = _shallow_committed_view(request)
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_state_module,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            membership_state_module,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, {}),
        )
        with pytest.raises(ValueError, match="receipt is mismatched"):
            membership_state_module._decode_committed_view_shallow(
                _shallow_committed_view(
                    request, revision=request.snapshot.revision + 1
                ),
                ledger.domain,
            )

        patch.setattr(
            membership_state_module,
            "_validate_read_set",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            membership_state_module,
            "_membership_event",
            lambda *_args, **_kwargs: object(),
        )
        with pytest.raises(ValueError, match="trace lineage is mismatched"):
            membership_state_module._decode_committed_view_shallow(
                view,
                ledger.domain,
            )

    child = _forged_dataclass(
        request,
        snapshot=_forged_dataclass(
            request.snapshot,
            parent_revision=1,
            parent_transition_id="transition:membership:cycle",
        ),
    )
    child_view = _shallow_committed_view(child)
    reader = cast(
        Any,
        SimpleNamespace(
            load_commit_view_v2=lambda *_args, **_kwargs: child_view,
        ),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_state_module,
            "_validate_verification_inclusion",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            membership_state_module,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            membership_state_module,
            "_decode_committed_view_shallow",
            lambda *_args, **_kwargs: (child, {}),
        )
        patch.setattr(
            membership_state_module,
            "_continuity_failure",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError, match="history contains a cycle"):
            membership_state_module._validate_history(
                reader,
                ledger.domain,
                child,
            )

    binding_error = membership_state_module.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/controlled",
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_state_module,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            membership_state_module,
            "_decode_committed_view_shallow",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(binding_error),
        )
        with pytest.raises(type(binding_error)) as exc_info:
            membership_state_module._load_verified_request_view(
                reader,
                ledger.domain,
                request,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/controlled"


def test_support_v2_principal_verification_state_totality_paths(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    request = support_scenario.upstream.verification_request
    view = _shallow_committed_view(request)
    with monkeypatch.context() as patch:
        patch.setattr(
            verification_state_module,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            verification_state_module,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, {}),
        )
        with pytest.raises(ValueError, match="receipt is mismatched"):
            verification_state_module._decode_committed_view_shallow(
                _shallow_committed_view(
                    request, revision=request.snapshot.revision + 1
                ),
                ledger.domain,
            )

        patch.setattr(
            verification_state_module,
            "_validate_read_set",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            verification_state_module,
            "_verification_event",
            lambda *_args, **_kwargs: object(),
        )
        with pytest.raises(ValueError, match="trace lineage is mismatched"):
            verification_state_module._decode_committed_view_shallow(
                view,
                ledger.domain,
            )

    child, _ = _prepare_verification(
        ledger,
        label="totality-verification-state-history",
        epoch=2,
        parent=request.snapshot,
    )
    child_view = _shallow_committed_view(child)
    reader = cast(
        Any,
        SimpleNamespace(
            load_commit_view_v2=lambda *_args, **_kwargs: child_view,
        ),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            verification_state_module,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            verification_state_module,
            "_decode_committed_view_shallow",
            lambda *_args, **_kwargs: (child, {}),
        )
        patch.setattr(
            verification_state_module,
            "_continuity_failure",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError, match="history contains a cycle"):
            verification_state_module._validate_history(
                reader,
                ledger.domain,
                child,
            )

    binding_error = verification_state_module.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/controlled",
    )
    for error, expected_path in (
        (binding_error, "/controlled"),
        (ValueError("controlled"), "/transition_id"),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(
                verification_state_module,
                "_canonical_commit_view_v2",
                lambda value, **_kwargs: value,
            )
            patch.setattr(
                verification_state_module,
                "_decode_committed_view_shallow",
                lambda *_args, error=error, **_kwargs: (_ for _ in ()).throw(error),
            )
            with pytest.raises(
                verification_state_module.GovernanceAuthorityBindingErrorV2
            ) as exc_info:
                verification_state_module._load_verified_request_view(
                    reader,
                    ledger.domain,
                    request,
                    expected_receipt_root=None,
                )
        assert exc_info.value.path == expected_path


def test_support_v2_state_load_decode_and_read_set_totality(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    request = support_scenario.initialized
    with monkeypatch.context() as patch:
        patch.setattr(
            support_state_load,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        with pytest.raises(
            support_state_load.GovernanceAuthorityBindingErrorV2,
            match="governance_committed_transition_invalid",
        ):
            support_state_load._decode_committed_view(
                SimpleNamespace(
                    disposition=object(),
                    committed_transition=None,
                    position_observation=None,
                ),
                ledger.domain,
            )

        patch.setattr(
            support_state_load,
            "_decode_state_records",
            lambda *_args, **_kwargs: (request, {}, "", "", None),
        )
        with pytest.raises(ValueError, match="receipt is mismatched"):
            support_state_load._decode_committed_view(
                _shallow_committed_view(
                    request, revision=request.snapshot.revision + 1
                ),
                ledger.domain,
            )

        patch.setattr(
            support_state_load,
            "_validate_committed_read_set",
            lambda *_args, **_kwargs: None,
        )
        patch.setattr(
            support_state_load,
            "_support_events",
            lambda *_args, **_kwargs: (object(),),
        )
        with pytest.raises(ValueError, match="trace lineage is mismatched"):
            support_state_load._decode_committed_view(
                _shallow_committed_view(request),
                ledger.domain,
            )

    duplicate_entry = SimpleNamespace(
        stream_ref=request.stream_ref,
        expected_revision=0,
        expected_root="sha256:" + "0" * 64,
    )
    duplicate_view = _shallow_committed_view(request)
    duplicate_view.committed_transition.batch.read_set.entries = (
        duplicate_entry,
        duplicate_entry,
    )
    with pytest.raises(ValueError, match="duplicate streams"):
        support_state_load._validate_committed_read_set(
            duplicate_view,
            request,
            {},
            membership_precondition=None,
        )

    binding = {
        "grant_ref": "grant:controlled",
        "grant_expected_revision": 0,
        "grant_expected_root": "sha256:" + "3" * 64,
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": "sha256:" + "4" * 64,
    }
    with pytest.raises(ValueError, match="authority read set is mismatched"):
        support_state_load._validate_committed_read_set(
            _shallow_committed_view(request),
            request,
            binding,
            membership_precondition=None,
        )


def test_support_v2_state_load_history_and_verified_view_totality(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    initialized = support_scenario.initialized
    with pytest.raises(ValueError, match="genesis Store lineage is invalid"):
        support_state_load._validate_history(
            cast(
                Any,
                SimpleNamespace(load_commit_view_v2=lambda *_args, **_kwargs: None),
            ),
            ledger.domain,
            initialized,
            _shallow_committed_view(initialized, parent_root="sha256:" + "f" * 64),
        )

    child = support_scenario.issued
    child_view = _shallow_committed_view(child, parent_root="sha256:" + "7" * 64)
    parent_view = _shallow_committed_view(
        support_scenario.initialized,
        head_root="sha256:" + "7" * 64,
    )
    reader = cast(
        Any,
        SimpleNamespace(
            load_commit_view_v2=lambda *_args, **_kwargs: parent_view,
        ),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_state_load,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            support_state_load,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (child, {}, "", "", None),
        )
        patch.setattr(
            support_state_load,
            "_validate_transition_delta",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError, match="history contains a cycle"):
            support_state_load._validate_history(
                reader,
                ledger.domain,
                child,
                child_view,
            )

    reordered_parent = _shallow_committed_view(
        support_scenario.initialized,
        head_root="sha256:" + "8" * 64,
    )
    reordered_reader = cast(
        Any,
        SimpleNamespace(
            load_commit_view_v2=lambda *_args, **_kwargs: reordered_parent,
        ),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_state_load,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            support_state_load,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (
                support_scenario.initialized,
                {},
                "",
                "",
                None,
            ),
        )
        with pytest.raises(ValueError, match="Store heads are reordered"):
            support_state_load._validate_history(
                reordered_reader,
                ledger.domain,
                child,
                child_view,
            )

    view = _shallow_committed_view(initialized)
    verified_reader = cast(
        Any,
        SimpleNamespace(
            load_commit_view_v2=lambda *_args, **_kwargs: view,
        ),
    )
    binding_error = support_state_load.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/controlled",
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            support_state_load,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            support_state_load,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(binding_error),
        )
        with pytest.raises(type(binding_error)) as exc_info:
            support_state_load._load_verified_request_view(
                verified_reader,
                ledger.domain,
                initialized,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/controlled"

    other = _forged_dataclass(initialized, mutation_ref="mutation:other")
    with monkeypatch.context() as patch:
        patch.setattr(
            support_state_load,
            "_canonical_commit_view_v2",
            lambda value, **_kwargs: value,
        )
        patch.setattr(
            support_state_load,
            "_decode_committed_view",
            lambda *_args, **_kwargs: (other, {}, "", "", None),
        )
        patch.setattr(
            support_state_load,
            "_validate_history",
            lambda *_args, **_kwargs: None,
        )
        with pytest.raises(type(binding_error)) as exc_info:
            support_state_load._load_verified_request_view(
                verified_reader,
                ledger.domain,
                initialized,
                expected_receipt_root=None,
            )
    assert exc_info.value.path == "/request_root"


def test_support_v2_upstream_continuity_failures_map_exact_diagnostics(
    support_scenario: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = support_scenario.ledger
    upstream = support_scenario.upstream
    next_verification, verification_source = _prepare_verification(
        ledger,
        label="totality-next-verification",
        epoch=2,
        parent=upstream.verification_request.snapshot,
    )
    verification_session = (
        verification_operations.open_principal_verification_authority_session_v2(
            support_capability(ledger, next_verification.observed_epoch),
            next_verification,
        )
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            verification_operations,
            "_continuity_failure",
            lambda _request, _parent: (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot/parent_revision",
            ),
        )
        verification_attempt = (
            verification_operations.advance_principal_verification_set_v2(
                next_verification,
                source=verification_source,
                authority_session=verification_session,
            )
        )
    assert verification_attempt.failure is not None
    assert verification_attempt.failure.path == "/snapshot/parent_revision"

    _, verification_state = _commit_verification(
        ledger,
        label="totality-membership-verification",
        epoch=2,
        parent=upstream.verification_request.snapshot,
    )
    next_membership, membership_source = _prepare_membership(
        ledger,
        verification_state,
        label="totality-next-membership",
        epoch=2,
        parent=upstream.membership_request.snapshot,
    )
    membership_session = membership_operations.open_membership_authority_session_v2(
        support_capability(ledger, next_membership.observed_epoch),
        next_membership,
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            membership_operations,
            "_continuity_failure",
            lambda _request, _parent: (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot/parent_revision",
            ),
        )
        membership_attempt = membership_operations.commit_membership_epoch_v2(
            next_membership,
            source=membership_source,
            authority_session=membership_session,
        )
    assert membership_attempt.failure is not None
    assert membership_attempt.failure.path == "/snapshot/parent_revision"
