from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.authority_domain import (
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    PreparedGovernanceTransition,
)
from pheroos.governance.attention import (
    AttentionReopenEligibility,
    AttentionSubjectPriority,
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    attention_breakdown_payload,
    derive_exploration_directive,
    evaluate_hybrid_attention_step,
    exploration_directive_is_authoritative,
    exploration_directive_payload,
)
from pheroos.governance.atomic_evaluation import (
    AtomicHybridCommitStatus,
    commit_prepared_hybrid_transition,
    evaluate_and_commit_hybrid_step,
    finalize_hybrid_commit_transition,
    hybrid_commit_stream,
    prepare_hybrid_commit_transition,
)
from pheroos.governance.challenge import (
    ChallengeCoverage,
    ChallengeResult,
    challenge_attestation_payload,
    challenge_coverage_fingerprint,
    challenge_coverage_payload,
    evaluate_challenge_coverage,
    verified_challenge_is_authoritative,
    verified_challenge_fingerprint,
    verified_challenge_matches,
    verified_challenge_payload,
    verify_challenge_attestation,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import (
    EvidenceGroupContribution,
    SourceDomainContribution,
    bind_evidence,
    evidence_binding_is_authoritative,
    evidence_binding_matches,
    evidence_binding_payload,
    evidence_summary_payload,
    evaluate_evidence_binding,
    rebuild_evidence_binding_roots,
)
from pheroos.governance.layer_coordination import (
    LayerPerformanceSnapshot,
    StrategyBias,
    allocate_layer_weights,
    assess_layer_confidences,
    detect_layer_conflicts,
    evaluate_layer_coordination,
    layer_action_effect,
    materialize_layer_pheromone_proposals,
    proposal_score_delta,
    strategy_bias_score_delta,
    validate_layer_coordination_policy,
    validate_layer_performance_snapshots,
    validate_layer_proposal,
    validate_layer_proposals,
    validate_strategy_bias,
    validate_strategy_biases,
)
from pheroos.governance.pheromone import (
    PheromoneDiffusionPolicy,
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    clip_pheromone_strength,
    legacy_pheromone_weight,
    normalize_legacy_pheromone_trail,
    pheromone_lineage,
    pheromone_subject_id,
    pheromone_subject_type,
    topology_subject_candidate_id,
    topology_subject_target,
    validate_pheromone_diffusion_policy,
    validate_pheromone_subject_binding,
    validate_pheromone_topology,
    validate_pheromone_trail,
)
from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationPolarity,
    counterevidence_disposition_is_authoritative,
    counterevidence_disposition_fingerprint,
    counterevidence_disposition_matches,
    counterevidence_disposition_payload,
    counterevidence_is_material_critical,
    issue_counterevidence_disposition,
    observation_attestation_payload,
    observation_weight_ppm,
    verified_observation_is_authoritative,
    verified_observation_matches,
    verified_observation_payload,
    verify_observation_attestation,
)
from tests.governance import test_hybrid_pheromone_hardening as pheromone_fixture
from tests.governance import test_atomic_hybrid_commit as atomic_fixture
from tests.governance import test_hybrid_commit_separation as attention_fixture
from tests.governance import test_observation_binding as observation_fixture


_SCOPE = "sha256:" + ("1" * 64)
_OTHER_SCOPE = "sha256:" + ("2" * 64)
_ROOT = "sha256:" + ("a" * 64)
_OTHER_ROOT = "sha256:" + ("b" * 64)
_STREAM = "authority:test"
_TRANSITION_ID = "transition:test"


class _SplitHashText(str):
    """Inbound string with canonical bytes but an adversarial container hash."""

    _salt: str

    def __new__(cls, value: str, salt: str) -> _SplitHashText:
        instance = str.__new__(cls, value)
        instance._salt = salt
        return instance

    def __hash__(self) -> int:
        return hash((str(self), self._salt))


class _NonEqualText(str):
    """Inbound string with canonical bytes but identity-only equality."""

    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)


def _authority_domain_records() -> tuple[
    AuthorityDomain,
    GovernanceHead,
    PreparedGovernanceTransition,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
]:
    domain = AuthorityDomain(_SCOPE)
    head = GovernanceHead.genesis(_SCOPE, _STREAM)
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id=_TRANSITION_ID,
        state_records={"enabled": True, "ratio": 0.5, "values": [1, None]},
        identity_claims={"claim:test": {"principal": "principal:test"}},
    )
    trace = {
        "trace_id": "trace:test",
        "scope_ref": _SCOPE,
        "stream": _STREAM,
        "transition_id": _TRANSITION_ID,
    }
    batch = GovernanceCommitBatch(transition=transition, trace_records=[trace])
    receipt = GovernanceCommitReceipt(
        scope_ref=_SCOPE,
        stream=_STREAM,
        transition_id=_TRANSITION_ID,
        revision=1,
        parent_root=transition.expected_state_root,
        state_root=transition.state_root,
        trace_root=batch.trace_root,
        batch_root=batch.batch_root,
    )
    return domain, head, transition, batch, receipt


def test_authority_record_fingerprints_are_canonical_and_stable() -> None:
    domain, head, transition, batch, receipt = _authority_domain_records()

    assert domain.fingerprint().startswith("sha256:")
    assert head.fingerprint().startswith("sha256:")
    assert transition.fingerprint().startswith("sha256:")
    assert batch.fingerprint() == batch.batch_root
    assert receipt.fingerprint() == receipt.receipt_root


@pytest.mark.parametrize(
    ("record_index", "schema"),
    (
        (0, "pheroos-authority-domain-v1"),
        (1, "pheroos-governance-head-v1"),
        (2, "pheroos-prepared-governance-transition-v1"),
        (3, "pheroos-governance-commit-batch-v1"),
        (4, "pheroos-governance-commit-receipt-v1"),
    ),
)
def test_authority_records_reject_schema_and_shape_substitution(
    record_index: int,
    schema: str,
) -> None:
    records = _authority_domain_records()
    record = records[record_index]
    record_type = type(record)
    payload = record.to_dict()

    with pytest.raises(GovernanceError, match="schema is unsupported"):
        record_type.from_dict({**payload, "schema": "pheroos-foreign-v1"})
    with pytest.raises(GovernanceError, match="exact declared fields"):
        record_type.from_dict({**payload, "extra": True})
    with pytest.raises(GovernanceError, match="exact declared fields"):
        record_type.from_dict(None)  # type: ignore[arg-type]

    assert payload["schema"] == schema


@pytest.mark.parametrize("revision", (-1, True, 0.5))
def test_authority_head_rejects_noncanonical_revision(revision: object) -> None:
    with pytest.raises(GovernanceError, match="revision must be a non-negative"):
        GovernanceHead(
            scope_ref=_SCOPE,
            stream=_STREAM,
            revision=revision,  # type: ignore[arg-type]
            parent_root=_ROOT,
            state_root=_ROOT,
            transition_id=_TRANSITION_ID,
        )


def test_authority_head_rejects_noncanonical_identity() -> None:
    with pytest.raises(GovernanceError, match="canonical non-blank text"):
        GovernanceHead(
            scope_ref=_SCOPE,
            stream=" stream",
            revision=0,
            parent_root=_ROOT,
            state_root=_ROOT,
            transition_id=_TRANSITION_ID,
        )


def test_authority_domain_rejects_noncanonical_scope_digest() -> None:
    with pytest.raises(GovernanceError, match="canonical SHA-256 digest"):
        AuthorityDomain("scope:not-a-digest")


def test_prepared_transition_rejects_invalid_public_inputs_and_roots() -> None:
    _, head, transition, _, _ = _authority_domain_records()
    common: dict[str, Any] = {
        "domain": AuthorityDomain(_SCOPE),
        "stream": _STREAM,
        "transition_id": _TRANSITION_ID,
        "expected_revision": 0,
        "expected_parent_root": _ROOT,
        "expected_state_root": _ROOT,
        "state_records": {},
    }

    invalid_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"domain": object()}, "authority domain is invalid"),
        ({"expected_revision": True}, "expected revision must be"),
        ({"state_records": []}, "state records must be a mapping"),
        ({"identity_claims": []}, "identity claims must be a mapping"),
        ({"identity_claims": {"claim:test": []}}, "claim body must be a mapping"),
        ({"state_records": {"": 1}}, "keys must be non-empty strings"),
        ({"state_records": {"bad": float("inf")}}, "non-finite number"),
        ({"state_records": {"bad": object()}}, "unsupported value type"),
        ({"state_root": _OTHER_ROOT}, "state root does not match"),
    )
    for changes, fragment in invalid_cases:
        with pytest.raises(GovernanceError, match=fragment):
            PreparedGovernanceTransition(**{**common, **changes})

    with pytest.raises(GovernanceError, match="requires a governance head"):
        PreparedGovernanceTransition.from_head(
            object(),  # type: ignore[arg-type]
            transition_id=_TRANSITION_ID,
            state_records={},
        )

    payload = transition.to_dict()
    with pytest.raises(GovernanceError, match="domain must be an object"):
        PreparedGovernanceTransition.from_dict({**payload, "domain": []})
    with pytest.raises(GovernanceError, match="scope does not match"):
        PreparedGovernanceTransition.from_dict({**payload, "scope_ref": _OTHER_SCOPE})

    assert PreparedGovernanceTransition.from_head(
        head,
        transition_id="transition:float",
        state_records={"ratio": 0.25},
    ).to_dict()["state_records"] == {"ratio": 0.25}


def test_commit_batch_rejects_invalid_trace_and_integrity_inputs() -> None:
    _, _, transition, batch, _ = _authority_domain_records()
    valid_trace = dict(batch.to_dict()["trace_records"][0])

    invalid_cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"transition": object()}, "transition is invalid"),
        ({"trace_records": "trace"}, "trace records must be a sequence"),
        ({"trace_records": []}, "requires at least one trace"),
        ({"trace_records": [object()]}, "trace record must be a mapping"),
        (
            {"trace_records": [valid_trace, dict(valid_trace)]},
            "trace ids must be unique",
        ),
        (
            {"trace_records": [{**valid_trace, "scope_ref": _OTHER_SCOPE}]},
            "crosses authority scope",
        ),
        (
            {"trace_records": [{**valid_trace, "stream": "authority:other"}]},
            "crosses authority stream",
        ),
        (
            {"trace_records": [{**valid_trace, "transition_id": "transition:other"}]},
            "transition id is mismatched",
        ),
        ({"trace_root": _OTHER_ROOT}, "trace root does not match"),
        ({"batch_root": _OTHER_ROOT}, "batch root does not match"),
    )
    for changes, fragment in invalid_cases:
        with pytest.raises(GovernanceError, match=fragment):
            GovernanceCommitBatch(
                transition=changes.get("transition", transition),  # type: ignore[arg-type]
                trace_records=changes.get("trace_records", [valid_trace]),  # type: ignore[arg-type]
                trace_root=changes.get("trace_root", ""),  # type: ignore[arg-type]
                batch_root=changes.get("batch_root", ""),  # type: ignore[arg-type]
            )

    payload = batch.to_dict()
    with pytest.raises(GovernanceError, match="transition must be an object"):
        GovernanceCommitBatch.from_dict({**payload, "transition": []})


def test_receipt_rejects_invalid_revision_and_integrity_root() -> None:
    _, _, _, _, receipt = _authority_domain_records()
    with pytest.raises(GovernanceError, match="revision must be a positive"):
        replace(receipt, revision=0, receipt_root="")
    with pytest.raises(GovernanceError, match="receipt root does not match"):
        replace(receipt, receipt_root=_OTHER_ROOT)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("state_records", {1: "bad"}, "keys must be non-empty strings"),
        ("state_records", {"bad": float("nan")}, "non-finite number"),
        ("state_records", {"bad": object()}, "unsupported value type"),
    ),
)
def test_public_authority_serialization_rejects_post_issuance_corruption(
    field: str,
    value: object,
    fragment: str,
) -> None:
    _, _, transition, _, _ = _authority_domain_records()
    object.__setattr__(transition, field, value)

    with pytest.raises(GovernanceError, match=fragment):
        transition.to_dict()


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"enabled": 1}, "enabled must be boolean"),
        ({"max_hops": True}, "max_hops must be a non-negative integer"),
        ({"attenuation": 1.1}, "attenuation must be between 0 and 1"),
    ),
)
def test_pheromone_diffusion_policy_rejects_invalid_public_declarations(
    changes: dict[str, object],
    fragment: str,
) -> None:
    policy = PheromoneDiffusionPolicy(enabled=False, max_hops=0, attenuation=0.0)

    with pytest.raises(GovernanceError, match=fragment):
        validate_pheromone_diffusion_policy(replace(policy, **changes))


def test_pheromone_clip_preserves_finite_policy_bounds() -> None:
    policy = pheromone_fixture.policy(min_strength=0.25, max_strength=2.0)

    assert clip_pheromone_strength(-1.0, policy) == 0.25
    assert clip_pheromone_strength(3.0, policy) == 2.0


