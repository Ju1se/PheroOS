from __future__ import annotations

"""Independent stdlib-only spec model for the declarative Commit TCK v2 slice.

This module deliberately does not import ``pheroos.governance``, the v1
reference adapter, or the v2 PheroOS subject adapter.  It models only the
normative operations declared by the checked v2 artifact.
"""

from copy import deepcopy
from hashlib import sha256
import json
import sys
from typing import Any

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest,
    CommitTckResponse,
    CommitTckV2ProtocolError,
    empty_commit_tck_actual,
    serve_commit_tck_v2_jsonl,
)


SPEC_MODEL_IMPLEMENTATION_ID = "pheroos-commit-spec-model-v2"
SPEC_MODEL_OPERATIONS = (
    "fixed_point_multiply",
    "fixed_point_ratio",
    "manifest_deadline_outcome",
    "manifest_threshold_assessment",
    "manifest_assurance_requirements",
    "manifest_distributed_quorum",
    "attention_truth_invariance",
    "certificate_leaf_binding",
    "trace_leaf_binding",
)
_MAX_AUTHORITY_INTEGER = (2**53) - 1
_TERMINAL_KINDS = {
    "invalid": "invalid",
    "safety_violation": "safety_violation",
    "blocked": "blocked",
    "evidence_commit_ready": "evidence_commit",
    "finality_unavailable": "finality_unavailable",
}


class IndependentCommitSpecModelAdapter:
    implementation_id = SPEC_MODEL_IMPLEMENTATION_ID

    def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
        operation = request.inputs["operation"]
        if operation == "fixed_point_multiply":
            left = _bounded_nonnegative_integer(request.inputs.get("left"), "left")
            right = _bounded_nonnegative_integer(
                request.inputs.get("right"),
                "right",
            )
            scale = _positive_scale(request.inputs.get("scale"))
            value = (left * right) // scale
            if value > _MAX_AUTHORITY_INTEGER:
                raise CommitTckV2ProtocolError("fixed-point product exceeds the bound")
            actual = empty_commit_tck_actual(metrics={"value": value})
        elif operation == "fixed_point_ratio":
            numerator = _nonnegative_integer(
                request.inputs.get("numerator"),
                "numerator",
            )
            denominator = _nonnegative_integer(
                request.inputs.get("denominator"),
                "denominator",
            )
            scale = _positive_scale(request.inputs.get("scale"))
            if denominator == 0:
                value = scale
            else:
                if numerator > denominator:
                    raise CommitTckV2ProtocolError(
                        "ratio numerator cannot exceed denominator"
                    )
                value = (numerator * scale) // denominator
            actual = empty_commit_tck_actual(metrics={"value": value})
        elif operation == "manifest_deadline_outcome":
            actual = _manifest_deadline_outcome(request)
        elif operation == "manifest_threshold_assessment":
            actual = _manifest_threshold_assessment(request)
        elif operation == "manifest_assurance_requirements":
            actual = _manifest_assurance_requirements(request)
        elif operation == "manifest_distributed_quorum":
            actual = _manifest_distributed_quorum(request)
        elif operation == "attention_truth_invariance":
            actual = _attention_truth_invariance(request)
        elif operation == "certificate_leaf_binding":
            actual = _certificate_leaf_binding(request)
        elif operation == "trace_leaf_binding":
            actual = _trace_leaf_binding(request)
        else:
            raise CommitTckV2ProtocolError(
                f"spec-model operation is unsupported: {operation!r}"
            )
        return CommitTckResponse(
            request_id=request.id,
            implementation_id=self.implementation_id,
            actual=actual,
        )


