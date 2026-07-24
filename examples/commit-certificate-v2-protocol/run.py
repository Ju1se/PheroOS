"""Provider-free executable proof of the public Commit Certificate v2 ABI."""

from __future__ import annotations

import json

from pheroos.conformance.checks.commit_certificate_v2_contract import (
    GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2,
    IndependentStdlibCommitCertificateConformanceAdapterV2,
    ReferenceCommitCertificateConformanceAdapterV2,
    run_governance_commit_certificate_conformance_v2,
)


RESULT_SCHEMA = "pheroos-commit-certificate-v2-example-result-v1"


def run_example() -> dict[str, object]:
    adapters = (
        ReferenceCommitCertificateConformanceAdapterV2(),
        IndependentStdlibCommitCertificateConformanceAdapterV2(),
    )
    results = tuple(
        run_governance_commit_certificate_conformance_v2(adapter)
        for adapter in adapters
    )
    failed = tuple(result for result in results if not result.ok)
    if failed:
        detail = ", ".join(result.detail for result in failed)
        raise RuntimeError(f"Commit Certificate v2 Conformance failed: {detail}")
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "authority_source": "trusted-issuer-attestation-verifier-v2",
        "conformance_version": (GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2),
        "implementations": [adapter.implementation_id for adapter in adapters],
        "results": [
            {
                "name": result.name,
                "ok": result.ok,
                "detail": result.detail,
            }
            for result in results
        ],
        "proved_invariants": [
            "canonical_portable_round_trip",
            "independent_attestation_verification",
            "complete_eight_authority_leaf_set",
            "decision_current_head_binding",
            "actual_seal_history_binding",
            "body_and_envelope_tamper_rejection",
            "expected_context_binding",
            "unknown_field_rejection",
            "boolean_integer_rejection",
            "portable_data_is_not_authority",
        ],
    }


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