@pytest.mark.parametrize(
    ("strength", "fragment"),
    (
        (0.1, "below the declared minimum"),
        (2.1, "exceeds the declared maximum"),
    ),
)
def test_active_pheromone_trail_enforces_declared_strength_bounds(
    strength: float,
    fragment: str,
) -> None:
    with pytest.raises(GovernanceError, match=fragment):
        validate_pheromone_trail(
            replace(pheromone_fixture.trail(), strength=strength),
            pheromone_fixture.policy(min_strength=0.25, max_strength=2.0),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"candidate_id": 1}, "candidate_id must be a string"),
        ({"subject_type": "foreign"}, "unsupported pheromone subject type"),
        (
            {
                "candidate_id": "",
                "subject_id": "",
                "route_id": "",
                "tool_id": "",
            },
            "must declare a subject",
        ),
        ({"evidence_id": " "}, "must be non-blank when declared"),
        (
            {"candidate_id": "candidate:beta", "subject_id": "candidate:alpha"},
            "subject_id must match candidate_id",
        ),
        ({"source_id": " "}, "source_id must be non-blank"),
        ({"target": ""}, "must declare target"),
        ({"target": "decision:foreign"}, "not candidate target"),
        ({"lineage_event_ids": ("",)}, "must be non-empty strings"),
        (
            {"lineage_event_ids": ("trace:a", "trace:a")},
            "must not contain duplicates",
        ),
        (
            {"diffusion_root_trace_event_id": "trace:root"},
            "root pheromone trail cannot declare diffusion lineage",
        ),
        ({"diffusion_hop": 1}, "requires explicit diffusion lineage"),
        (
            {
                "diffusion_hop": 1,
                "diffusion_root_trace_event_id": "trace:root",
                "diffusion_parent_trace_event_id": "trace:parent",
                "lineage_event_ids": ("trace:root",),
            },
            "diffusion lineage is inconsistent",
        ),
    ),
)
def test_pheromone_trail_rejects_invalid_lineage_and_scope(
    changes: dict[str, object],
    fragment: str,
) -> None:
    trail = replace(pheromone_fixture.trail(), **changes)

    with pytest.raises(GovernanceError, match=fragment):
        validate_pheromone_trail(
            trail,
            pheromone_fixture.policy(),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_pheromone_trail_rejects_candidate_bound_to_another_active_target() -> None:
    foreign = pheromone_fixture.trail(
        "candidate:foreign",
        subject_id="candidate:foreign",
        target="decision:foreign",
    )

    with pytest.raises(GovernanceError, match="not active target"):
        validate_pheromone_trail(
            foreign,
            pheromone_fixture.policy(),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_pheromone_trail_without_candidate_catalog_still_rejects_target_mismatch() -> (
    None
):
    with pytest.raises(GovernanceError, match="not active target"):
        validate_pheromone_trail(
            replace(pheromone_fixture.trail(), target="decision:other"),
            pheromone_fixture.policy(),
            candidate_set=None,
            target=pheromone_fixture.TARGET,
        )


def test_active_pheromone_trail_requires_source_identity() -> None:
    trail = replace(pheromone_fixture.trail(), source_id="", provenance="")
    with pytest.raises(GovernanceError, match="requires a non-blank source identity"):
        validate_pheromone_trail(
            trail,
            pheromone_fixture.policy(require_provenance=False, require_trace=True),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_legacy_pheromone_subject_resolution_and_minimal_lineage() -> None:
    base = pheromone_fixture.trail()
    candidate = replace(base, subject_id="")
    route = replace(
        base,
        candidate_id="",
        subject_id="",
        route_id="route:test",
        tool_id="",
    )
    tool = replace(
        base,
        candidate_id="",
        subject_id="",
        route_id="",
        tool_id="tool:test",
    )
    empty = replace(
        base,
        candidate_id="",
        subject_id="",
        route_id="",
        tool_id="",
        target="",
    )

    assert (pheromone_subject_type(route), pheromone_subject_id(route)) == (
        "route",
        "route:test",
    )
    assert (pheromone_subject_type(candidate), pheromone_subject_id(candidate)) == (
        "candidate",
        "candidate:alpha",
    )
    assert (pheromone_subject_type(tool), pheromone_subject_id(tool)) == (
        "tool",
        "tool:test",
    )
    assert (pheromone_subject_type(empty), pheromone_subject_id(empty)) == (
        "candidate",
        "",
    )
    assert pheromone_lineage(empty) == {
        "candidate_id": "",
        "subject_type": "candidate",
        "subject_id": "",
        "kind": "positive",
        "source_id": "source:a",
        "evidence_id": "evidence:trace:deposit:a",
        "provenance": "runtime:source:a",
        "trace_event_id": "trace:deposit:a",
        "lineage_event_ids": ["trace:deposit:a"],
        "new_strength": 1.0,
        "step": 0,
    }
    assert legacy_pheromone_weight("x-neutral", pheromone_fixture.policy()) == 0.0
    assert (
        legacy_pheromone_weight("alarm", pheromone_fixture.policy())
        == pheromone_fixture.policy().cautionary_weight
    )

    normalized = normalize_legacy_pheromone_trail(
        base,
        target=base.target,
        source_id=base.source_id,
        source_role=base.source_role,
        evidence_id=base.evidence_id,
        provenance=base.provenance,
        trace_event_id=base.trace_event_id,
    )
    assert normalized == base


def _valid_topology() -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "candidate",
                "candidate:alpha",
                "candidate:alpha",
                pheromone_fixture.TARGET,
            ),
            PheromoneSubject(
                "route",
                "route:alpha",
                "candidate:alpha",
                pheromone_fixture.TARGET,
            ),
        ],
        edges=[
            PheromoneEdge(
                "candidate",
                "candidate:alpha",
                "route",
                "route:alpha",
                attenuation=0.5,
            )
        ],
    )


@pytest.mark.parametrize(
    ("subject", "fragment"),
    (
        (
            PheromoneSubject(
                1,  # type: ignore[arg-type]
                "subject:test",
                "candidate:alpha",
                pheromone_fixture.TARGET,
            ),
            "subject_type must be a string",
        ),
        (
            PheromoneSubject(
                "route",
                "route:test",
                " ",
                pheromone_fixture.TARGET,
            ),
            "must be non-blank when declared",
        ),
        (
            PheromoneSubject(
                "foreign",
                "subject:test",
                "candidate:alpha",
                pheromone_fixture.TARGET,
            ),
            "unsupported pheromone subject type",
        ),
        (
            PheromoneSubject(
                "route",
                "",
                "candidate:alpha",
                pheromone_fixture.TARGET,
            ),
            "subject_id is required",
        ),
        (
            PheromoneSubject(
                "candidate",
                "candidate:alpha",
                "candidate:beta",
                pheromone_fixture.TARGET,
            ),
            "subject_id must match candidate_id",
        ),
        (
            PheromoneSubject(
                "candidate",
                "candidate:foreign",
                "candidate:foreign",
                "decision:foreign",
            ),
            "not active target",
        ),
        (
            PheromoneSubject("candidate", "candidate:alpha", "", ""),
            "must declare target or candidate binding",
        ),
        (
            PheromoneSubject(
                "route", "route:test", "candidate:alpha", "decision:other"
            ),
            "not candidate target",
        ),
    ),
)
def test_pheromone_topology_rejects_invalid_subjects(
    subject: PheromoneSubject,
    fragment: str,
) -> None:
    candidate_set = (
        None if "must declare target" in fragment else pheromone_fixture.candidates()
    )
    with pytest.raises(GovernanceError, match=fragment):
        validate_pheromone_topology(
            PheromoneNeighborhood(subjects=[subject]),
            candidate_set=candidate_set,
            target=pheromone_fixture.TARGET,
        )