def _manifest_deadline_outcome(request: CommitTckRequest) -> dict[str, Any]:
    manifest = _object(request.manifest, "manifest")
    protocol = _object(manifest.get("protocol"), "manifest protocol")
    policy = _object(
        protocol.get("collective_commit_policy"),
        "manifest collective_commit_policy",
    )
    commit_window = _object(policy.get("commit_window"), "manifest commit_window")
    terminal = _object(policy.get("terminal_outcome"), "manifest terminal_outcome")
    run_deadline_steps = _positive_integer(
        commit_window.get("run_deadline_steps"),
        "run_deadline_steps",
    )
    deadline_outcome = terminal.get("deadline_outcome")
    if deadline_outcome not in {"safe_fallback", "advisory"}:
        raise CommitTckV2ProtocolError("deadline_outcome is unsupported")
    elapsed_steps = _nonnegative_integer(
        request.inputs.get("elapsed_steps"),
        "elapsed_steps",
    )
    conditions = {
        name: _boolean(request.inputs.get(name), name)
        for name in _TERMINAL_KINDS
    }
    deadline_reached = elapsed_steps >= run_deadline_steps
    selected: str | None = None
    for name in (
        "invalid",
        "safety_violation",
        "blocked",
        "evidence_commit_ready",
        "finality_unavailable",
    ):
        if conditions[name]:
            selected = _TERMINAL_KINDS[name]
            break
    if selected is None and deadline_reached:
        selected = deadline_outcome
    return empty_commit_tck_actual(
        progress={
            "elapsed_steps": elapsed_steps,
            "run_deadline_steps": run_deadline_steps,
            "deadline_reached": deadline_reached,
        },
        outcome={"kind": selected},
    )


def _manifest_threshold_assessment(request: CommitTckRequest) -> dict[str, Any]:
    policy = _manifest_policy(request)
    risk_bands = _object(policy.get("risk_bands"), "manifest risk_bands")
    band_name = _text(request.inputs.get("risk_band"), "risk_band")
    band = _object(risk_bands.get(band_name), "manifest risk band")
    observed = _threshold_observations(request.inputs)
    required_categories = set(
        _text_array(
            band.get("required_challenge_categories"),
            "required_challenge_categories",
        )
    )
    gates = {
        "positive_evidence_satisfied": (
            observed["positive_evidence"]
            >= _nonnegative_integer(
                band.get("minimum_positive_evidence"),
                "minimum_positive_evidence",
            )
        ),
        "counterevidence_satisfied": (
            observed["counterevidence"]
            <= _nonnegative_integer(
                band.get("maximum_counterevidence"),
                "maximum_counterevidence",
            )
        ),
        "counter_ratio_satisfied": (
            observed["counterevidence_ratio_ppm"]
            <= _nonnegative_integer(
                band.get("maximum_counterevidence_ratio_ppm"),
                "maximum_counterevidence_ratio_ppm",
            )
        ),
        "support_clusters_satisfied": (
            observed["support_clusters"]
            >= _positive_integer(
                band.get("minimum_support_clusters"),
                "minimum_support_clusters",
            )
        ),
        "support_ratio_satisfied": (
            observed["support_ratio_ppm"]
            >= _positive_integer(
                band.get("minimum_support_ratio_ppm"),
                "minimum_support_ratio_ppm",
            )
        ),
        "source_diversity_satisfied": (
            observed["source_diversity"]
            >= _positive_integer(
                band.get("minimum_source_diversity"),
                "minimum_source_diversity",
            )
        ),
        "margin_satisfied": (
            observed["leader_margin"]
            >= _positive_integer(band.get("minimum_margin"), "minimum_margin")
        ),
        "challenge_coverage_satisfied": required_categories.issubset(
            observed["challenge_categories"]
        ),
    }
    return empty_commit_tck_actual(
        metrics={
            name: _nonnegative_integer(band.get(name), name)
            for name in (
                "minimum_positive_evidence",
                "maximum_counterevidence",
                "maximum_counterevidence_ratio_ppm",
                "minimum_support_clusters",
                "minimum_support_ratio_ppm",
                "minimum_source_diversity",
                "minimum_margin",
            )
        },
        outcome={
            "risk_band": band_name,
            **gates,
            "ready": all(gates.values()),
        },
    )


