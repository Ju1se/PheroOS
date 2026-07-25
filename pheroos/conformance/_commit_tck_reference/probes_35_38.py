"""Private Commit TCK reference probes 35 38 handlers."""

from __future__ import annotations

import json

from pathlib import Path

import subprocess

import sys

from tempfile import TemporaryDirectory

from typing import Any

from pheroos.conformance._commit_tck.artifacts import (
    COMMIT_TCK_ARTIFACT,
    COMMIT_TCK_SCHEMA_ID,
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
)

from pheroos.conformance._commit_tck.models import (
    result as _result,
    text_value as _text,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.conformance.profile import profile_for_manifest

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.candidate import Candidate, CandidateSet

from pheroos.governance.quorum import (
    QuorumSignal,
    evaluate_quorum_decision,
    quorum_decision_is_authoritative,
)

from pheroos.governance.signal import verify_signal_input

from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_payload_fingerprint,
)

from pheroos.protocol.manifest import capability_manifest_from_dict

from pheroos.protocol.validation import validate_capability_manifest

from pheroos.trace import (
    TraceEvent,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _require_vector_manifest,
)


def _probe_case_35(vector: _CommitTckRequest) -> dict[str, Any]:
    from pheroos.conformance._manifest_check_registry import (
        project_active_manifest_checks,
    )

    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    profile = profile_for_manifest(manifest)
    projection = project_active_manifest_checks(profile.required_checks)
    required = projection.required
    registered = projection.registered
    missing = projection.missing
    skipped = projection.skipped_or_na
    return _result(
        metrics={
            "required_check_count": len(required),
            "registered_check_count": len(registered),
            "missing_check_count": len(missing),
            "skipped_check_count": len(skipped),
        },
        roots={
            "active_check_set_root": commit_payload_fingerprint(
                {"required_checks": required},
                schema="pheroos-active-conformance-check-set-v1",
                profile=vector.profile,
            )
        },
        outcome={
            "profile": profile.version,
            "active": True,
            "all_registered": not missing,
            "no_skip_or_na": not skipped,
            "missing": list(missing),
            "skipped_or_na": list(skipped),
        },
        failure_code=(
            "active_conformance_check_missing"
            if missing
            else "active_conformance_check_skipped"
            if skipped
            else None
        ),
    )


def _probe_case_36(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest_payload = _require_vector_manifest(vector)
    try:
        manifest = capability_manifest_from_dict(manifest_payload)
    except Exception as exc:
        return _result(
            outcome={
                "loaded": False,
                "valid": False,
                "profile_selected": False,
                "diagnostic_codes": [],
                "load_error": type(exc).__name__,
            },
            failure_code=f"fail_closed:{type(exc).__name__}",
        )
    diagnostics = validate_capability_manifest(manifest)
    codes = tuple(sorted(item.code for item in diagnostics if item.level == "error"))
    profile_selected = True
    profile_error = ""
    try:
        profile_for_manifest(manifest)
    except Exception as exc:
        profile_selected = False
        profile_error = type(exc).__name__
    valid = not codes and profile_selected
    return _result(
        roots={
            "declared_manifest_root": commit_manifest_fingerprint(
                manifest,
                profile=vector.profile,
            ),
        },
        outcome={
            "loaded": True,
            "valid": valid,
            "profile_selected": profile_selected,
            "diagnostic_codes": list(codes),
            "profile_error": profile_error,
        },
        failure_code=(
            None if valid else codes[0] if codes else f"fail_closed:{profile_error}"
        ),
    )


def _probe_case_37(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    profile = profile_for_manifest(manifest)
    target = manifest.protocol.quorum_policy.target
    candidate_id = _text(
        vector.inputs.get("candidate_id"),
        "case 37 candidate_id",
    )
    source_id = _text(vector.inputs.get("source_id"), "case 37 source_id")
    candidates = CandidateSet(
        tuple(
            Candidate(item.id, item.target, item.safe_fallback)
            for item in manifest.protocol.candidates
        )
    )
    verification = verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:tck:legacy",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:pheroos:tck:legacy-quorum",
        trace_event_id=f"trace:{vector.id}:legacy-quorum",
    )
    signal = QuorumSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        target=target,
        verification=verification,
    )
    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=manifest.protocol.quorum_policy,
        signals=[signal],
        fallback_candidate_id=manifest.protocol.quorum_policy.fallback_candidate,
    )
    event = TraceEvent(
        event_type="commit",
        protocol_id=manifest.protocol.id,
        target=target,
        reason=decision.reason,
        lineage={
            "target": target,
            "candidate_id": decision.candidate_id,
            "decision_reason": decision.reason,
            "upstream_score_lineage": [verification.trace_event_id],
        },
    )
    event.validate()
    return _result(
        metrics={
            "signal_count": 1,
            "commit_threshold": manifest.protocol.quorum_policy.commit_threshold,
        },
        roots={
            "legacy_result_root": commit_payload_fingerprint(
                {
                    "candidate_id": decision.candidate_id,
                    "committed": decision.committed,
                    "reason": decision.reason,
                    "target": decision.target,
                },
                schema="pheroos-legacy-quorum-result-v1",
                profile=profile.version,
            ),
            "legacy_trace_root": commit_payload_fingerprint(
                {
                    "event_type": event.event_type,
                    "lineage": event.lineage,
                    "protocol_id": event.protocol_id,
                    "reason": event.reason,
                    "target": event.target,
                },
                schema="pheroos-legacy-quorum-trace-v1",
                profile=profile.version,
            ),
        },
        outcome={
            "profile": profile.version,
            "candidate_id": decision.candidate_id,
            "committed": decision.committed,
            "reason": decision.reason,
            "authoritative": quorum_decision_is_authoritative(decision),
        },
        trace_sequence=[event.event_type],
    )