@pytest.mark.parametrize(
    ("edge", "fragment"),
    (
        (
            PheromoneEdge("", "candidate:alpha", "route", "route:alpha"),
            "must be a non-empty string",
        ),
        (
            PheromoneEdge("foreign", "candidate:alpha", "route", "route:alpha"),
            "unsupported pheromone edge source type",
        ),
        (
            PheromoneEdge("candidate", "candidate:alpha", "foreign", "route:alpha"),
            "unsupported pheromone edge target type",
        ),
        (
            PheromoneEdge(
                "candidate",
                "candidate:alpha",
                "route",
                "route:alpha",
                attenuation=1.1,
            ),
            "attenuation must be between 0 and 1",
        ),
    ),
)
def test_pheromone_topology_rejects_invalid_edges(
    edge: PheromoneEdge,
    fragment: str,
) -> None:
    topology = replace(_valid_topology(), edges=[edge])

    with pytest.raises(GovernanceError, match=fragment):
        validate_pheromone_topology(
            topology,
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_pheromone_topology_rejects_duplicate_edge() -> None:
    topology = _valid_topology()
    duplicate = replace(topology, edges=[topology.edges[0], topology.edges[0]])

    with pytest.raises(GovernanceError, match="duplicate pheromone topology edge"):
        validate_pheromone_topology(
            duplicate,
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_pheromone_topology_rejects_undeclared_edge_endpoint() -> None:
    topology = replace(
        _valid_topology(),
        edges=[
            PheromoneEdge(
                "candidate",
                "candidate:alpha",
                "tool",
                "tool:undeclared",
            )
        ],
    )
    with pytest.raises(GovernanceError, match="reference declared topology subjects"):
        validate_pheromone_topology(
            topology,
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_pheromone_topology_public_resolution_and_unbound_subject_rejection() -> None:
    candidate = PheromoneSubject("candidate", "candidate:alpha")
    route = PheromoneSubject("route", "route:alpha")

    assert topology_subject_candidate_id(candidate) == "candidate:alpha"
    assert topology_subject_candidate_id(route) == ""
    assert (
        topology_subject_target(
            PheromoneSubject("route", "route:alpha", "candidate:alpha"),
            pheromone_fixture.candidates(),
        )
        == pheromone_fixture.TARGET
    )
    assert topology_subject_target(route, None) == ""

    with pytest.raises(GovernanceError, match="has no candidate binding"):
        validate_pheromone_subject_binding(
            PheromoneNeighborhood(subjects=[route]),
            subject_type="route",
            subject_id="route:alpha",
            candidate_id="candidate:alpha",
            require_declared=True,
        )
    validate_pheromone_subject_binding(
        _valid_topology(),
        subject_type="tool",
        subject_id="tool:optional",
        candidate_id="candidate:alpha",
        require_declared=False,
    )


def test_pheromone_topology_without_candidate_catalog_rejects_target_mismatch() -> None:
    subject = PheromoneSubject(
        "route",
        "route:alpha",
        "candidate:alpha",
        "decision:other",
    )
    with pytest.raises(GovernanceError, match="not active target"):
        validate_pheromone_topology(
            PheromoneNeighborhood(subjects=[subject]),
            candidate_set=None,
            target=pheromone_fixture.TARGET,
        )


def _strategy_bias(**changes: object) -> StrategyBias:
    values: dict[str, object] = {
        "layer_id": "evolutionary",
        "candidate_id": "candidate:alpha",
        "support": 0.5,
        "provenance": "runtime:evolutionary",
        "trace_event_id": "trace:bias:alpha",
        "target": pheromone_fixture.TARGET,
        "source_id": "source:evolutionary",
        "confidence": 0.8,
        "evidence_id": "evidence:bias:alpha",
    }
    values.update(changes)
    return StrategyBias(**values)  # type: ignore[arg-type]


def test_layer_records_are_deepcopy_stable() -> None:
    proposal = pheromone_fixture.proposal("learned")
    policy = pheromone_fixture.layer_policy()

    assert deepcopy(proposal) is proposal
    assert deepcopy(policy) is policy


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"enabled": 1}, "enabled must be boolean"),
        (
            {"fallback_on_unresolved_conflict": 1},
            "fallback_on_unresolved_conflict must be boolean",
        ),
        ({"conflict_threshold": 1.1}, "thresholds must be between 0 and 1"),
        ({"emergency_override_threshold": -0.1}, "thresholds must be between"),
        ({"min_layer_provenance": True}, "must be a positive integer"),
        ({"min_layer_provenance": 0}, "must be a positive integer"),
        (
            {"enabled": True, "fallback_on_unresolved_conflict": False},
            "must fall back",
        ),
        ({"max_strategy_bias": 11.0}, "outside absolute bounds"),
        ({"default_layer_weights": {"foreign": 1.0}}, "unsupported layer id"),
        ({"default_layer_weights": {"learned": -0.1}}, "must be non-negative"),
        (
            {"confidence_thresholds": {"learned": 1.1}},
            "must not exceed 1",
        ),
        ({"layer_weight_bounds": {"foreign": (0.0, 1.0)}}, "unsupported layer id"),
        (
            {"layer_weight_bounds": {"learned": (0.0,)}},
            "must contain two values",
        ),
        (
            {"layer_weight_bounds": {"learned": (2.0, 1.0)}},
            "weight bounds are invalid",
        ),
        (
            {
                "layer_weight_bounds": {"learned": (0.0, 1.0)},
                "default_layer_weights": {"learned": 1.5},
            },
            "default weight is outside",
        ),
    ),
)
def test_layer_policy_rejects_invalid_public_declarations(
    changes: dict[str, object],
    fragment: str,
) -> None:
    with pytest.raises(GovernanceError, match=fragment):
        validate_layer_coordination_policy(
            replace(pheromone_fixture.layer_policy(), **changes)
        )


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"layer_id": 1}, "layer_id must be a string"),
        ({"layer_id": "foreign"}, "unsupported layer id"),
        ({"source_id": " "}, "source_id is required"),
        ({"target": "decision:other"}, "not active target"),
        ({"action": "foreign"}, "unsupported layer action"),
        ({"candidate_id": ""}, "requires a candidate"),
        ({"confidence": 1.1}, "must be between 0 and 1"),
        ({"support": 11.0}, "outside absolute bounds"),
        (
            {"proposed_pheromone_kind": "foreign"},
            "unsupported proposed pheromone kind",
        ),
        (
            {
                "action": "propose_pheromone",
                "proposed_pheromone_kind": "positive",
                "proposed_strength": 1.0,
                "metadata": {"subject_type": 1},
            },
            "subject binding is invalid",
        ),
        (
            {
                "action": "propose_pheromone",
                "proposed_pheromone_kind": "positive",
                "proposed_strength": 1.0,
                "metadata": {"subject_type": "foreign", "subject_id": "route:a"},
            },
            "subject type is unsupported",
        ),
        (
            {
                "action": "propose_pheromone",
                "proposed_pheromone_kind": "positive",
                "proposed_strength": 1.0,
                "metadata": {
                    "subject_type": "candidate",
                    "subject_id": "candidate:beta",
                },
            },
            "subject must match candidate_id",
        ),
        (
            {"proposed_pheromone_kind": "positive", "proposed_strength": 1.0},
            "fields require propose_pheromone",
        ),
        (
            {
                "layer_id": "learned",
                "action": "propose_pheromone",
                "proposed_pheromone_kind": "alarm",
                "proposed_strength": 1.0,
            },
            "reactive layer may propose emergency",
        ),
        ({"action": "alarm", "layer_id": "learned"}, "reactive layer"),
        (
            {"action": "alarm", "proposed_pheromone_kind": "cautionary"},
            "kind must match",
        ),
        (
            {"action": "resolve_conflict", "layer_id": "learned"},
            "metacognitive layer",
        ),
        ({"provenance": ""}, "missing provenance"),
        ({"trace_event_id": ""}, "missing trace event id"),
    ),
)
def test_layer_proposal_rejects_invalid_public_semantics(
    changes: dict[str, object],
    fragment: str,
) -> None:
    base = pheromone_fixture.proposal("reactive")
    with pytest.raises(GovernanceError, match=fragment):
        validate_layer_proposal(
            replace(base, **changes),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_layer_proposal_collection_rejects_duplicate_identity_and_lineage() -> None:
    first = pheromone_fixture.proposal("learned")
    duplicate_lineage = replace(
        first,
        candidate_id="candidate:beta",
        trace_event_id=first.trace_event_id,
    )
    with pytest.raises(GovernanceError, match="duplicate layer proposal trace"):
        validate_layer_proposals(
            [first, duplicate_lineage],
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )

    duplicate_identity = replace(first, trace_event_id="trace:other")
    with pytest.raises(GovernanceError, match="duplicate equivalent"):
        validate_layer_proposals(
            [first, duplicate_identity],
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_layer_action_effect_covers_extension_threshold_and_unknown_action() -> None:
    policy = pheromone_fixture.layer_policy()
    assert (
        layer_action_effect(
            replace(pheromone_fixture.proposal("learned"), action="x-observe"),
            policy,
        )
        == "metadata_only"
    )
    assert (
        layer_action_effect(
            replace(pheromone_fixture.proposal("learned"), confidence=0.1),
            policy,
        )
        == "support_below_confidence_threshold"
    )
    with pytest.raises(GovernanceError, match="no governance semantics"):
        layer_action_effect(
            replace(pheromone_fixture.proposal("learned"), action="foreign"),
            policy,
        )


def test_layer_pheromone_materialization_rejects_invalid_step_and_zero_effect() -> None:
    proposal = replace(
        pheromone_fixture.proposal("learned", action="propose_pheromone"),
        confidence=0.0,
        proposed_pheromone_kind="positive",
        proposed_strength=1.0,
    )
    with pytest.raises(GovernanceError, match="step must be a non-negative"):
        materialize_layer_pheromone_proposals(
            proposals=[],
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            current_step=True,  # type: ignore[arg-type]
            policy=pheromone_fixture.layer_policy(),
        )
    with pytest.raises(GovernanceError, match="strength must be finite and positive"):
        materialize_layer_pheromone_proposals(
            proposals=[proposal],
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            current_step=0,
            policy=pheromone_fixture.layer_policy(
                confidence_thresholds={
                    layer: 0.0
                    for layer in (
                        "reactive",
                        "learned",
                        "evolutionary",
                        "metacognitive",
                    )
                }
            ),
        )
    assert (
        materialize_layer_pheromone_proposals(
            proposals=[replace(proposal, confidence=0.1)],
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            current_step=0,
            policy=pheromone_fixture.layer_policy(),
        )
        == ()
    )


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"layer_id": 1}, "layer_id must be a string"),
        ({"layer_id": "learned"}, "only be proposed by the evolutionary"),
        ({"source_id": ""}, "source_id is required"),
        ({"target": "decision:other"}, "not active target"),
        ({"support": 2.0}, "outside declared bounds"),
        ({"provenance": ""}, "missing provenance"),
        ({"evidence_id": ""}, "missing evidence"),
        ({"trace_event_id": ""}, "missing trace event id"),
    ),
)
def test_strategy_bias_rejects_invalid_public_semantics(
    changes: dict[str, object],
    fragment: str,
) -> None:
    with pytest.raises(GovernanceError, match=fragment):
        validate_strategy_bias(
            _strategy_bias(**changes),
            pheromone_fixture.layer_policy(),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_strategy_bias_collection_rejects_duplicate_identity_and_lineage() -> None:
    first = _strategy_bias()
    duplicate_lineage = _strategy_bias(
        candidate_id="candidate:beta",
        trace_event_id=first.trace_event_id,
    )
    with pytest.raises(GovernanceError, match="duplicate StrategyBias trace"):
        validate_strategy_biases(
            [first, duplicate_lineage],
            pheromone_fixture.layer_policy(),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )
    duplicate_identity = _strategy_bias(trace_event_id="trace:bias:other")
    with pytest.raises(GovernanceError, match="duplicate equivalent StrategyBias"):
        validate_strategy_biases(
            [first, duplicate_identity],
            pheromone_fixture.layer_policy(),
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
        )


def test_layer_snapshot_validation_and_confidence_reject_invalid_inputs() -> None:
    with pytest.raises(GovernanceError, match="unsupported layer snapshot"):
        validate_layer_performance_snapshots(
            [LayerPerformanceSnapshot(layer_id="foreign")]
        )
    with pytest.raises(GovernanceError, match="must be between 0 and 1"):
        validate_layer_performance_snapshots(
            [
                LayerPerformanceSnapshot(
                    layer_id="learned",
                    recent_success_rate=1.1,
                )
            ]
        )
    snapshot = LayerPerformanceSnapshot(layer_id="learned")
    with pytest.raises(GovernanceError, match="duplicate layer performance"):
        validate_layer_performance_snapshots([snapshot, snapshot])
    with pytest.raises(GovernanceError, match="unsupported layer id"):
        assess_layer_confidences(
            [replace(pheromone_fixture.proposal("learned"), layer_id="foreign")]
        )


def test_layer_conflict_and_weight_public_paths_cover_emergency_interactions() -> None:
    policy = pheromone_fixture.layer_policy()
    proposals = [
        pheromone_fixture.proposal(
            "reactive",
            action="alarm",
            risk=1.0,
            support=0.0,
        ),
        pheromone_fixture.proposal("learned"),
    ]

    assert "reactive_emergency_exploitation_conflict" in detect_layer_conflicts(
        proposals,
        policy,
    )
    assert "positive_alarm_conflict" in detect_layer_conflicts(
        [proposals[0], replace(proposals[1], candidate_id="candidate:alpha")],
        policy,
    )
    assert "candidate_support_conflict" not in detect_layer_conflicts(
        [
            pheromone_fixture.proposal("learned", confidence=1.0),
            pheromone_fixture.proposal(
                "evolutionary",
                candidate_id="candidate:beta",
                confidence=0.5,
            ),
        ],
        policy,
    )
    assert "positive_alarm_conflict" not in detect_layer_conflicts(
        [
            proposals[0],
            pheromone_fixture.proposal(
                "metacognitive",
                candidate_id="candidate:beta",
            ),
        ],
        policy,
    )
    weights = allocate_layer_weights(
        policy,
        [
            LayerPerformanceSnapshot(
                layer_id="reactive",
                recent_success_rate=1.0,
                mean_confidence=1.0,
            )
        ],
        active_emergency=True,
    )
    assert weights["reactive"] >= 1.0


def test_layer_score_deltas_fail_closed_for_negative_or_overflowing_weights() -> None:
    proposal = pheromone_fixture.proposal("learned")
    policy = pheromone_fixture.layer_policy()
    with pytest.raises(GovernanceError, match="weight must be non-negative"):
        proposal_score_delta(proposal, policy, -1.0)
    with pytest.raises(GovernanceError, match="score must remain finite"):
        proposal_score_delta(
            replace(proposal, support=1e308),
            policy,
            1e308,
        )
    assert proposal_score_delta(replace(proposal, confidence=0.1), policy, 1.0) == 0
    bias = _strategy_bias()
    with pytest.raises(GovernanceError, match="weight must be non-negative"):
        strategy_bias_score_delta(bias, policy, -1.0)
    with pytest.raises(GovernanceError, match="score must remain finite"):
        strategy_bias_score_delta(
            replace(bias, support=1e308),
            policy,
            1e308,
        )


def test_layer_coordination_rejects_unsafe_fallback_and_duplicate_lineage() -> None:
    policy = pheromone_fixture.layer_policy()
    with pytest.raises(GovernanceError, match="fallback candidate is not marked safe"):
        evaluate_layer_coordination(
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            policy=policy,
            proposals=[],
            fallback_candidate_id="candidate:alpha",
        )
    assert (
        evaluate_layer_coordination(
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            policy=replace(policy, enabled=False),
            proposals=[],
            fallback_candidate_id="candidate:fallback",
        ).resolution
        == "disabled"
    )
    proposal = pheromone_fixture.proposal("learned")
    with pytest.raises(GovernanceError, match="duplicate layer lineage"):
        evaluate_layer_coordination(
            candidate_set=pheromone_fixture.candidates(),
            target=pheromone_fixture.TARGET,
            policy=policy,
            proposals=[proposal],
            strategy_biases=[_strategy_bias(trace_event_id=proposal.trace_event_id)],
            fallback_candidate_id="candidate:fallback",
        )
    zero_bias = evaluate_layer_coordination(
        candidate_set=pheromone_fixture.candidates(),
        target=pheromone_fixture.TARGET,
        policy=policy,
        proposals=[],
        strategy_biases=[_strategy_bias(support=0.0)],
        fallback_candidate_id="candidate:fallback",
    )
    assert zero_bias.fallback_used is True


def _verify_observation_raw(
    attestation: object,
    **changes: object,
):
    principal_id = (
        attestation.principal_id
        if isinstance(attestation, observation_fixture.ObservationAttestation)
        else "principal:test"
    )
    values: dict[str, object] = {
        "attestation": attestation,
        "profile": observation_fixture.PROFILE,
        "assurance": observation_fixture.ASSURANCE,
        "manifest_root": observation_fixture.MANIFEST_ROOT,
        "commit_policy_root": observation_fixture.COMMIT_POLICY_ROOT,
        "protocol_id": observation_fixture.PROTOCOL_ID,
        "run_id": observation_fixture.RUN_ID,
        "target": observation_fixture.TARGET,
        "candidate_id": observation_fixture.CANDIDATE,
        "claim_fingerprint": observation_fixture.CLAIM_ROOT,
        "epoch": observation_fixture.EPOCH,
        "principal_verification": observation_fixture.principal_verification(
            principal_id
        ),
        "evidence_policy": observation_fixture.evidence_policy(),
        "quality_ppm": 1_000_000,
        "relevance_ppm": 1_000_000,
        "materiality_ppm": 0,
        "criticality_ppm": 0,
        "verifier_id": "governance:evidence",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 2,
        "verification_provenance": "urn:test:observation-verification",
        "verification_trace_event_id": "trace:verified:test",
        "prior_observations": (),
    }
    values.update(changes)
    return verify_observation_attestation(**values)  # type: ignore[arg-type]


def _counter_observation(
    label: str = "gap",
    *,
    expires_at_step: int = 20,
):
    return observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            f"observation:counter:{label}",
            principal_id=f"principal:counter:{label}",
            polarity=ObservationPolarity.CONTRADICT,
            group=f"group:counter:{label}",
            domain=f"domain:counter:{label}",
            materiality_ppm=1_000_000,
            criticality_ppm=1_000_000,
            expires_at_step=expires_at_step,
        )
    )


def _unresolved_disposition(label: str = "gap"):
    return observation_fixture.unresolved(_counter_observation(label))


def test_observation_public_payloads_require_canonical_record_types() -> None:
    with pytest.raises(GovernanceError, match="attestation must use the canonical"):
        observation_attestation_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="attestation must use the canonical"):
        _verify_observation_raw(object())
    with pytest.raises(GovernanceError, match="verified observation must use"):
        verified_observation_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="disposition must use"):
        counterevidence_disposition_payload(object())  # type: ignore[arg-type]

    assert verified_observation_is_authoritative(object()) is False
    assert counterevidence_disposition_is_authoritative(object()) is False


def test_observation_verification_rejects_relevance_and_principal_mismatch() -> None:
    attestation = observation_fixture.observation_attestation(
        "observation:gap:verification",
        principal_id="principal:gap:verification",
    )
    with pytest.raises(GovernanceError, match="relevance is below policy"):
        observation_fixture.verify_observation(attestation, relevance_ppm=99_999)
    with pytest.raises(GovernanceError, match="requires governance authority"):
        _verify_observation_raw(attestation, authority=AuthorityLevel.AGENT)
    with pytest.raises(GovernanceError, match="binding mismatch"):
        _verify_observation_raw(attestation, target="decision:other")
    with pytest.raises(GovernanceError, match="exceeds the declared TTL"):
        _verify_observation_raw(
            attestation,
            evidence_policy=observation_fixture.evidence_policy(
                observation_ttl_steps=1
            ),
        )
    with pytest.raises(GovernanceError, match="quality is below policy"):
        _verify_observation_raw(attestation, quality_ppm=99_999)
    with pytest.raises(GovernanceError, match="principal verification is not"):
        observation_fixture.verify_observation(
            attestation,
            principal=observation_fixture.principal_verification("principal:other"),
        )


def test_observation_exact_replay_is_idempotent_and_nonce_reuse_is_rejected() -> None:
    attestation = observation_fixture.observation_attestation(
        "observation:exact-replay",
        principal_id="principal:exact-replay",
    )
    first = _verify_observation_raw(attestation)
    assert (
        _verify_observation_raw(
            attestation,
            prior_observations=(first,),
        )
        is first
    )

    nonce_collision = observation_fixture.observation_attestation(
        "observation:nonce-replay",
        principal_id="principal:nonce-replay",
        nonce=attestation.nonce,
    )
    with pytest.raises(GovernanceError, match="nonce replay conflict"):
        _verify_observation_raw(
            nonce_collision,
            prior_observations=(first,),
        )

    object.__setattr__(
        first,
        "observation_id",
        _NonEqualText(attestation.observation_id),
    )
    object.__setattr__(first, "nonce", _NonEqualText(attestation.nonce))
    assert verified_observation_is_authoritative(first)
    fingerprint_collision = replace(
        attestation,
        observation_id=_NonEqualText(attestation.observation_id),
        nonce=_NonEqualText(attestation.nonce),
    )
    with pytest.raises(GovernanceError, match="attestation replay conflict"):
        _verify_observation_raw(
            fingerprint_collision,
            prior_observations=(first,),
        )