def _manifest_assurance_requirements(
    request: CommitTckRequest,
) -> dict[str, Any]:
    policy = _manifest_policy(request)
    assurance = _text(policy.get("assurance"), "manifest assurance")
    proof_rank = {
        "advisory": 0,
        "evidence_bound": 1,
        "certified": 2,
        "distributed": 3,
    }.get(assurance)
    if proof_rank is None:
        raise CommitTckV2ProtocolError("manifest assurance is unsupported")
    certificate = _object(policy.get("certificate"), "manifest certificate")
    distributed = policy.get("distributed")
    if distributed is not None:
        distributed = _object(distributed, "manifest distributed policy")
    profile = {
        "advisory": "pheroos-commit-integrity-v1",
        "evidence_bound": "pheroos-commit-integrity-v1",
        "certified": "pheroos-certified-commit-v1",
        "distributed": "pheroos-distributed-commit-v1",
    }[assurance]
    return empty_commit_tck_actual(
        metrics={
            "proof_rank": proof_rank,
            "distributed_membership_size": (
                _positive_integer(
                    distributed.get("membership_size"),
                    "membership_size",
                )
                if distributed is not None
                else 0
            ),
        },
        outcome={
            "assurance": assurance,
            "profile": profile,
            "certificate_mode": _text(
                certificate.get("mode"),
                "certificate mode",
            ),
            "issuer_attestation_required": _boolean(
                certificate.get("issuer_attestation_required"),
                "issuer_attestation_required",
            ),
            "independent_verification_required": _boolean(
                certificate.get("independent_verification_required"),
                "independent_verification_required",
            ),
            "distributed_finality_required": distributed is not None,
        },
    )


def _manifest_distributed_quorum(request: CommitTckRequest) -> dict[str, Any]:
    policy = _manifest_policy(request)
    distributed = _object(policy.get("distributed"), "manifest distributed policy")
    n = _positive_integer(distributed.get("membership_size"), "membership_size")
    faults = _nonnegative_integer(
        distributed.get("max_byzantine_faults"),
        "max_byzantine_faults",
    )
    quorum = _positive_integer(distributed.get("witness_quorum"), "witness_quorum")
    minimum_domains = _positive_integer(
        distributed.get("minimum_failure_domain_diversity"),
        "minimum_failure_domain_diversity",
    )
    observed_witnesses = _nonnegative_integer(
        request.inputs.get("observed_witnesses"),
        "observed_witnesses",
    )
    observed_domains = _nonnegative_integer(
        request.inputs.get("observed_failure_domains"),
        "observed_failure_domains",
    )
    required_membership = (3 * faults) + 1
    intersection_margin = (2 * quorum) - n - faults
    fault_model_valid = distributed.get("fault_model") == "byzantine_static_v1"
    membership_sufficient = n >= required_membership
    intersection_safe = intersection_margin > 0
    quorum_reached = observed_witnesses >= quorum
    domain_diverse = observed_domains >= minimum_domains
    errors = _distributed_policy_errors(policy, distributed)
    policy_valid = not errors
    return empty_commit_tck_actual(
        metrics={
            "membership_size": n,
            "max_byzantine_faults": faults,
            "witness_quorum": quorum,
            "required_membership_size": required_membership,
            "maximum_safe_quorum": n - faults,
            "intersection_margin": intersection_margin,
            "observed_witnesses": observed_witnesses,
            "observed_failure_domains": observed_domains,
        },
        outcome={
            "fault_model_valid": fault_model_valid,
            "membership_sufficient": membership_sufficient,
            "intersection_safe": intersection_safe,
            "quorum_reached": quorum_reached,
            "failure_domain_diverse": domain_diverse,
            "policy_valid": policy_valid,
            "finality_ready": (
                policy_valid
                and fault_model_valid
                and membership_sufficient
                and intersection_safe
                and quorum_reached
                and domain_diverse
            ),
            "diagnostic_codes": errors,
        },
        failure_code=errors[0] if errors else None,
    )


