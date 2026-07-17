from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_COMMIT_PROFILES,
)
from pheroos.protocol.commit_wire import commit_payload_fingerprint

from pheroos.governance._schema.common import (
    CommitWireBinding,
    CommitWireContract,
    _validate_canonical_set,
    authority_integer_schema,
    canonical_text_schema,
    fingerprint_schema,
    fingerprint_set_schema,
    optional_fingerprint_schema,
    optional_text_schema,
    profile_agnostic,
    signed_authority_integer_schema,
    strict_object_schema,
)


def _validate_hybrid_commit_step_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    commit = payload["commit"]
    if commit["profile"] != profile:
        errors.append("$.payload.commit.profile: envelope profile mismatch")
    allowed_profiles = COMMIT_PROFILES_BY_ASSURANCE.get(commit["assurance"])
    if allowed_profiles is None or profile not in allowed_profiles:
        errors.append("$.payload.commit.assurance: profile/assurance mismatch")
    if commit["commit_truth_root"] != commit["commit_assessment_fingerprint"]:
        errors.append("$.payload.commit.commit_truth_root: assessment binding mismatch")
    if commit["assessment_status"] == "ready" and not (
        commit["unique_leader"]
        and commit["leader_ready_for_stability"]
        and commit["leader_candidate_id"]
    ):
        errors.append("$.payload.commit.assessment_status: ready leader is incomplete")
    if not commit["unique_leader"] and commit["leader_candidate_id"]:
        errors.append("$.payload.commit.leader_candidate_id: non-unique step names leader")
    expected_composition = commit_payload_fingerprint(
        {
            "attention": payload["attention"],
            "binding_profile": payload["binding_profile"],
            "commit": commit,
        },
        schema="pheroos-hybrid-commit-composition-v1",
        profile=profile,
    )
    if payload["composition_root"] != expected_composition:
        errors.append("$.payload.composition_root: reconstructable root mismatch")
    return errors

def _validate_hybrid_commit_evaluation_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    authoritative = payload["authoritative"]
    status = payload["status"]
    terminal = payload["terminal"]
    progress_ref = payload["progress_ref"]
    outcome_ref = payload["outcome_ref"]
    if authoritative:
        for field_name in (
            "assessment_ref",
            "context_ref",
            "window_state_ref",
            "replay_state_ref",
        ):
            if not payload[field_name]:
                errors.append(
                    f"$.payload.{field_name}: authoritative evaluation lacks authority ref"
                )
        if status == "progress":
            if terminal or not progress_ref or outcome_ref:
                errors.append("$.payload: authoritative progress is inconsistent")
            if payload["deliver_authorization_ref"]:
                errors.append(
                    "$.payload.deliver_authorization_ref: progress cannot deliver"
                )
        elif not terminal or progress_ref or not outcome_ref:
            errors.append("$.payload: authoritative terminal outcome is inconsistent")
        elif not payload["deliver_authorization_ref"]:
            errors.append(
                "$.payload.deliver_authorization_ref: terminal evaluation must deliver"
            )
        if not payload["trace_event_ids"]:
            errors.append("$.payload.trace_event_ids: authority trace is empty")
    elif (
        status != "invalid"
        or terminal is not True
        or progress_ref
        or outcome_ref
    ):
        errors.append("$.payload: non-authoritative evaluation must be terminal invalid")
    for index, diagnostic in enumerate(payload["diagnostics"]):
        _validate_canonical_set(
            diagnostic["references"],
            path=f"$.payload.diagnostics[{index}].references",
            errors=errors,
        )
    expected_trace_root = commit_payload_fingerprint(
        {"event_ids": tuple(payload["trace_event_ids"])},
        schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
        profile=str(payload["profile"]),
    )
    if payload["trace_root"] != expected_trace_root:
        errors.append("$.payload.trace_root: chronology root mismatch")
    expected_root = commit_payload_fingerprint(
        {
            key: value
            for key, value in payload.items()
            if key != "evaluation_root"
        },
        schema="pheroos-hybrid-commit-evaluation-v1",
        profile=str(payload["profile"]),
    )
    if payload["evaluation_root"] != expected_root:
        errors.append("$.payload.evaluation_root: reconstructable root mismatch")
    return errors

def hybrid_commit_truth_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "assessment_status": {
                "enum": ["not_ready", "ready", "safety_violation"]
            },
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "commit_assessment_fingerprint": fingerprint_schema(),
            "commit_authority_source": {"const": "optimal_commit_assessment_only"},
            "commit_challenge_root": fingerprint_schema(),
            "commit_context_root": fingerprint_schema(),
            "commit_evidence_root": fingerprint_schema(),
            "commit_lease_root": fingerprint_schema(),
            "commit_metrics_root": fingerprint_schema(),
            "commit_truth_root": fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "epoch": authority_integer_schema(),
            "leader_candidate_id": optional_text_schema(),
            "leader_margin": signed_authority_integer_schema(),
            "leader_ready_for_stability": {"type": "boolean"},
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "protocol_id": canonical_text_schema(),
            "run_id": canonical_text_schema(),
            "target": canonical_text_schema(),
            "unique_leader": {"type": "boolean"},
        }
    )

def hybrid_attention_binding_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "attention_fingerprint": fingerprint_schema(),
            "authority_scope": {"const": "none"},
            "commit_authority": {"const": False},
            "exploration_directive_fingerprint": fingerprint_schema(),
            "memory_root": fingerprint_schema(),
            "replay_root": fingerprint_schema(),
            "source_step_root": fingerprint_schema(),
            "trace_root": fingerprint_schema(),
        }
    )