def test_observation_authority_readers_fail_closed_on_corruption() -> None:
    observation = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:gap:corrupt",
            principal_id="principal:gap:corrupt",
        )
    )
    object.__setattr__(observation, "polarity", object())

    assert verified_observation_is_authoritative(observation) is False
    with pytest.raises(GovernanceError, match="requires authoritative evidence"):
        observation_weight_ppm(observation)
    with pytest.raises(GovernanceError, match="requires authoritative evidence"):
        counterevidence_is_material_critical(observation)


def test_observation_matchers_reject_invalid_expected_coordinates() -> None:
    observation = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:gap:match",
            principal_id="principal:gap:match",
        )
    )
    common = {
        "profile": observation_fixture.PROFILE,
        "assurance": observation_fixture.ASSURANCE,
        "manifest_root": observation_fixture.MANIFEST_ROOT,
        "commit_policy_root": observation_fixture.COMMIT_POLICY_ROOT,
        "protocol_id": observation_fixture.PROTOCOL_ID,
        "run_id": observation_fixture.RUN_ID,
        "target": observation_fixture.TARGET,
        "candidate_id": observation_fixture.CANDIDATE,
        "claim_fingerprint": observation_fixture.CLAIM_ROOT,
        "epoch": observation_fixture.EPOCH,
        "current_step": 3,
    }
    assert (
        verified_observation_matches(
            observation,
            **common,
            polarity="support",  # type: ignore[arg-type]
        )
        is False
    )
    assert (
        verified_observation_matches(observation, **{**common, "profile": ""}) is False
    )

    disposition = _unresolved_disposition("match")
    assert (
        counterevidence_disposition_matches(
            disposition,
            _counter_observation("other"),
            current_step=-1,
        )
        is False
    )


def _issue_disposition(
    counter: object,
    **changes: object,
):
    values: dict[str, object] = {
        "counter_observation": counter,
        "disposition_id": "disposition:gap",
        "kind": CounterevidenceDispositionKind.UNRESOLVED,
        "rebuttal_observations": (),
        "resolution_ref": "",
        "reason_codes": ("pending",),
        "verifier_id": "governance:counterevidence",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 3,
        "provenance": "urn:test:counterevidence",
        "trace_event_id": "trace:counterevidence:gap",
    }
    values.update(changes)
    return issue_counterevidence_disposition(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("counter_factory", "changes", "fragment"),
    (
        (
            lambda: _counter_observation("kind"),
            {"kind": "unresolved"},
            "kind is invalid",
        ),
        (
            lambda: _counter_observation("authority"),
            {"authority": AuthorityLevel.AGENT},
            "requires governance authority",
        ),
        (lambda: object(), {}, "requires an authoritative observation"),
        (
            lambda: observation_fixture.verify_observation(
                observation_fixture.observation_attestation(
                    "observation:support:gap",
                    principal_id="principal:support:gap",
                )
            ),
            {},
            "requires contradict polarity",
        ),
        (
            lambda: _counter_observation("stale", expires_at_step=3),
            {"current_step": 3},
            "is not fresh",
        ),
        (
            lambda: _counter_observation("non-rebuttal"),
            {"rebuttal_observations": (object(),)},
            "only rebutted counterevidence",
        ),
        (
            lambda: _counter_observation("resolution"),
            {"resolution_ref": observation_fixture.RESOLUTION_ROOT},
            "cannot claim a governance resolution",
        ),
    ),
)
def test_counterevidence_disposition_rejects_invalid_public_requests(
    counter_factory,
    changes: dict[str, object],
    fragment: str,
) -> None:
    with pytest.raises(GovernanceError, match=fragment):
        _issue_disposition(counter_factory(), **changes)


def test_counterevidence_disposition_rejects_stale_rebuttal() -> None:
    counter = _counter_observation("stale-rebuttal")
    rebuttal = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:stale-rebuttal",
            principal_id="principal:stale-rebuttal",
            group="group:stale-rebuttal",
            domain="domain:stale-rebuttal",
            expires_at_step=3,
        )
    )
    with pytest.raises(GovernanceError, match="rebuttal observation is not"):
        _issue_disposition(
            counter,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(rebuttal,),
            resolution_ref=observation_fixture.RESOLUTION_ROOT,
            current_step=3,
        )


def test_counterevidence_rebuttals_require_mutual_independence() -> None:
    counter = _counter_observation("independence")
    same_group = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:rebuttal:same-group",
            principal_id="principal:rebuttal:same-group",
            group=counter.independence_group,
            domain="domain:rebuttal:independent",
        )
    )
    with pytest.raises(GovernanceError, match="requires an independent group"):
        _issue_disposition(
            counter,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(same_group,),
            resolution_ref=observation_fixture.RESOLUTION_ROOT,
        )

    pairwise = tuple(
        observation_fixture.verify_observation(
            observation_fixture.observation_attestation(
                f"observation:rebuttal:pairwise:{index}",
                principal_id=f"principal:rebuttal:pairwise:{index}",
                group="group:rebuttal:pairwise",
                domain="domain:rebuttal:pairwise",
            )
        )
        for index in range(2)
    )
    with pytest.raises(GovernanceError, match="must be pairwise independent"):
        _issue_disposition(
            counter,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=pairwise,
            resolution_ref=observation_fixture.RESOLUTION_ROOT,
        )


def test_rebutted_counterevidence_requires_rebuttal_observations() -> None:
    with pytest.raises(GovernanceError, match="requires independent rebuttal evidence"):
        _issue_disposition(
            _counter_observation("missing-rebuttal"),
            kind=CounterevidenceDispositionKind.REBUTTED,
            resolution_ref=observation_fixture.RESOLUTION_ROOT,
        )


def test_counterevidence_authority_reader_fails_closed_on_corruption() -> None:
    disposition = _unresolved_disposition("corrupt")
    object.__setattr__(disposition, "kind", object())
    assert counterevidence_disposition_is_authoritative(disposition) is False


def test_counterevidence_materiality_returns_false_for_support() -> None:
    support = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:support:materiality",
            principal_id="principal:support:materiality",
        )
    )
    assert counterevidence_is_material_critical(support) is False
    assert counterevidence_is_material_critical(
        _counter_observation("material-critical")
    )


def test_observation_record_constructors_reject_invalid_shape() -> None:
    attestation = observation_fixture.observation_attestation(
        "observation:shape",
        principal_id="principal:shape",
    )
    with pytest.raises(GovernanceError, match="polarity is invalid"):
        replace(attestation, polarity="support")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="expiry must be after"):
        replace(attestation, expires_at_step=attestation.observed_at_step)

    verified = observation_fixture.verify_observation(attestation)
    with pytest.raises(GovernanceError, match="polarity is invalid"):
        replace(verified, polarity="support")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="interval is invalid"):
        replace(verified, verified_at_step=0)
    with pytest.raises(GovernanceError, match="authority is invalid"):
        replace(verified, authority=AuthorityLevel.AGENT)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("kind", "unresolved", "kind is invalid"),
        (
            "kind",
            CounterevidenceDispositionKind.REBUTTED,
            "requires evidence and governance resolution",
        ),
        (
            "rebuttal_observation_fingerprints",
            (observation_fixture.PAYLOAD_ROOT, observation_fixture.CLAIM_ROOT),
            "not canonical",
        ),
        (
            "rebuttal_observation_fingerprints",
            (observation_fixture.PAYLOAD_ROOT,),
            "only rebutted counterevidence",
        ),
        (
            "resolution_ref",
            observation_fixture.RESOLUTION_ROOT,
            "cannot claim a governance resolution",
        ),
        ("expires_at_step", 3, "expiry must be after"),
        ("authority", AuthorityLevel.AGENT, "authority is invalid"),
    ),
)
def test_public_counterevidence_payload_rejects_corrupted_record(
    field: str,
    value: object,
    fragment: str,
) -> None:
    disposition = _unresolved_disposition("payload")
    object.__setattr__(disposition, field, value)
    if field == "expires_at_step":
        object.__setattr__(disposition, "issued_at_step", 3)
    with pytest.raises(GovernanceError, match=fragment):
        counterevidence_disposition_payload(disposition)


def test_observation_replay_rejects_malformed_history_and_id_collision() -> None:
    first_attestation = observation_fixture.observation_attestation(
        "observation:replay:first",
        principal_id="principal:replay:first",
    )
    first = observation_fixture.verify_observation(first_attestation)
    next_attestation = observation_fixture.observation_attestation(
        "observation:replay:next",
        principal_id="principal:replay:next",
    )

    with pytest.raises(GovernanceError, match="must be a sequence"):
        observation_fixture.verify_observation(
            next_attestation,
            prior="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="non-authoritative evidence"):
        observation_fixture.verify_observation(
            next_attestation,
            prior=(replace(first),),
        )
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        observation_fixture.verify_observation(
            next_attestation,
            prior=(first, first),
        )

    unrelated = observation_fixture.verify_observation(
        next_attestation,
        prior=(first,),
    )
    assert unrelated.observation_id == next_attestation.observation_id

    colliding_id = observation_fixture.observation_attestation(
        first.observation_id,
        principal_id="principal:replay:collision",
        nonce="nonce:replay:collision",
    )
    with pytest.raises(GovernanceError, match="observation_id replay conflict"):
        observation_fixture.verify_observation(colliding_id, prior=(first,))


@pytest.mark.parametrize(
    ("policy_changes", "raw_changes", "fragment"),
    (
        ({}, {"evidence_policy": object()}, "canonical evidence policy"),
        ({"numeric_scale": 999_999}, {}, "numeric scale is unsupported"),
        ({"observation_ttl_steps": 0}, {}, "must be positive"),
        ({"require_trace": False}, {}, "must require provenance and trace"),
        (
            {},
            {"profile": "pheroos-certified-commit-v1"},
            "profile/assurance mismatch",
        ),
    ),
)
def test_observation_verification_rejects_invalid_policy_contract(
    policy_changes: dict[str, object],
    raw_changes: dict[str, object],
    fragment: str,
) -> None:
    attestation = observation_fixture.observation_attestation(
        f"observation:policy:{fragment}",
        principal_id=f"principal:policy:{fragment}",
    )
    changes = dict(raw_changes)
    if "evidence_policy" not in changes:
        changes["evidence_policy"] = observation_fixture.evidence_policy(
            **policy_changes
        )
    with pytest.raises(GovernanceError, match=fragment):
        _verify_observation_raw(attestation, **changes)


def test_counterevidence_constructor_rejects_nonsequence_and_duplicate_rebuttals() -> (
    None
):
    disposition = _unresolved_disposition("canonical")
    with pytest.raises(GovernanceError, match="must be a sequence"):
        replace(
            disposition,
            rebuttal_observation_fingerprints="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        replace(
            disposition,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observation_fingerprints=(
                observation_fixture.PAYLOAD_ROOT,
                observation_fixture.PAYLOAD_ROOT,
            ),
            resolution_ref=observation_fixture.RESOLUTION_ROOT,
        )


def _verify_challenge_raw(
    attestation: object,
    **changes: object,
):
    principal_id = (
        attestation.principal_id
        if isinstance(attestation, observation_fixture.ChallengeAttestation)
        else "principal:challenge:test"
    )
    values: dict[str, object] = {
        "attestation": attestation,
        "profile": observation_fixture.PROFILE,
        "assurance": observation_fixture.ASSURANCE,
        "manifest_root": observation_fixture.MANIFEST_ROOT,
        "commit_policy_root": observation_fixture.COMMIT_POLICY_ROOT,
        "protocol_id": observation_fixture.PROTOCOL_ID,
        "run_id": observation_fixture.RUN_ID,
        "target": observation_fixture.TARGET,
        "candidate_id": observation_fixture.CANDIDATE,
        "claim_fingerprint": observation_fixture.CLAIM_ROOT,
        "epoch": observation_fixture.EPOCH,
        "principal_verification": observation_fixture.principal_verification(
            principal_id
        ),
        "declared_categories": ("edge_case", "falsification"),
        "maximum_ttl_steps": 20,
        "result_observations": (),
        "verifier_id": "governance:challenge",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 3,
        "verification_provenance": "urn:test:challenge-verification",
        "verification_trace_event_id": "trace:verified:challenge:test",
        "prior_challenges": (),
    }
    values.update(changes)
    return verify_challenge_attestation(**values)  # type: ignore[arg-type]


def _verified_challenge(label: str = "gap"):
    return observation_fixture.verify_challenge(
        observation_fixture.challenge_attestation(
            f"challenge:{label}",
            principal_id=f"principal:challenge:{label}",
            category="falsification",
        )
    )


def _evaluate_challenge_coverage(challenges: object):
    return evaluate_challenge_coverage(
        challenges,  # type: ignore[arg-type]
        required_categories=("falsification",),
        profile=observation_fixture.PROFILE,
        assurance=observation_fixture.ASSURANCE,
        manifest_root=observation_fixture.MANIFEST_ROOT,
        commit_policy_root=observation_fixture.COMMIT_POLICY_ROOT,
        protocol_id=observation_fixture.PROTOCOL_ID,
        run_id=observation_fixture.RUN_ID,
        target=observation_fixture.TARGET,
        candidate_id=observation_fixture.CANDIDATE,
        claim_fingerprint=observation_fixture.CLAIM_ROOT,
        epoch=observation_fixture.EPOCH,
        current_step=3,
    )


def test_challenge_coverage_rejects_inconsistent_declared_sets() -> None:
    with pytest.raises(GovernanceError, match="must be required categories"):
        ChallengeCoverage(
            required_categories=("required",),
            covered_categories=("foreign",),
            missing_categories=("required",),
            challenge_fingerprints=(),
        )
    with pytest.raises(GovernanceError, match="missing categories are invalid"):
        ChallengeCoverage(
            required_categories=("required",),
            covered_categories=(),
            missing_categories=(),
            challenge_fingerprints=(),
        )


def test_challenge_public_payloads_require_canonical_records() -> None:
    with pytest.raises(GovernanceError, match="attestation must use the canonical"):
        challenge_attestation_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="attestation must use the canonical"):
        _verify_challenge_raw(object())
    with pytest.raises(GovernanceError, match="verified challenge must use"):
        verified_challenge_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="coverage must use"):
        challenge_coverage_payload(object())  # type: ignore[arg-type]

    assert verified_challenge_is_authoritative(object()) is False


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"authority": AuthorityLevel.AGENT}, "requires governance authority"),
        ({"maximum_ttl_steps": 0}, "maximum_ttl_steps must be positive"),
        ({"target": "decision:other"}, "binding mismatch"),
        ({"maximum_ttl_steps": 1}, "exceeds the declared TTL"),
        (
            {
                "principal_verification": observation_fixture.principal_verification(
                    "principal:challenge:other"
                )
            },
            "principal verification is not",
        ),
        (
            {"profile": "pheroos-certified-commit-v1"},
            "profile/assurance mismatch",
        ),
    ),
)
def test_challenge_verification_rejects_invalid_public_contract(
    changes: dict[str, object],
    fragment: str,
) -> None:
    attestation = observation_fixture.challenge_attestation(
        f"challenge:contract:{fragment}",
        principal_id=f"principal:challenge:contract:{fragment}",
        category="falsification",
    )
    with pytest.raises(GovernanceError, match=fragment):
        _verify_challenge_raw(attestation, **changes)