def _probe_case_38(vector: _CommitTckRequest) -> dict[str, Any]:
    del vector
    vectors = load_commit_tck_vectors()
    cases = tuple(item.matrix_case for item in vectors)
    ids = tuple(item.id for item in vectors)
    schema = commit_tck_schema()
    matrix_root = commit_payload_fingerprint(
        {"matrix_cases": cases, "vector_ids": ids},
        schema="pheroos-commit-tck-matrix-index-v1",
        profile="pheroos-commit-integrity-v1",
    )
    schema_root = commit_payload_fingerprint(
        schema,
        schema="pheroos-commit-tck-schema-export-v1",
        profile="pheroos-commit-integrity-v1",
    )
    artifact_root = commit_tck_artifact_root()
    external_projection: dict[str, Any] = {}
    external_error = ""
    script = """
import json
from pathlib import Path
import sys
import_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(import_root))
import pheroos
package_path = Path(pheroos.__file__).resolve()
if not package_path.is_relative_to(import_root):
    raise RuntimeError("isolated TCK probe imported outside the declared root")
from pheroos.conformance.commit_tck import commit_tck_artifact_root, commit_tck_schema, load_commit_tck_vectors
from pheroos.protocol.commit_wire import commit_payload_fingerprint
vectors = load_commit_tck_vectors()
cases = tuple(item.matrix_case for item in vectors)
ids = tuple(item.id for item in vectors)
print(json.dumps({
    "matrix_root": commit_payload_fingerprint(
        {"matrix_cases": cases, "vector_ids": ids},
        schema="pheroos-commit-tck-matrix-index-v1",
        profile="pheroos-commit-integrity-v1",
    ),
    "schema_root": commit_payload_fingerprint(
        commit_tck_schema(),
        schema="pheroos-commit-tck-schema-export-v1",
        profile="pheroos-commit-integrity-v1",
    ),
    "artifact_root": commit_tck_artifact_root(),
    "vector_count": len(vectors),
}, sort_keys=True))
"""
    import_root = Path(__file__).resolve().parents[3]
    try:
        with TemporaryDirectory(prefix="pheroos-tck-cwd-") as directory:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", script, str(import_root)],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        if completed.returncode != 0:
            external_error = f"subprocess_exit_{completed.returncode}"
        else:
            loaded = json.loads(completed.stdout)
            if isinstance(loaded, dict):
                external_projection = loaded
            else:
                external_error = "subprocess_projection_invalid"
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        external_error = type(exc).__name__
    external_matches = external_projection == {
        "matrix_root": matrix_root,
        "schema_root": schema_root,
        "artifact_root": artifact_root,
        "vector_count": len(vectors),
    }
    complete = cases == tuple(range(1, 39))
    resource_present = bool(COMMIT_TCK_ARTIFACT.is_file())
    return _result(
        metrics={
            "vector_count": len(vectors),
            "matrix_case_count": len(set(cases)),
            "minimum_case": min(cases),
            "maximum_case": max(cases),
        },
        roots={
            "matrix_root": matrix_root,
            "schema_root": schema_root,
            "artifact_root": artifact_root,
        },
        outcome={
            "resource_present": resource_present,
            "complete_matrix": complete,
            "external_cwd_independent": external_matches,
            "duplicate_ids": len(ids) != len(set(ids)),
            "external_error": external_error,
        },
        certificate={
            "artifact_package": "pheroos.conformance",
            "artifact_name": "tck/commit-integrity-v1.json",
            "schema_id": COMMIT_TCK_SCHEMA_ID,
        },
        failure_code=(
            "tck_resource_missing"
            if not resource_present
            else "tck_matrix_incomplete"
            if not complete
            else "tck_external_cwd_failure"
            if not external_matches
            else None
        ),
    )