def hybrid_commit_step_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "attention": hybrid_attention_binding_payload_schema(),
            "binding_profile": {"const": "pheroos-hybrid-commit-binding-v1"},
            "commit": hybrid_commit_truth_payload_schema(),
            "composition_root": fingerprint_schema(),
        }
    )

def hybrid_commit_diagnostic_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "code": canonical_text_schema(),
            "severity": {"enum": ["error", "info", "warning"]},
            "stage": canonical_text_schema(),
            "message": canonical_text_schema(),
            "fatal": {"type": "boolean"},
            "references": fingerprint_set_schema(),
        }
    )

def hybrid_commit_evaluation_payload_schema() -> dict[str, Any]:
    optional_root_names = (
        "assessment_ref",
        "attention_ref",
        "binding_step_ref",
        "context_ref",
        "deliver_authorization_ref",
        "distributed_certificate_ref",
        "distributed_state_ref",
        "evidence_certificate_ref",
        "execute_authorization_ref",
        "exploration_directive_ref",
        "finality_verification_ref",
        "local_receipt_ref",
        "outcome_certificate_ref",
        "outcome_ref",
        "progress_ref",
        "publish_authorization_ref",
        "replay_root",
        "replay_state_ref",
        "window_root",
        "window_state_ref",
    )
    schema = strict_object_schema(
        {
            "evaluation_version": {
                "const": "pheroos-hybrid-commit-evaluation-v1"
            },
            "request_ref": fingerprint_schema(),
            "status": {"enum": ["invalid", "outcome", "progress"]},
            "authoritative": {"type": "boolean"},
            "terminal": {"type": "boolean"},
            "assurance_downgraded": {"const": False},
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "protocol_id": canonical_text_schema(),
            "run_id": canonical_text_schema(),
            "target": canonical_text_schema(),
            "epoch": authority_integer_schema(),
            "current_step": authority_integer_schema(),
            "attention_status": {"enum": ["unavailable", "verified"]},
            **{
                name: optional_fingerprint_schema()
                for name in optional_root_names
            },
            "trace_event_ids": fingerprint_set_schema(),
            "trace_root": fingerprint_schema(),
            "diagnostics": {
                "type": "array",
                "items": hybrid_commit_diagnostic_schema(),
            },
            "evaluation_root": fingerprint_schema(),
        }
    )
    schema["allOf"] = [
        {
            "oneOf": [
                {
                    "properties": {
                        "authoritative": {"const": True},
                        "status": {"const": "progress"},
                        "terminal": {"const": False},
                        "progress_ref": fingerprint_schema(),
                        "outcome_ref": {"const": ""},
                    }
                },
                {
                    "properties": {
                        "authoritative": {"const": True},
                        "status": {"enum": ["invalid", "outcome"]},
                        "terminal": {"const": True},
                        "progress_ref": {"const": ""},
                        "outcome_ref": fingerprint_schema(),
                    }
                },
                {
                    "properties": {
                        "authoritative": {"const": False},
                        "status": {"const": "invalid"},
                        "terminal": {"const": True},
                        "progress_ref": {"const": ""},
                        "outcome_ref": {"const": ""},
                    }
                },
            ]
        },
        {
            "if": {
                "properties": {"authoritative": {"const": True}},
                "required": ["authoritative"],
            },
            "then": {
                "properties": {
                    "assessment_ref": fingerprint_schema(),
                    "context_ref": fingerprint_schema(),
                    "window_state_ref": fingerprint_schema(),
                    "replay_state_ref": fingerprint_schema(),
                }
            },
        },
        {
            "oneOf": [
                {
                    "properties": {
                        "attention_status": {"const": "verified"},
                        "binding_step_ref": fingerprint_schema(),
                        "attention_ref": fingerprint_schema(),
                        "exploration_directive_ref": fingerprint_schema(),
                        "diagnostics": {
                            "not": {
                                "contains": {
                                    "properties": {
                                        "code": {
                                            "const": "attention_channel_unavailable"
                                        }
                                    },
                                    "required": ["code"],
                                }
                            }
                        },
                    }
                },
                {
                    "properties": {
                        "attention_status": {"const": "unavailable"},
                        "binding_step_ref": {"const": ""},
                        "attention_ref": {"const": ""},
                        "exploration_directive_ref": {"const": ""},
                        "diagnostics": {
                            "contains": {
                                "oneOf": [
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {"const": "attention"},
                                            "message": {
                                                "const": (
                                                    "Hybrid attention input is missing "
                                                    "or non-authoritative"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {
                                                "const": "exploration_directive"
                                            },
                                            "message": {
                                                "const": (
                                                    "Hybrid exploration directive is "
                                                    "missing, non-authoritative, or does "
                                                    "not match attention"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {"const": "channel_binding"},
                                            "message": {
                                                "const": (
                                                    "Hybrid attention cannot be bound "
                                                    "to the authoritative "
                                                    "CommitAssessment"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                ]
                            },
                            "minContains": 1,
                            "maxContains": 1,
                        },
                    }
                },
            ]
        },
    ]
    return schema


HYBRID_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-hybrid-commit-step-v1",
        hybrid_commit_step_payload_schema,
        _validate_hybrid_commit_step_semantics,
        binding=CommitWireBinding.UNBOUND,
    ),
    CommitWireContract(
        "pheroos-hybrid-commit-evaluation-v1",
        hybrid_commit_evaluation_payload_schema,
        profile_agnostic(_validate_hybrid_commit_evaluation_semantics),
    ),
)


__all__: tuple[str, ...] = ()