def test_challenge_rejects_undeclared_category_and_result_leaf_substitution() -> None:
    undeclared = observation_fixture.challenge_attestation(
        "challenge:undeclared-category",
        principal_id="principal:challenge:undeclared-category",
        category="edge_case",
    )
    with pytest.raises(GovernanceError, match="category is not declared"):
        _verify_challenge_raw(
            undeclared,
            declared_categories=("falsification",),
        )

    first_counter = _counter_observation("challenge-result:first")
    second_counter = _counter_observation("challenge-result:second")
    found = observation_fixture.challenge_attestation(
        "challenge:result-substitution",
        principal_id="principal:challenge:result-substitution",
        category="falsification",
        result=ChallengeResult.COUNTEREVIDENCE_FOUND,
        result_observation_fingerprints=(
            observation_fixture.verified_observation_fingerprint(first_counter),
        ),
    )
    with pytest.raises(GovernanceError, match="do not match the attestation"):
        _verify_challenge_raw(
            found,
            result_observations=(second_counter,),
        )


def test_challenge_rejects_unbound_result_observation_and_nonce_reuse() -> None:
    support = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:challenge:support",
            principal_id="principal:challenge:support",
        )
    )
    attestation = observation_fixture.challenge_attestation(
        "challenge:result:support",
        principal_id="principal:challenge:result:support",
        category="falsification",
    )
    with pytest.raises(GovernanceError, match="result observation is not"):
        _verify_challenge_raw(attestation, result_observations=(support,))

    nonce = "nonce:challenge:shared"
    counter = observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            "observation:challenge:nonce",
            principal_id="principal:challenge:nonce",
            polarity=ObservationPolarity.CONTRADICT,
            nonce=nonce,
        )
    )
    found = observation_fixture.challenge_attestation(
        "challenge:result:nonce",
        principal_id="principal:challenge:result:nonce",
        category="falsification",
        result=ChallengeResult.COUNTEREVIDENCE_FOUND,
        result_observation_fingerprints=(
            observation_fixture.verified_observation_fingerprint(counter),
        ),
        nonce=nonce,
    )
    with pytest.raises(GovernanceError, match="cannot replay an observation nonce"):
        _verify_challenge_raw(found, result_observations=(counter,))


def test_challenge_authority_readers_fail_closed_on_corruption() -> None:
    challenge = _verified_challenge("corrupt")
    object.__setattr__(challenge, "result", object())
    assert verified_challenge_is_authoritative(challenge) is False
    assert (
        verified_challenge_matches(
            challenge,
            profile=observation_fixture.PROFILE,
            assurance=observation_fixture.ASSURANCE,
            manifest_root=observation_fixture.MANIFEST_ROOT,
            commit_policy_root=observation_fixture.COMMIT_POLICY_ROOT,
            protocol_id=observation_fixture.PROTOCOL_ID,
            run_id=observation_fixture.RUN_ID,
            target=observation_fixture.TARGET,
            candidate_id=observation_fixture.CANDIDATE,
            claim_fingerprint=observation_fixture.CLAIM_ROOT,
            epoch=observation_fixture.EPOCH,
            current_step=-1,
        )
        is False
    )


def test_challenge_coverage_rejects_invalid_or_replayed_input() -> None:
    challenge = _verified_challenge("coverage")
    with pytest.raises(GovernanceError, match="non-authoritative"):
        _evaluate_challenge_coverage((replace(challenge),))
    with pytest.raises(GovernanceError, match="contains a replay"):
        _evaluate_challenge_coverage((challenge, challenge))
    coverage = _evaluate_challenge_coverage((challenge,))
    assert challenge_coverage_payload(coverage)["complete"] is True
    assert challenge_coverage_fingerprint(
        coverage,
        profile=observation_fixture.PROFILE,
    ).startswith("sha256:")


def test_challenge_coverage_rejects_execution_reuse_and_iterates_unique_inputs() -> (
    None
):
    first_attestation = observation_fixture.challenge_attestation(
        "challenge:coverage:execution:first",
        principal_id="principal:challenge:coverage:execution:first",
        category="falsification",
    )
    second_attestation = observation_fixture.challenge_attestation(
        "challenge:coverage:execution:second",
        principal_id="principal:challenge:coverage:execution:second",
        category="edge_case",
        execution_attestation_ref=first_attestation.execution_attestation_ref,
        execution_fingerprint=first_attestation.execution_fingerprint,
    )
    first = observation_fixture.verify_challenge(first_attestation)
    second = observation_fixture.verify_challenge(second_attestation)
    with pytest.raises(GovernanceError, match="cannot reuse one execution"):
        _evaluate_challenge_coverage((first, second))

    unique = (
        observation_fixture.verify_challenge(
            observation_fixture.challenge_attestation(
                "challenge:coverage-unique:edge",
                principal_id="principal:challenge:coverage-unique:edge",
                category="edge_case",
            )
        ),
        _verified_challenge("coverage-unique:falsification"),
    )
    coverage = _evaluate_challenge_coverage(unique)
    assert len(coverage.challenge_fingerprints) == 2


def test_challenge_coverage_rejects_forged_duplicate_fingerprint_totality() -> None:
    first = _verified_challenge("coverage-fingerprint-totality")
    second = replace(first)
    issuance = first._issuance
    assert isinstance(issuance, tuple)
    for field in (
        "challenge_id",
        "nonce",
        "execution_attestation_ref",
        "execution_fingerprint",
    ):
        object.__setattr__(
            second,
            field,
            _SplitHashText(getattr(first, field), field),
        )
    object.__setattr__(
        second,
        "_issuance",
        (issuance[0], verified_challenge_fingerprint(second)),
    )
    assert verified_challenge_is_authoritative(second)
    with pytest.raises(GovernanceError, match="duplicate evidence"):
        _evaluate_challenge_coverage((first, second))


def test_challenge_record_constructors_and_payload_reject_invalid_shape() -> None:
    attestation = observation_fixture.challenge_attestation(
        "challenge:shape",
        principal_id="principal:challenge:shape",
        category="falsification",
    )
    with pytest.raises(GovernanceError, match="result is invalid"):
        replace(attestation, result="inconclusive")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="reference observations"):
        replace(attestation, result=ChallengeResult.COUNTEREVIDENCE_FOUND)
    with pytest.raises(GovernanceError, match="cannot reference observations"):
        replace(
            attestation,
            result_observation_fingerprints=(observation_fixture.PAYLOAD_ROOT,),
        )
    with pytest.raises(GovernanceError, match="expiry must be after"):
        replace(attestation, expires_at_step=attestation.executed_at_step)
    object.__setattr__(
        attestation,
        "result_observation_fingerprints",
        (observation_fixture.PAYLOAD_ROOT, observation_fixture.CLAIM_ROOT),
    )
    with pytest.raises(GovernanceError, match="not canonical"):
        challenge_attestation_payload(attestation)

    challenge = _verified_challenge("shape")
    with pytest.raises(GovernanceError, match="result is invalid"):
        replace(challenge, result="inconclusive")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="requires observation evidence"):
        replace(challenge, result=ChallengeResult.COUNTEREVIDENCE_FOUND)
    with pytest.raises(GovernanceError, match="cannot reference observations"):
        replace(
            challenge,
            result_observation_fingerprints=(observation_fixture.PAYLOAD_ROOT,),
        )
    with pytest.raises(GovernanceError, match="interval is invalid"):
        replace(challenge, verified_at_step=0)
    with pytest.raises(GovernanceError, match="authority is invalid"):
        replace(challenge, authority=AuthorityLevel.AGENT)

    object.__setattr__(
        challenge,
        "result_observation_fingerprints",
        (observation_fixture.PAYLOAD_ROOT, observation_fixture.CLAIM_ROOT),
    )
    with pytest.raises(GovernanceError, match="not canonical"):
        verified_challenge_payload(challenge)


def test_challenge_replay_rejects_malformed_history_and_identity_collision() -> None:
    first = _verified_challenge("replay:first")
    next_attestation = observation_fixture.challenge_attestation(
        "challenge:replay:next",
        principal_id="principal:challenge:replay:next",
        category="falsification",
    )
    with pytest.raises(GovernanceError, match="must be a sequence"):
        observation_fixture.verify_challenge(
            next_attestation,
            prior="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="non-authoritative input"):
        observation_fixture.verify_challenge(
            next_attestation,
            prior=(replace(first),),
        )
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        observation_fixture.verify_challenge(
            next_attestation,
            prior=(first, first),
        )
    unrelated = observation_fixture.verify_challenge(
        next_attestation,
        prior=(first,),
    )
    assert unrelated.challenge_id == next_attestation.challenge_id

    same_id = observation_fixture.challenge_attestation(
        first.challenge_id,
        principal_id="principal:challenge:identity-collision",
        category="edge_case",
        nonce="nonce:challenge:identity-collision",
        execution_attestation_ref="opaque:execution:identity-collision",
        execution_fingerprint="sha256:" + ("8" * 64),
    )
    with pytest.raises(GovernanceError, match="identity replay"):
        observation_fixture.verify_challenge(same_id, prior=(first,))


def test_challenge_exact_replay_and_nonce_or_execution_collisions_are_distinct() -> (
    None
):
    attestation = observation_fixture.challenge_attestation(
        "challenge:replay:exact",
        principal_id="principal:challenge:replay:exact",
        category="falsification",
    )
    first = _verify_challenge_raw(attestation)
    assert (
        _verify_challenge_raw(
            attestation,
            prior_challenges=(first,),
        )
        is first
    )

    nonce_collision = observation_fixture.challenge_attestation(
        "challenge:replay:nonce",
        principal_id="principal:challenge:replay:nonce",
        category="falsification",
        nonce=attestation.nonce,
    )
    with pytest.raises(GovernanceError, match="nonce replay is a safety violation"):
        _verify_challenge_raw(
            nonce_collision,
            prior_challenges=(first,),
        )

    execution_collision = observation_fixture.challenge_attestation(
        "challenge:replay:execution",
        principal_id="principal:challenge:replay:execution",
        category="falsification",
        execution_attestation_ref=attestation.execution_attestation_ref,
        execution_fingerprint=attestation.execution_fingerprint,
    )
    with pytest.raises(
        GovernanceError,
        match="execution evidence replay is a safety violation",
    ):
        _verify_challenge_raw(
            execution_collision,
            prior_challenges=(first,),
        )


def test_challenge_canonical_collections_reject_string_empty_and_duplicates() -> None:
    attestation = observation_fixture.challenge_attestation(
        "challenge:canonical",
        principal_id="principal:challenge:canonical",
        category="falsification",
    )
    with pytest.raises(GovernanceError, match="must be a sequence"):
        replace(
            attestation,
            result_observation_fingerprints="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        replace(
            attestation,
            result=ChallengeResult.COUNTEREVIDENCE_FOUND,
            result_observation_fingerprints=(
                observation_fixture.PAYLOAD_ROOT,
                observation_fixture.PAYLOAD_ROOT,
            ),
        )
    with pytest.raises(GovernanceError, match="must be a sequence"):
        _verify_challenge_raw(attestation, declared_categories="bad")
    with pytest.raises(GovernanceError, match="must not be empty"):
        _verify_challenge_raw(attestation, declared_categories=())
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        _verify_challenge_raw(
            attestation,
            declared_categories=("falsification", "falsification"),
        )


def _positive_observation(
    label: str,
    *,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    expires_at_step: int = 20,
):
    return observation_fixture.verify_observation(
        observation_fixture.observation_attestation(
            f"observation:positive:{label}",
            principal_id=f"principal:positive:{label}",
            group=f"group:positive:{label}",
            domain=f"domain:positive:{label}",
            quality_ppm=quality_ppm,
            relevance_ppm=relevance_ppm,
            expires_at_step=expires_at_step,
        )
    )


def _bind_evidence_raw(
    positive: object = (),
    counters: object = (),
    dispositions: object = (),
    challenges: object = (),
    **changes: object,
):
    values: dict[str, object] = {
        "evidence_id": "evidence:gap",
        "profile": observation_fixture.PROFILE,
        "assurance": observation_fixture.ASSURANCE,
        "manifest_root": observation_fixture.MANIFEST_ROOT,
        "commit_policy_root": observation_fixture.COMMIT_POLICY_ROOT,
        "protocol_id": observation_fixture.PROTOCOL_ID,
        "run_id": observation_fixture.RUN_ID,
        "target": observation_fixture.TARGET,
        "candidate_id": observation_fixture.CANDIDATE,
        "claim_fingerprint": observation_fixture.CLAIM_ROOT,
        "epoch": observation_fixture.EPOCH,
        "positive_observations": positive,
        "counter_observations": counters,
        "dispositions": dispositions,
        "challenges": challenges,
        "issuer_id": "governance:evidence-binding",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 4,
        "provenance": "urn:test:evidence-binding",
        "trace_event_id": "trace:evidence-binding:gap",
    }
    values.update(changes)
    return bind_evidence(**values)  # type: ignore[arg-type]


def _evidence_evaluation_fixture(label: str = "gap"):
    positive = (
        _positive_observation(f"{label}:one"),
        _positive_observation(f"{label}:two"),
    )
    challenges = observation_fixture.complete_challenges()
    binding = observation_fixture.bind(
        positive,
        challenges=challenges,
        evidence_id=f"evidence:{label}",
    )
    policy = observation_fixture.evidence_policy()
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=positive,
        counter_observations=(),
        dispositions=(),
        challenges=challenges,
        evidence_policy=policy,
        current_step=5,
    )
    return positive, challenges, binding, policy, summary