def _attention_truth_invariance(request: CommitTckRequest) -> dict[str, Any]:
    manifest = _object(request.manifest, "manifest")
    protocol = _object(manifest.get("protocol"), "manifest protocol")
    collective = _object(
        protocol.get("collective_decision_policy"),
        "manifest collective_decision_policy",
    )
    candidates = _candidate_evidence(request.inputs.get("candidate_evidence"))
    ordered = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
    top_score = ordered[0][1]
    tied = [identifier for identifier, score in ordered if score == top_score]
    unique = len(tied) == 1
    leader = tied[0] if unique else ""
    second_score = ordered[1][1] if len(ordered) > 1 else 0
    margin = top_score - second_score if unique else 0
    truth_payload = {
        "candidate_evidence": [
            {"candidate_id": identifier, "evidence": candidates[identifier]}
            for identifier in sorted(candidates)
        ],
        "leader_candidate_id": leader,
        "leader_margin": margin,
        "unique_leader": unique,
    }
    truth_root = _commit_fingerprint(
        truth_payload,
        schema="pheroos-tck-v2-commit-truth-v1",
        profile=request.profile,
    )
    attention_candidate = _text(
        request.inputs.get("attention_candidate"),
        "attention_candidate",
    )
    if attention_candidate not in candidates:
        raise CommitTckV2ProtocolError("attention_candidate must be declared")
    attention_strength = _nonnegative_integer(
        request.inputs.get("attention_strength"),
        "attention_strength",
    )
    weight = collective.get("pheromone_positive_weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
        raise CommitTckV2ProtocolError("pheromone_positive_weight is invalid")
    weight_ppm = int(weight * 1_000_000)
    attention_score = (attention_strength * weight_ppm) // 1_000_000
    attention_payload = {
        "attention_candidate": attention_candidate,
        "attention_score": attention_score,
        "attention_strength": attention_strength,
        "positive_weight_ppm": weight_ppm,
    }
    attention_root = _commit_fingerprint(
        attention_payload,
        schema="pheroos-tck-v2-attention-v1",
        profile=request.profile,
    )
    return empty_commit_tck_actual(
        metrics={
            "leader_margin": margin,
            "attention_score": attention_score,
            "positive_weight_ppm": weight_ppm,
        },
        roots={
            "commit_truth_root": truth_root,
            "attention_root": attention_root,
        },
        outcome={
            "commit_leader": leader,
            "unique_leader": unique,
            "attention_top_candidate": attention_candidate,
            "attention_commit_authority": False,
            "truth_invariant": True,
        },
    )


def _certificate_leaf_binding(request: CommitTckRequest) -> dict[str, Any]:
    payload = deepcopy(
        _object(request.inputs.get("certificate_payload"), "certificate_payload")
    )
    trusted = _object(
        request.inputs.get("trusted_issuer_attestations"),
        "trusted_issuer_attestations",
    )
    base_valid = _verify_evidence_certificate(payload, trusted)
    records: list[dict[str, Any]] = []
    rejected = 0
    for path in _scalar_leaf_paths(payload):
        mutated = deepcopy(payload)
        _mutate_json_leaf(mutated, path)
        accepted = _verify_evidence_certificate(mutated, trusted)
        if not accepted:
            rejected += 1
        records.append(
            {
                "accepted": accepted,
                "mutation_root": _commit_fingerprint(
                    mutated,
                    schema="pheroos-tck-v2-certificate-mutation-v1",
                    profile=request.profile,
                ),
                "path": list(path),
            }
        )
    return empty_commit_tck_actual(
        metrics={
            "authority_leaf_count": len(records),
            "rejected_mutation_count": rejected,
        },
        roots={
            "base_root": _commit_fingerprint(
                payload,
                schema="pheroos-evidence-commit-certificate-v1",
                profile=request.profile,
            ),
            "mutation_set_root": _commit_fingerprint(
                {"mutations": records},
                schema="pheroos-tck-v2-certificate-leaf-audit-v1",
                profile=request.profile,
            ),
        },
        outcome={
            "base_valid": base_valid,
            "all_authority_leaf_mutations_rejected": (
                base_valid and rejected == len(records)
            ),
            "payload_kind": "evidence_commit_certificate",
        },
        certificate={"kind": "evidence_commit", "verified": base_valid},
        failure_code=(
            None
            if base_valid and rejected == len(records)
            else "certificate_authority_leaf_unbound"
        ),
    )


def _trace_leaf_binding(request: CommitTckRequest) -> dict[str, Any]:
    event_type = _text(request.inputs.get("event_type"), "event_type")
    protocol_id = _text(request.inputs.get("protocol_id"), "protocol_id")
    target = _text(request.inputs.get("target"), "target")
    reason = _text(request.inputs.get("reason"), "reason")
    lineage = deepcopy(_object(request.inputs.get("lineage"), "lineage"))
    base_valid = _trace_lineage_is_valid(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        lineage=lineage,
    )
    records: list[dict[str, Any]] = []
    rejected = 0
    for path in _scalar_leaf_paths(lineage):
        mutated = deepcopy(lineage)
        _mutate_json_leaf(mutated, path)
        accepted = _trace_lineage_is_valid(
            event_type=event_type,
            protocol_id=protocol_id,
            target=target,
            lineage=mutated,
        )
        if not accepted:
            rejected += 1
        records.append(
            {
                "accepted": accepted,
                "event_id": _trace_event_id(
                    event_type=event_type,
                    protocol_id=protocol_id,
                    target=target,
                    lineage=mutated,
                ),
                "path": list(path),
            }
        )
    return empty_commit_tck_actual(
        metrics={
            "authority_leaf_count": len(records),
            "rejected_mutation_count": rejected,
        },
        roots={
            "base_root": lineage.get("event_id", ""),
            "mutation_set_root": _commit_fingerprint(
                {"mutations": records},
                schema="pheroos-tck-v2-trace-leaf-audit-v1",
                profile=request.profile,
            ),
        },
        outcome={
            "base_valid": base_valid,
            "all_authority_leaf_mutations_rejected": (
                base_valid and rejected == len(records)
            ),
            "payload_kind": "commit_trace_lineage",
        },
        trace_sequence=[event_type] if base_valid else [],
        failure_code=(
            None
            if base_valid and rejected == len(records)
            else "trace_authority_leaf_unbound"
        ),
    )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommitTckV2ProtocolError(f"{label} must be an object")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise CommitTckV2ProtocolError(
            f"{label} must be a non-negative exact integer"
        )
    return value


def _bounded_nonnegative_integer(value: object, label: str) -> int:
    normalized = _nonnegative_integer(value, label)
    if normalized > _MAX_AUTHORITY_INTEGER:
        raise CommitTckV2ProtocolError(f"{label} exceeds the authority bound")
    return normalized


def _positive_integer(value: object, label: str) -> int:
    normalized = _nonnegative_integer(value, label)
    if normalized <= 0:
        raise CommitTckV2ProtocolError(f"{label} must be positive")
    return normalized


def _positive_scale(value: object) -> int:
    normalized = _bounded_nonnegative_integer(value, "scale")
    if normalized <= 0:
        raise CommitTckV2ProtocolError("scale must be positive")
    return normalized


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise CommitTckV2ProtocolError(f"{label} must be an exact boolean")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CommitTckV2ProtocolError(f"{label} must be a non-blank string")
    return value


def _text_array(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise CommitTckV2ProtocolError(
            f"{label} must be a unique non-blank string array"
        )
    return value


def _manifest_policy(request: CommitTckRequest) -> dict[str, Any]:
    manifest = _object(request.manifest, "manifest")
    protocol = _object(manifest.get("protocol"), "manifest protocol")
    return _object(
        protocol.get("collective_commit_policy"),
        "manifest collective_commit_policy",
    )


def _threshold_observations(inputs: dict[str, Any]) -> dict[str, Any]:
    observed = {
        name: _nonnegative_integer(inputs.get(name), name)
        for name in (
            "positive_evidence",
            "counterevidence",
            "counterevidence_ratio_ppm",
            "support_clusters",
            "support_ratio_ppm",
            "source_diversity",
            "leader_margin",
        )
    }
    observed["challenge_categories"] = set(
        _text_array(inputs.get("challenge_categories"), "challenge_categories")
    )
    return observed


def _distributed_policy_errors(
    policy: dict[str, Any],
    distributed: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if policy.get("assurance") != "distributed":
        errors.append("commit_distributed_policy_inactive")
    if distributed.get("fault_model") != "byzantine_static_v1":
        errors.append("commit_fault_model_invalid")
    if distributed.get("membership_mode") != "static_epoch_verified_clusters_v1":
        errors.append("commit_membership_mode_invalid")
    if distributed.get("conflict_rule") != "freeze_v1":
        errors.append("commit_conflict_rule_invalid")
    n = _positive_integer(distributed.get("membership_size"), "membership_size")
    faults = _nonnegative_integer(
        distributed.get("max_byzantine_faults"),
        "max_byzantine_faults",
    )
    quorum = _positive_integer(distributed.get("witness_quorum"), "witness_quorum")
    minimum_domains = _positive_integer(
        distributed.get("minimum_failure_domain_diversity"),
        "minimum_failure_domain_diversity",
    )
    if n < (3 * faults) + 1:
        errors.append("commit_byzantine_membership_invalid")
    if quorum > n - faults:
        errors.append("commit_witness_quorum_too_large")
    if (2 * quorum) - n <= faults:
        errors.append("commit_quorum_intersection_invalid")
    if minimum_domains > quorum:
        errors.append("commit_failure_domain_diversity_unreachable")
    return errors


def _candidate_evidence(value: object) -> dict[str, int]:
    raw = _object(value, "candidate_evidence")
    if len(raw) < 2:
        raise CommitTckV2ProtocolError(
            "candidate_evidence requires at least two candidates"
        )
    return {
        _text(identifier, "candidate_evidence id"): _nonnegative_integer(
            score,
            "candidate_evidence score",
        )
        for identifier, score in raw.items()
    }


def _commit_fingerprint(
    payload: dict[str, Any],
    *,
    schema: str,
    profile: str,
) -> str:
    _text(schema, "canonical schema")
    _text(profile, "canonical profile")
    canonical = json.dumps(
        {
            "payload": _canonical_json(payload, "payload"),
            "profile": profile,
            "schema": schema,
            "version": "pheroos-commit-wire-v1",
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_json(value: Any, path: str) -> Any:
    if value is None or type(value) in {bool, int, str}:
        if type(value) is int and abs(value) > _MAX_AUTHORITY_INTEGER:
            raise CommitTckV2ProtocolError(f"{path} exceeds the integer bound")
        return value
    if isinstance(value, float):
        raise CommitTckV2ProtocolError(f"{path} must not contain floats")
    if isinstance(value, dict):
        return {
            _text(key, f"{path} key"): _canonical_json(item, f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _canonical_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise CommitTckV2ProtocolError(f"{path} contains unsupported JSON")


def _canonical_set(values: list[str]) -> list[str]:
    records: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values:
        rendered = json.dumps(
            _canonical_json(value, "set"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if rendered in seen:
            raise CommitTckV2ProtocolError("canonical set contains a duplicate")
        seen.add(rendered)
        records.append((sha256(rendered.encode("utf-8")).hexdigest(), value))
    return [value for _, value in sorted(records, key=lambda item: (item[0], item[1]))]


def _verify_evidence_certificate(
    payload: dict[str, Any],
    trusted: dict[str, Any],
) -> bool:
    try:
        profile = _text(payload.get("profile"), "certificate profile")
        assurance = payload.get("assurance")
        if payload.get("schema_discriminator") != "evidence_commit_certificate":
            return False
        if (
            payload.get("certificate_version")
            != "pheroos-evidence-commit-certificate-v1"
            or payload.get("wire_version") != "pheroos-commit-wire-v1"
            or payload.get("canonicalization") != "pheroos-commit-canonical-v1"
            or payload.get("hash_algorithm") != "sha256"
            or assurance not in {"certified", "distributed"}
            or payload.get("authority_scope") != "certified"
        ):
            return False
        expected_profile = {
            "certified": "pheroos-certified-commit-v1",
            "distributed": "pheroos-distributed-commit-v1",
        }[assurance]
        if profile != expected_profile:
            return False
        body = {
            key: deepcopy(value)
            for key, value in payload.items()
            if key
            not in {
                "issuer_attestation_refs",
                "certificate_body_root",
                "certificate_root",
            }
        }
        body_root = _commit_fingerprint(
            body,
            schema="pheroos-evidence-commit-certificate-body-v1",
            profile=profile,
        )
        if payload.get("certificate_body_root") != body_root:
            return False
        refs = _canonical_set(
            _text_array(
                payload.get("issuer_attestation_refs"),
                "issuer_attestation_refs",
            )
        )
        envelope_root = _commit_fingerprint(
            {
                "certificate_body_root": body_root,
                "issuer_attestation_refs": refs,
            },
            schema="pheroos-evidence-commit-certificate-envelope-v1",
            profile=profile,
        )
        if payload.get("certificate_root") != envelope_root:
            return False
        return bool(refs) and all(trusted.get(ref) == body_root for ref in refs)
    except (KeyError, TypeError, ValueError, CommitTckV2ProtocolError):
        return False


def _trace_event_id(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    lineage: dict[str, Any],
) -> str:
    profile = _text(lineage.get("profile"), "trace profile")
    body = {
        "event_type": event_type,
        "lineage": {
            key: value
            for key, value in lineage.items()
            if key not in {"event_id", "extensions"}
        },
        "protocol_id": protocol_id,
        "target": target,
    }
    return _commit_fingerprint(
        body,
        schema="pheroos-commit-trace-event-v1",
        profile=profile,
    )


def _trace_lineage_is_valid(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    lineage: dict[str, Any],
) -> bool:
    try:
        if lineage.get("payload_version") != "pheroos-commit-trace-payload-v1":
            return False
        profile = _text(lineage.get("profile"), "trace profile")
        record_schema = _text(lineage.get("record_schema"), "record schema")
        record_payload = _object(lineage.get("record_payload"), "record payload")
        record_ref = _commit_fingerprint(
            record_payload,
            schema=record_schema,
            profile=profile,
        )
        if lineage.get("record_ref") != record_ref:
            return False
        if event_type == "risk_assessed":
            if lineage.get("risk_ref") != record_ref:
                return False
            if record_payload.get("risk_band") != lineage.get("risk_band"):
                return False
            if record_payload.get("threshold_ref") != lineage.get("threshold_ref"):
                return False
            if (
                record_payload.get("risk_chain_revision")
                != lineage.get("risk_chain_revision")
            ):
                return False
        return lineage.get("event_id") == _trace_event_id(
            event_type=event_type,
            protocol_id=protocol_id,
            target=target,
            lineage=lineage,
        )
    except (TypeError, ValueError, CommitTckV2ProtocolError):
        return False


def _scalar_leaf_paths(
    value: object,
    prefix: tuple[object, ...] = (),
) -> tuple[tuple[object, ...], ...]:
    paths: list[tuple[object, ...]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            paths.extend(_scalar_leaf_paths(value[key], (*prefix, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_scalar_leaf_paths(item, (*prefix, index)))
    elif value is None or type(value) in {bool, int, str}:
        paths.append(prefix)
    else:
        raise CommitTckV2ProtocolError(
            "authority payload contains a non-JSON scalar"
        )
    return tuple(paths)


def _mutate_json_leaf(payload: object, path: tuple[object, ...]) -> None:
    if not path:
        raise CommitTckV2ProtocolError("authority leaf path must not be empty")
    parent = payload
    for component in path[:-1]:
        parent = _read_child(parent, component)
    key = path[-1]
    current = _read_child(parent, key)
    if current is None:
        replacement: object = "tck-mutated"
    elif type(current) is bool:
        replacement = not current
    elif type(current) is int:
        replacement = current + 1
    elif isinstance(current, str):
        if current.startswith("sha256:") and len(current) == 71:
            tail = "0" if current[-1] != "0" else "1"
            replacement = current[:-1] + tail
        else:
            replacement = current + ":tck-mutated"
    else:
        raise CommitTckV2ProtocolError("authority mutation selected a container")
    if isinstance(parent, dict) and isinstance(key, str):
        parent[key] = replacement
        return
    if isinstance(parent, list) and type(key) is int:
        parent[key] = replacement
        return
    raise CommitTckV2ProtocolError("authority mutation path is invalid")


def _read_child(parent: object, key: object) -> Any:
    if isinstance(parent, dict) and isinstance(key, str) and key in parent:
        return parent[key]
    if (
        isinstance(parent, list)
        and type(key) is int
        and 0 <= key < len(parent)
    ):
        return parent[key]
    raise CommitTckV2ProtocolError("authority mutation path is missing")


def main() -> int:
    adapter = IndependentCommitSpecModelAdapter()
    try:
        serve_commit_tck_v2_jsonl(
            adapter.evaluate,
            implementation_id=adapter.implementation_id,
            implementation_version="1",
            supported_operations=SPEC_MODEL_OPERATIONS,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "SPEC_MODEL_IMPLEMENTATION_ID",
    "SPEC_MODEL_OPERATIONS",
    "IndependentCommitSpecModelAdapter",
    "main",
]