def test_evidence_contribution_records_reject_invalid_arithmetic() -> None:
    with pytest.raises(GovernanceError, match="not correctly capped"):
        EvidenceGroupContribution(
            independence_group="group:test",
            observation_fingerprints=(observation_fixture.PAYLOAD_ROOT,),
            raw_contribution=10,
            group_cap=5,
            counted_contribution=10,
        )
    with pytest.raises(GovernanceError, match="floor must be positive"):
        SourceDomainContribution(
            source_domain="domain:test",
            observation_fingerprints=(observation_fixture.PAYLOAD_ROOT,),
            contribution=10,
            contribution_floor=0,
        )


def test_evidence_summary_constructor_rejects_inconsistent_derived_state() -> None:
    _, _, _, _, summary = _evidence_evaluation_fixture("summary-shape")
    with pytest.raises(GovernanceError, match="counter ratio exceeds scale"):
        replace(summary, counterevidence_ratio_ppm=1_000_001)
    with pytest.raises(GovernanceError, match="challenge coverage is invalid"):
        replace(summary, challenge_coverage=object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="source diversity is inconsistent"):
        replace(summary, source_diversity=summary.source_diversity + 1)


def test_evidence_binding_public_readers_require_canonical_records() -> None:
    with pytest.raises(GovernanceError, match="binding must use the canonical"):
        evidence_binding_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="binding must use the canonical"):
        rebuild_evidence_binding_roots(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="summary must use the canonical"):
        evidence_summary_payload(object())  # type: ignore[arg-type]
    assert evidence_binding_is_authoritative(object()) is False


def test_evidence_binding_rejects_authority_empty_inputs_and_profile_mismatch() -> None:
    positive = (_positive_observation("bind-authority"),)
    with pytest.raises(GovernanceError, match="requires governance authority"):
        _bind_evidence_raw(positive, authority=AuthorityLevel.AGENT)
    with pytest.raises(GovernanceError, match="requires at least one observation"):
        _bind_evidence_raw()
    with pytest.raises(GovernanceError, match="profile/assurance mismatch"):
        _bind_evidence_raw(
            positive,
            profile="pheroos-certified-commit-v1",
        )


def test_evidence_binding_matcher_and_authority_reader_fail_closed() -> None:
    positive = (_positive_observation("binding-reader"),)
    binding = observation_fixture.bind(positive)
    assert evidence_binding_matches(
        binding,
        profile=observation_fixture.PROFILE,
        assurance=observation_fixture.ASSURANCE,
        manifest_root=observation_fixture.MANIFEST_ROOT,
        commit_policy_root=observation_fixture.COMMIT_POLICY_ROOT,
        protocol_id=observation_fixture.PROTOCOL_ID,
        run_id=observation_fixture.RUN_ID,
        target=observation_fixture.TARGET,
        candidate_id=observation_fixture.CANDIDATE,
        claim_fingerprint=observation_fixture.CLAIM_ROOT,
        epoch=observation_fixture.EPOCH,
        current_step=4,
    )
    assert (
        evidence_binding_matches(
            binding,
            profile="",
            assurance=observation_fixture.ASSURANCE,
            manifest_root=observation_fixture.MANIFEST_ROOT,
            commit_policy_root=observation_fixture.COMMIT_POLICY_ROOT,
            protocol_id=observation_fixture.PROTOCOL_ID,
            run_id=observation_fixture.RUN_ID,
            target=observation_fixture.TARGET,
            candidate_id=observation_fixture.CANDIDATE,
            claim_fingerprint=observation_fixture.CLAIM_ROOT,
            epoch=observation_fixture.EPOCH,
            current_step=4,
        )
        is False
    )
    object.__setattr__(binding, "authority", object())
    assert evidence_binding_is_authoritative(binding) is False


def test_evidence_evaluation_rejects_non_authority_freshness_and_policy_floors() -> (
    None
):
    positive, challenges, binding, policy, _ = _evidence_evaluation_fixture(
        "evaluation-guards"
    )
    with pytest.raises(GovernanceError, match="requires an authoritative binding"):
        evaluate_evidence_binding(
            replace(binding),
            positive_observations=positive,
            counter_observations=(),
            dispositions=(),
            challenges=challenges,
            evidence_policy=policy,
            current_step=5,
        )
    with pytest.raises(GovernanceError, match="binding is not fresh"):
        evaluate_evidence_binding(
            binding,
            positive_observations=positive,
            counter_observations=(),
            dispositions=(),
            challenges=challenges,
            evidence_policy=policy,
            current_step=binding.expires_at_step,
        )

    low_quality = (_positive_observation("low-quality", quality_ppm=100_000),)
    low_binding = observation_fixture.bind(low_quality)
    with pytest.raises(GovernanceError, match="below the quality floor"):
        evaluate_evidence_binding(
            low_binding,
            positive_observations=low_quality,
            counter_observations=(),
            dispositions=(),
            challenges=(),
            evidence_policy=observation_fixture.evidence_policy(
                minimum_quality_ppm=200_000,
            ),
            current_step=5,
        )
    low_relevance = (_positive_observation("low-relevance", relevance_ppm=100_000),)
    relevance_binding = observation_fixture.bind(low_relevance)
    with pytest.raises(GovernanceError, match="below the relevance floor"):
        evaluate_evidence_binding(
            relevance_binding,
            positive_observations=low_relevance,
            counter_observations=(),
            dispositions=(),
            challenges=(),
            evidence_policy=observation_fixture.evidence_policy(
                minimum_relevance_ppm=200_000,
            ),
            current_step=5,
        )
    long_lived = (_positive_observation("long-lived", expires_at_step=20),)
    ttl_binding = observation_fixture.bind(long_lived)
    with pytest.raises(GovernanceError, match="observation beyond the policy TTL"):
        evaluate_evidence_binding(
            ttl_binding,
            positive_observations=long_lived,
            counter_observations=(),
            dispositions=(),
            challenges=(),
            evidence_policy=observation_fixture.evidence_policy(
                observation_ttl_steps=10,
            ),
            current_step=5,
        )

    short_positive = (_positive_observation("challenge-ttl", expires_at_step=10),)
    long_challenge = observation_fixture.verify_challenge(
        observation_fixture.challenge_attestation(
            "challenge:evidence-ttl",
            principal_id="principal:challenge:evidence-ttl",
            category="falsification",
            expires_at_step=20,
        )
    )
    challenge_binding = observation_fixture.bind(
        short_positive,
        challenges=(long_challenge,),
        evidence_id="evidence:challenge-ttl",
    )
    with pytest.raises(GovernanceError, match="challenge beyond the policy TTL"):
        evaluate_evidence_binding(
            challenge_binding,
            positive_observations=short_positive,
            counter_observations=(),
            dispositions=(),
            challenges=(long_challenge,),
            evidence_policy=observation_fixture.evidence_policy(
                observation_ttl_steps=10,
            ),
            current_step=5,
        )


def test_evidence_evaluation_rejects_substituted_valid_leaves() -> None:
    first = (_positive_observation("root:first"),)
    second = (_positive_observation("root:second"),)
    binding = observation_fixture.bind(first)
    with pytest.raises(GovernanceError, match="leaves or roots do not reconstruct"):
        evaluate_evidence_binding(
            binding,
            positive_observations=second,
            counter_observations=(),
            dispositions=(),
            challenges=(),
            evidence_policy=observation_fixture.evidence_policy(),
            current_step=5,
        )


def test_evidence_evaluation_classifies_resolved_counterevidence() -> None:
    positive = (_positive_observation("resolved-positive"),)
    counter = _counter_observation("resolved-counter")
    disposition = _issue_disposition(
        counter,
        disposition_id="disposition:resolved-counter",
        kind=CounterevidenceDispositionKind.IMMATERIAL,
        resolution_ref=observation_fixture.RESOLUTION_ROOT,
        trace_event_id="trace:disposition:resolved-counter",
    )
    binding = observation_fixture.bind(
        positive,
        counters=(counter,),
        dispositions=(disposition,),
    )
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=positive,
        counter_observations=(counter,),
        dispositions=(disposition,),
        challenges=(),
        evidence_policy=observation_fixture.evidence_policy(),
        current_step=5,
    )
    assert summary.resolved_counter_observation_fingerprints == (
        observation_fixture.verified_observation_fingerprint(counter),
    )


def test_evidence_evaluation_classifies_active_critical_counterevidence() -> None:
    positive = (
        _positive_observation("active-positive:a"),
        _positive_observation("active-positive:b"),
    )
    counters = (
        _counter_observation("active-counter:c"),
        _counter_observation("active-counter:d"),
    )
    dispositions = tuple(observation_fixture.unresolved(item) for item in counters)
    binding = observation_fixture.bind(
        positive,
        counters=counters,
        dispositions=dispositions,
    )
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=positive,
        counter_observations=counters,
        dispositions=dispositions,
        challenges=(),
        evidence_policy=observation_fixture.evidence_policy(),
        current_step=5,
    )
    counter_roots = {
        observation_fixture.verified_observation_fingerprint(item) for item in counters
    }
    assert set(summary.active_counter_observation_fingerprints) == counter_roots
    assert (
        set(summary.blocking_critical_counter_observation_fingerprints) == counter_roots
    )


def test_binding_components_reject_invalid_observation_and_disposition_state() -> None:
    positive = _positive_observation("components-positive")
    counter = _counter_observation("components")
    disposition = observation_fixture.unresolved(counter)

    with pytest.raises(GovernanceError, match="observation is non-authoritative"):
        _bind_evidence_raw((replace(positive),))
    with pytest.raises(GovernanceError, match="contains a replay or duplicate"):
        _bind_evidence_raw((positive, positive))
    with pytest.raises(GovernanceError, match="disposition is not authoritative"):
        _bind_evidence_raw(
            (positive,),
            (counter,),
            (replace(disposition),),
        )
    with pytest.raises(GovernanceError, match="stale or references another counter"):
        _bind_evidence_raw(
            (positive,),
            (_counter_observation("components:other"),),
            (disposition,),
        )
    second = _issue_disposition(
        counter,
        disposition_id="disposition:components:second",
        trace_event_id="trace:disposition:components:second",
    )
    with pytest.raises(GovernanceError, match="multiple dispositions"):
        _bind_evidence_raw(
            (positive,),
            (counter,),
            (disposition, second),
        )
    with pytest.raises(GovernanceError, match="requires exactly one disposition"):
        _bind_evidence_raw((positive,), (counter,), ())


def test_binding_components_reject_forged_duplicate_fingerprint_totality() -> None:
    positive = (_positive_observation("fingerprint-positive"),)
    counter = _counter_observation("fingerprint-counter")
    first_disposition = observation_fixture.unresolved(counter)
    second_disposition = replace(first_disposition)
    disposition_issuance = first_disposition._issuance
    assert isinstance(disposition_issuance, tuple)
    object.__setattr__(
        second_disposition,
        "counter_observation_fingerprint",
        _SplitHashText(
            first_disposition.counter_observation_fingerprint,
            "counter-observation-fingerprint",
        ),
    )
    object.__setattr__(
        second_disposition,
        "_issuance",
        (
            disposition_issuance[0],
            counterevidence_disposition_fingerprint(second_disposition),
        ),
    )
    assert counterevidence_disposition_is_authoritative(second_disposition)
    with pytest.raises(GovernanceError, match="duplicate disposition"):
        _bind_evidence_raw(
            positive,
            (counter,),
            (first_disposition, second_disposition),
        )

    first_challenge = _verified_challenge("binding-fingerprint-totality")
    second_challenge = replace(first_challenge)
    challenge_issuance = first_challenge._issuance
    assert isinstance(challenge_issuance, tuple)
    for field in ("challenge_id", "nonce"):
        object.__setattr__(
            second_challenge,
            field,
            _SplitHashText(getattr(first_challenge, field), field),
        )
    object.__setattr__(
        second_challenge,
        "_issuance",
        (challenge_issuance[0], verified_challenge_fingerprint(second_challenge)),
    )
    assert verified_challenge_is_authoritative(second_challenge)
    with pytest.raises(GovernanceError, match="duplicate challenge"):
        _bind_evidence_raw(
            positive,
            challenges=(first_challenge, second_challenge),
        )


def test_binding_components_require_rebuttal_leaf_and_challenge_leaf_lineage() -> None:
    counter = _counter_observation("lineage")
    independent = _positive_observation("lineage:independent")
    other_positive = _positive_observation("lineage:other")
    rebutted = _issue_disposition(
        counter,
        disposition_id="disposition:lineage",
        kind=CounterevidenceDispositionKind.REBUTTED,
        rebuttal_observations=(independent,),
        resolution_ref=observation_fixture.RESOLUTION_ROOT,
        trace_event_id="trace:disposition:lineage",
    )
    with pytest.raises(GovernanceError, match="omits rebuttal evidence"):
        _bind_evidence_raw(
            (other_positive,),
            (counter,),
            (rebutted,),
        )

    found_attestation = observation_fixture.challenge_attestation(
        "challenge:lineage",
        principal_id="principal:challenge:lineage",
        category="falsification",
        result=ChallengeResult.COUNTEREVIDENCE_FOUND,
        result_observation_fingerprints=(
            observation_fixture.verified_observation_fingerprint(counter),
        ),
    )
    challenge = observation_fixture.verify_challenge(
        found_attestation,
        result_observations=(counter,),
    )
    with pytest.raises(GovernanceError, match="result is absent from counter leaves"):
        _bind_evidence_raw((other_positive,), challenges=(challenge,))
    with pytest.raises(GovernanceError, match="challenge replay"):
        _bind_evidence_raw(
            (other_positive,),
            (counter,),
            (observation_fixture.unresolved(counter),),
            challenges=(challenge, challenge),
        )
    with pytest.raises(GovernanceError, match="challenge is non-authoritative"):
        _bind_evidence_raw(
            (other_positive,),
            challenges=(replace(challenge),),
        )


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("binding_version", "foreign", "version is unsupported"),
        ("profile", "pheroos-certified-commit-v1", "profile/assurance mismatch"),
        (
            "positive_observation_fingerprints",
            (observation_fixture.PAYLOAD_ROOT, observation_fixture.CLAIM_ROOT),
            "is not canonical",
        ),
        ("positive_observation_fingerprints", (), "requires at least one observation"),
        (
            "counter_observation_fingerprints",
            (observation_fixture.PAYLOAD_ROOT,),
            "positive and counter evidence leaves overlap",
        ),
        ("expires_at_step", 4, "expiry must be after issuance"),
        ("authority", AuthorityLevel.AGENT, "authority is invalid"),
        ("evidence_root", observation_fixture.MANIFEST_ROOT, "not reconstructable"),
    ),
)
def test_public_evidence_binding_payload_rejects_corruption(
    field: str,
    value: object,
    fragment: str,
) -> None:
    positive = (_positive_observation(f"binding-corruption:{field}"),)
    binding = observation_fixture.bind(positive)
    object.__setattr__(binding, field, value)
    if field == "counter_observation_fingerprints":
        object.__setattr__(
            binding,
            "positive_observation_fingerprints",
            (observation_fixture.PAYLOAD_ROOT,),
        )
    with pytest.raises(GovernanceError, match=fragment):
        evidence_binding_payload(binding)


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"evidence_policy": object()}, "canonical evidence policy"),
        (
            {
                "evidence_policy": observation_fixture.evidence_policy(
                    numeric_scale=999_999
                )
            },
            "numeric scale is unsupported",
        ),
        (
            {
                "evidence_policy": observation_fixture.evidence_policy(
                    positive_group_cap=0
                )
            },
            "must be positive",
        ),
        (
            {
                "evidence_policy": observation_fixture.evidence_policy(
                    required_challenge_categories=[]
                )
            },
            "requires challenge categories",
        ),
        (
            {
                "evidence_policy": observation_fixture.evidence_policy(
                    required_challenge_categories=["edge_case", "edge_case"]
                )
            },
            "categories are duplicated",
        ),
        (
            {
                "evidence_policy": observation_fixture.evidence_policy(
                    require_trace=False
                )
            },
            "must require provenance and trace",
        ),
    ),
)
def test_evidence_evaluation_rejects_invalid_policy_contract(
    changes: dict[str, object],
    fragment: str,
) -> None:
    positive = (_positive_observation(f"policy:{fragment}"),)
    binding = observation_fixture.bind(positive)
    with pytest.raises(GovernanceError, match=fragment):
        evaluate_evidence_binding(
            binding,
            positive_observations=positive,
            counter_observations=(),
            dispositions=(),
            challenges=(),
            current_step=5,
            **changes,  # type: ignore[arg-type]
        )


def test_evidence_summary_collections_reject_invalid_and_duplicate_records() -> None:
    _, _, _, _, summary = _evidence_evaluation_fixture("summary-collections")
    group = summary.positive_groups[0]
    domain = summary.source_domains[0]
    with pytest.raises(GovernanceError, match="positive groups must be a sequence"):
        replace(summary, positive_groups="bad")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="contains an invalid contribution"):
        replace(summary, positive_groups=(object(),))  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="contains a duplicate group"):
        replace(summary, positive_groups=(group, group))
    with pytest.raises(GovernanceError, match="source domains must be a sequence"):
        replace(summary, source_domains="bad")  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="invalid contribution"):
        replace(summary, source_domains=(object(),))  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="domains contain a duplicate"):
        replace(summary, source_domains=(domain, domain))


def test_evidence_fingerprint_collections_reject_string_empty_and_duplicates() -> None:
    with pytest.raises(GovernanceError, match="must be a sequence"):
        EvidenceGroupContribution(
            independence_group="group:test",
            observation_fingerprints="bad",  # type: ignore[arg-type]
            raw_contribution=1,
            group_cap=1,
            counted_contribution=1,
        )
    with pytest.raises(GovernanceError, match="must not be empty"):
        EvidenceGroupContribution(
            independence_group="group:test",
            observation_fingerprints=(),
            raw_contribution=1,
            group_cap=1,
            counted_contribution=1,
        )
    with pytest.raises(GovernanceError, match="contains a duplicate"):
        EvidenceGroupContribution(
            independence_group="group:test",
            observation_fingerprints=(
                observation_fixture.PAYLOAD_ROOT,
                observation_fixture.PAYLOAD_ROOT,
            ),
            raw_contribution=1,
            group_cap=1,
            counted_contribution=1,
        )


def _attention_records():
    scenario = attention_fixture._scenario()
    return attention_fixture.evaluate_hybrid_attention_step(
        **attention_fixture._hybrid_inputs(scenario)
    )


def test_attention_public_derivation_rejects_non_authoritative_inputs() -> None:
    attention, _ = _attention_records()
    with pytest.raises(GovernanceError, match="cannot be overridden"):
        evaluate_hybrid_attention_step(attention_only=False)
    with pytest.raises(GovernanceError, match="governance-issued attention breakdown"):
        derive_exploration_directive(replace(attention))
    with pytest.raises(GovernanceError, match="governance-issued Hybrid step"):
        attention_fixture.derive_attention_breakdown(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="attention breakdown must be canonical"):
        attention_breakdown_payload(object())  # type: ignore[arg-type]
    with pytest.raises(
        GovernanceError, match="exploration directive must be canonical"
    ):
        exploration_directive_payload(object())  # type: ignore[arg-type]
    assert attention_breakdown_is_authoritative(object()) is False
    assert exploration_directive_is_authoritative(object()) is False


def test_attention_authority_reader_rejects_reissued_time_and_root_tampering() -> None:
    attention, _ = _attention_records()
    issuance_token = attention._issuance[0]
    object.__setattr__(attention, "current_step", attention.current_step + 1)
    object.__setattr__(
        attention,
        "_issuance",
        (issuance_token, attention_breakdown_fingerprint(attention)),
    )
    assert attention_breakdown_is_authoritative(attention) is False

    attention, _ = _attention_records()
    issuance_token = attention._issuance[0]
    object.__setattr__(attention, "attention_root", observation_fixture.MANIFEST_ROOT)
    object.__setattr__(
        attention,
        "_issuance",
        (issuance_token, attention_breakdown_fingerprint(attention)),
    )
    assert attention_breakdown_is_authoritative(attention) is False


def test_attention_defensive_step_checks_reject_missing_score_and_legacy_path() -> None:
    from pheroos.governance.attention import _hybrid_step_current_step

    with pytest.raises(GovernanceError, match="requires one pheromone_score"):
        _hybrid_step_current_step(SimpleNamespace(trace_events=()))

    scenario = attention_fixture._scenario()
    legacy = attention_fixture.evaluate_hybrid_collective_step(
        **attention_fixture._hybrid_inputs(scenario)
    )
    with pytest.raises(GovernanceError, match="legacy Hybrid decision path"):
        attention_fixture.derive_attention_breakdown(legacy)


def test_attention_directive_omits_scout_request_when_all_candidates_are_explored() -> (
    None
):
    scenario = attention_fixture._scenario()
    inputs = attention_fixture._hybrid_inputs(scenario)
    inputs["scout_reports"] = [
        attention_fixture.verified_scout(
            f"attention-scout:{candidate_id}",
            candidate_id,
            scenario.context.target,
        )
        for candidate_id in (
            "candidate:alpha",
            "candidate:beta",
            "candidate:fallback",
        )
    ]
    _, directive = attention_fixture.evaluate_hybrid_attention_step(**inputs)
    assert "independent_scout" not in directive.requested_verification_roles


def test_attention_authority_readers_fail_closed_on_tamper_and_shape_errors() -> None:
    attention, directive = _attention_records()
    assert attention_breakdown_is_authoritative(attention)
    assert exploration_directive_is_authoritative(directive, attention=attention)

    assert (
        exploration_directive_is_authoritative(
            replace(directive, directive_root=observation_fixture.MANIFEST_ROOT),
            attention=attention,
        )
        is False
    )
    object.__setattr__(attention, "candidate_priorities", (object(),))
    assert attention_breakdown_is_authoritative(attention) is False
    object.__setattr__(directive, "candidate_order", (object(),))
    assert exploration_directive_is_authoritative(directive) is False


def test_attention_authority_reader_binds_replay_and_source_roots() -> None:
    attention, _ = _attention_records()
    altered_scenario = attention_fixture._scenario()
    altered_inputs = attention_fixture._hybrid_inputs(altered_scenario)
    altered_inputs["deposits"] = [
        replace(altered_inputs["deposits"][0], strength=0.2),
        *altered_inputs["deposits"][1:],
    ]
    altered, _ = attention_fixture.evaluate_hybrid_attention_step(**altered_inputs)

    non_authoritative_replay = replace(altered.replay_state)
    object.__setattr__(attention, "replay_state", non_authoritative_replay)
    assert attention_breakdown_is_authoritative(attention) is False

    attention, _ = _attention_records()
    object.__setattr__(attention, "replay_state", altered.replay_state)
    assert attention_breakdown_is_authoritative(attention) is False

    attention, _ = _attention_records()
    object.__setattr__(attention, "source_step", altered.source_step)
    object.__setattr__(attention, "replay_state", altered.replay_state)
    assert attention_breakdown_is_authoritative(attention) is False


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("profile", "foreign", "profile is unsupported"),
        ("channel", "foreign", "channel is invalid"),
        ("authority_scope", "commit", "authority_scope must be none"),
        ("commit_authority", True, "never carry commit authority"),
        ("candidate_priorities", (), "requires candidate priorities"),
        ("candidate_priorities", (object(),), "priorities are not canonical"),
        ("subject_priorities", (object(),), "subject priorities are not canonical"),
        ("reopen_eligibility", (object(),), "reopen records are not canonical"),
        ("source_step", object(), "source step is not canonical"),
        ("replay_state", object(), "replay state is not canonical"),
        ("memory_root", "bad", "canonical sha256 fingerprint"),
    ),
)
def test_attention_breakdown_rejects_invalid_public_shape(
    field: str,
    value: object,
    fragment: str,
) -> None:
    attention, _ = _attention_records()
    with pytest.raises(GovernanceError, match=fragment):
        replace(attention, **{field: value})


def test_attention_breakdown_rejects_rank_gaps_and_duplicate_candidates() -> None:
    attention, _ = _attention_records()
    first, second, *rest = attention.candidate_priorities
    with pytest.raises(GovernanceError, match="ranks are not contiguous"):
        replace(
            attention,
            candidate_priorities=(
                first,
                replace(second, rank=second.rank + 1),
                *rest,
            ),
        )
    with pytest.raises(GovernanceError, match="priorities contain duplicates"):
        replace(
            attention,
            candidate_priorities=(
                first,
                replace(second, candidate_id=first.candidate_id),
                *rest,
            ),
        )


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("profile", "foreign", "profile is unsupported"),
        ("channel", "foreign", "channel is invalid"),
        ("authority_scope", "commit", "authority_scope must be none"),
        ("commit_authority", True, "cannot carry commit authority"),
        ("candidate_order", (), "candidate order is empty"),
        (
            "candidate_order",
            ("candidate:a", "candidate:a"),
            "candidate_order contains duplicates",
        ),
        ("route_priorities", (object(),), "priorities are not canonical"),
        ("tool_priorities", (object(),), "priorities are not canonical"),
        ("reopen_eligibility", (object(),), "reopen records are not canonical"),
        ("exploration_budget", -1.0, "budget must be non-negative"),
        ("directive_root", "bad", "canonical sha256 fingerprint"),
    ),
)
def test_exploration_directive_rejects_invalid_public_shape(
    field: str,
    value: object,
    fragment: str,
) -> None:
    _, directive = _attention_records()
    with pytest.raises(GovernanceError, match=fragment):
        replace(directive, **{field: value})


def test_exploration_directive_rejects_cross_typed_route_and_tool_priorities() -> None:
    _, directive = _attention_records()
    route_as_tool = AttentionSubjectPriority(
        candidate_id="candidate:alpha",
        subject_type="tool",
        subject_id="tool:test",
        kind="positive",
        pressure=1.0,
        source_count=1,
        trace_event_ids=("trace:tool:test",),
    )
    tool_as_route = replace(
        route_as_tool,
        subject_type="route",
        subject_id="route:test",
    )
    with pytest.raises(GovernanceError, match="route priorities contain"):
        replace(directive, route_priorities=(route_as_tool,))
    with pytest.raises(GovernanceError, match="tool priorities contain"):
        replace(directive, tool_priorities=(tool_as_route,))


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"candidate_id": " candidate"}, "nonblank canonical string"),
        ({"rank": 0}, "rank must be positive"),
        ({"attention_value": True}, "must be a finite number"),
        ({"attention_value": float("inf")}, "must be a finite number"),
        ({"independent_scout_count": True}, "must be a non-negative integer"),
        ({"recruitment_pressure": -1.0}, "must be non-negative"),
        ({"contribution_breakdown": (("score",),)}, "name/value pair"),
        (
            {"contribution_breakdown": (("score", 1.0), ("score", 2.0))},
            "names must be unique",
        ),
    ),
)
def test_attention_candidate_priority_rejects_invalid_values(
    changes: dict[str, object],
    fragment: str,
) -> None:
    attention, _ = _attention_records()
    with pytest.raises(GovernanceError, match=fragment):
        replace(attention.candidate_priorities[0], **changes)


def test_attention_subject_and_reopen_records_reject_invalid_values() -> None:
    with pytest.raises(GovernanceError, match="source_count must be positive"):
        AttentionSubjectPriority(
            candidate_id="candidate:alpha",
            subject_type="route",
            subject_id="route:test",
            kind="positive",
            pressure=1.0,
            source_count=0,
            trace_event_ids=("trace:test",),
        )
    with pytest.raises(GovernanceError, match="must be a sequence"):
        AttentionSubjectPriority(
            candidate_id="candidate:alpha",
            subject_type="route",
            subject_id="route:test",
            kind="positive",
            pressure=1.0,
            source_count=1,
            trace_event_ids="trace:test",  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="must not be empty"):
        AttentionSubjectPriority(
            candidate_id="candidate:alpha",
            subject_type="route",
            subject_id="route:test",
            kind="positive",
            pressure=1.0,
            source_count=1,
            trace_event_ids=(),
        )
    with pytest.raises(GovernanceError, match="contains duplicates"):
        AttentionSubjectPriority(
            candidate_id="candidate:alpha",
            subject_type="route",
            subject_id="route:test",
            kind="positive",
            pressure=1.0,
            source_count=1,
            trace_event_ids=("trace:test", "trace:test"),
        )
    with pytest.raises(GovernanceError, match="must be non-negative"):
        AttentionReopenEligibility(
            candidate_id="candidate:alpha",
            subject_type="route",
            subject_id="route:test",
            novelty_pressure=-1.0,
            reason="novelty",
            trace_event_id="trace:test",
        )


def test_attention_public_payloads_reject_corrupted_records() -> None:
    attention, directive = _attention_records()
    object.__setattr__(attention, "channel", "foreign")
    with pytest.raises(GovernanceError, match="channel is invalid"):
        attention_breakdown_payload(attention)
    object.__setattr__(directive, "channel", "foreign")
    with pytest.raises(GovernanceError, match="channel is invalid"):
        exploration_directive_payload(directive)
    _, duplicate_directive = _attention_records()
    object.__setattr__(
        duplicate_directive,
        "candidate_order",
        ("candidate:a", "candidate:a"),
    )
    with pytest.raises(GovernanceError, match="candidate order has duplicates"):
        exploration_directive_payload(duplicate_directive)


def _committed_atomic_result(label: str):
    _, _, store, prepared = atomic_fixture._prepared(label)
    result = commit_prepared_hybrid_transition(prepared, state_store=store)
    assert result.status is AtomicHybridCommitStatus.COMMITTED
    return store, prepared, result


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("version", "foreign", "version is unsupported"),
        ("batch", object(), "batch is invalid"),
        ("_evaluation", object(), "evaluation is invalid"),
        ("stream", "authority:other", "prepared stream is mismatched"),
        (
            "prepared_root",
            observation_fixture.MANIFEST_ROOT,
            "prepared root does not match",
        ),
    ),
)
def test_prepared_atomic_transition_rejects_invalid_public_shape(
    field: str,
    value: object,
    fragment: str,
) -> None:
    _, _, _, prepared = atomic_fixture._prepared(f"prepared-shape:{field}")
    with pytest.raises(GovernanceError, match=fragment):
        replace(prepared, **{field: value})


def test_atomic_record_serialization_exposes_only_portable_fields() -> None:
    _, prepared, result = _committed_atomic_result("serialization")
    assert prepared.to_dict()["prepared_root"] == prepared.prepared_root
    assert result.to_dict()["result_root"] == result.result_root


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"version": "foreign"}, "result version is unsupported"),
        ({"status": "committed"}, "result status is invalid"),
        ({"authoritative": 1}, "authoritative must be boolean"),
        ({"details": []}, "details must be a mapping"),
        ({"stream": ""}, "stream must be canonical non-blank text"),
        ({"scope_ref": "bad"}, "scope_ref must be a canonical SHA-256 digest"),
        ({"authoritative": False}, "authority flags are invalid"),
        ({"evaluation": None}, "requires evaluation and receipt"),
        (
            {"receipt_root": observation_fixture.MANIFEST_ROOT},
            "receipt root is mismatched",
        ),
        (
            {"evaluation_root": observation_fixture.MANIFEST_ROOT},
            "evaluation root is mismatched",
        ),
        ({"terminal": False}, "terminal flag is mismatched"),
        (
            {"decision_output_authorized": False},
            "output authority is mismatched",
        ),
        (
            {"result_root": observation_fixture.MANIFEST_ROOT},
            "result root does not match",
        ),
    ),
)
def test_committed_atomic_result_rejects_invalid_public_shape(
    changes: dict[str, object],
    fragment: str,
) -> None:
    _, _, result = _committed_atomic_result(f"committed-shape:{fragment}")
    with pytest.raises(GovernanceError, match=fragment):
        replace(result, **changes)


def _retry_atomic_result(label: str):
    evaluation, domain, store, first = atomic_fixture._prepared(label)
    stale = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=store.load_head(domain.scope_ref, first.stream),
        transition_id=f"stale:{label}",
    )
    commit_prepared_hybrid_transition(first, state_store=store)
    retry = commit_prepared_hybrid_transition(stale, state_store=store)
    assert retry.status is AtomicHybridCommitStatus.RETRY_REQUIRED
    return retry


@pytest.mark.parametrize(
    ("changes", "fragment"),
    (
        ({"authoritative": True}, "cannot carry decision authority"),
        ({"evaluation": object()}, "cannot expose evaluation or receipt"),
        ({"retry_required": False}, "retry-required Hybrid result flags are invalid"),
        (
            {"status": AtomicHybridCommitStatus.INVALID},
            "non-retry Hybrid result cannot request retry",
        ),
        (
            {
                "status": AtomicHybridCommitStatus.INVALID,
                "retry_required": False,
            },
            "terminal Hybrid diagnostic must be deliverable",
        ),
    ),
)
def test_uncommitted_atomic_result_rejects_invalid_public_shape(
    changes: dict[str, object],
    fragment: str,
) -> None:
    retry = _retry_atomic_result(f"retry-shape:{fragment}")
    with pytest.raises(GovernanceError, match=fragment):
        replace(retry, **changes)


def test_atomic_public_entrypoints_reject_invalid_contract_types() -> None:
    evaluation, domain, store, prepared = atomic_fixture._prepared("entrypoint-types")
    with pytest.raises(GovernanceError, match="stream requires a canonical"):
        hybrid_commit_stream(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="authoritative proposal"):
        prepare_hybrid_commit_transition(
            replace(evaluation),
            domain=domain,
            head=store.load_head(domain.scope_ref, prepared.stream),
        )
    with pytest.raises(GovernanceError, match="authority domain is invalid"):
        prepare_hybrid_commit_transition(
            evaluation,
            domain=object(),  # type: ignore[arg-type]
            head=store.load_head(domain.scope_ref, prepared.stream),
        )
    with pytest.raises(GovernanceError, match="requires a head"):
        prepare_hybrid_commit_transition(
            evaluation,
            domain=domain,
            head=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="head crosses scope or stream"):
        prepare_hybrid_commit_transition(
            evaluation,
            domain=domain,
            head=GovernanceHead.genesis(_OTHER_SCOPE, prepared.stream),
        )
    with pytest.raises(GovernanceError, match="prepared transition is invalid"):
        commit_prepared_hybrid_transition(
            object(),  # type: ignore[arg-type]
            state_store=store,
        )
    with pytest.raises(GovernanceError, match="StateStore is incompatible"):
        commit_prepared_hybrid_transition(
            prepared,
            state_store=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="prepared transition is invalid"):
        finalize_hybrid_commit_transition(
            object(),  # type: ignore[arg-type]
            receipt=object(),  # type: ignore[arg-type]
            state_store=store,
        )
    invalid_receipt = finalize_hybrid_commit_transition(
        prepared,
        receipt=object(),  # type: ignore[arg-type]
        state_store=store,
    )
    assert invalid_receipt.status is AtomicHybridCommitStatus.INVALID
    with pytest.raises(GovernanceError, match="StateStore is incompatible"):
        finalize_hybrid_commit_transition(
            prepared,
            receipt=GovernanceCommitReceipt(
                scope_ref=prepared.scope_ref,
                stream=prepared.stream,
                transition_id=prepared.transition_id,
                revision=1,
                parent_root=prepared.batch.transition.expected_state_root,
                state_root=prepared.batch.transition.state_root,
                trace_root=prepared.batch.trace_root,
                batch_root=prepared.batch.batch_root,
            ),
            state_store=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(GovernanceError, match="authority domain is invalid"):
        evaluate_and_commit_hybrid_step(
            object(),
            domain=object(),  # type: ignore[arg-type]
            state_store=store,
        )
    with pytest.raises(GovernanceError, match="StateStore is incompatible"):
        evaluate_and_commit_hybrid_step(
            object(),
            domain=domain,
            state_store=object(),  # type: ignore[arg-type]
        )


class _GovernanceErrorAtomicStore(atomic_fixture.InMemoryGovernanceStateStore):
    def atomic_commit(self, batch):
        del batch
        raise GovernanceError("storage backend unavailable")


class _AuthorityConflictAtomicStore(atomic_fixture.InMemoryGovernanceStateStore):
    def atomic_commit(self, batch):
        del batch
        raise GovernanceError("governance_transition_conflict")


class _CrashingAtomicStore(atomic_fixture.InMemoryGovernanceStateStore):
    def atomic_commit(self, batch):
        del batch
        raise RuntimeError("backend crashed")


class _UnreadableAtomicStore(atomic_fixture.InMemoryGovernanceStateStore):
    def load_receipt(self, scope_ref: str, transition_id: str):
        del scope_ref, transition_id
        raise RuntimeError("unreadable")


class _HeadUnavailableAtomicStore(atomic_fixture.InMemoryGovernanceStateStore):
    def load_head(self, scope_ref: str, stream: str):
        del scope_ref, stream
        raise RuntimeError("unavailable")


def test_atomic_store_failures_are_total_and_never_expose_authority() -> None:
    evaluation = atomic_fixture.evaluate_hybrid_commit_step(
        request=atomic_fixture._total_request(stable=True)
    )
    domain = AuthorityDomain(atomic_fixture._scope("governance-error-store"))
    store = _GovernanceErrorAtomicStore()
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=store.load_head(
            domain.scope_ref,
            hybrid_commit_stream(evaluation),
        ),
    )
    failed = commit_prepared_hybrid_transition(prepared, state_store=store)
    assert failed.status is AtomicHybridCommitStatus.FINALITY_UNAVAILABLE
    assert failed.authoritative is False

    authority_conflict = commit_prepared_hybrid_transition(
        prepared,
        state_store=_AuthorityConflictAtomicStore(),
    )
    assert authority_conflict.status is AtomicHybridCommitStatus.INVALID
    assert authority_conflict.reason_code == "governance_authority_conflict"

    crashed = commit_prepared_hybrid_transition(
        prepared,
        state_store=_CrashingAtomicStore(),
    )
    assert crashed.status is AtomicHybridCommitStatus.FINALITY_UNAVAILABLE
    assert crashed.reason_code == "governance_state_store_unavailable"

    _, _, committed = _committed_atomic_result("unreadable-finalization")
    unreadable = _UnreadableAtomicStore()
    unavailable = finalize_hybrid_commit_transition(
        prepared,
        receipt=committed.receipt,
        state_store=unreadable,
    )
    assert unavailable.status is AtomicHybridCommitStatus.FINALITY_UNAVAILABLE

    high_level = evaluate_and_commit_hybrid_step(
        atomic_fixture._total_request(stable=True),
        domain=AuthorityDomain(atomic_fixture._scope("head-unavailable")),
        state_store=_HeadUnavailableAtomicStore(),
    )
    assert high_level.status is AtomicHybridCommitStatus.FINALITY_UNAVAILABLE


def test_atomic_success_receipt_mismatch_and_trace_defense_paths() -> None:
    success = evaluate_and_commit_hybrid_step(
        atomic_fixture._total_request(stable=True),
        domain=AuthorityDomain(atomic_fixture._scope("high-level-success")),
        state_store=atomic_fixture.InMemoryGovernanceStateStore(),
    )
    assert success.status is AtomicHybridCommitStatus.COMMITTED

    store, prepared, committed = _committed_atomic_result("receipt-mismatch")
    assert committed.receipt is not None
    forged_receipt = replace(
        committed.receipt,
        state_root=_OTHER_ROOT,
        receipt_root="",
    )
    mismatch = finalize_hybrid_commit_transition(
        prepared,
        receipt=forged_receipt,
        state_store=store,
    )
    assert mismatch.status is AtomicHybridCommitStatus.INVALID
    assert mismatch.reason_code == "governance_receipt_mismatch"

    from pheroos.governance.atomic_evaluation import _scoped_trace_record

    with pytest.raises(GovernanceError, match="trace event is invalid"):
        _scoped_trace_record(
            object(),  # type: ignore[arg-type]
            scope_ref=_SCOPE,
            stream=_STREAM,
            transition_id=_TRANSITION_ID,
        )


def test_atomic_high_level_invalid_request_returns_diagnostic_without_authority() -> (
    None
):
    result = evaluate_and_commit_hybrid_step(
        object(),
        domain=AuthorityDomain(atomic_fixture._scope("invalid-request")),
        state_store=atomic_fixture.InMemoryGovernanceStateStore(),
    )
    assert result.status is AtomicHybridCommitStatus.INVALID
    assert result.authoritative is False
    assert result.stream.startswith("hybrid-commit-v1:")


def test_atomic_result_details_reject_nonportable_corruption() -> None:
    _, _, result = _committed_atomic_result("details-portability")
    with pytest.raises(GovernanceError, match="keys must be non-empty strings"):
        replace(result, details={1: "bad"})  # type: ignore[dict-item]
    with pytest.raises(GovernanceError, match="unsupported value type"):
        replace(result, details={"bad": object()})

    object.__setattr__(result, "details", {"values": [1, 2]})
    assert result.to_dict()["details"] == {"values": [1, 2]}
    object.__setattr__(result, "details", {"bad": object()})
    with pytest.raises(GovernanceError, match="unsupported value type"):
        result.to_dict()
