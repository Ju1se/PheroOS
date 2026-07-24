"""Public-only portable Commit Certificate v2 conformance matrix."""

from __future__ import annotations

from hashlib import sha256
import hmac
from typing import Protocol, cast, runtime_checkable

from pheroos.conformance.report import CheckResult
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateAuthorityLeafV2,
    CommitCertificateAuthorityRoleV2,
    CommitCertificateBodyV2,
    CommitCertificateIssuerAttestationVerifierV2,
    PortableCommitCertificateV2,
    verify_portable_commit_certificate_v2,
)
from pheroos.protocol import CERTIFIED_COMMIT_PROFILE_VERSION
from pheroos.protocol.commit_models import CommitAssurance


GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-certificate-conformance-v2"
)
_CHECK_NAME = "commit_certificate_v2_contract"
_ISSUER = "issuer:conformance:certificate"


@runtime_checkable
class CommitCertificateConformanceAdapterV2(Protocol):
    implementation_id: str
    conformance_version: str

    def attestation_ref_v2(self, issuer_ref: str, body_root: str) -> str: ...

    def verifier_v2(self) -> CommitCertificateIssuerAttestationVerifierV2: ...


class ReferenceCommitCertificateConformanceAdapterV2:
    implementation_id = "pheroos-reference-certificate-verifier-v2"
    conformance_version = GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2

    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str], str] = {}

    def attestation_ref_v2(self, issuer_ref: str, body_root: str) -> str:
        ref = (
            "attestation:reference:"
            + sha256(
                issuer_ref.encode("utf-8") + b"\x00" + body_root.encode("ascii")
            ).hexdigest()
        )
        self._bindings[(issuer_ref, ref)] = body_root
        return ref

    def verifier_v2(self) -> CommitCertificateIssuerAttestationVerifierV2:
        return _ReferenceVerifier(self._bindings.copy())


class _ReferenceVerifier:
    def __init__(self, bindings: dict[tuple[str, str], str]) -> None:
        self._bindings = bindings

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return self._bindings.get((issuer_ref, attestation_ref)) == body_root


class IndependentStdlibCommitCertificateConformanceAdapterV2:
    implementation_id = "stdlib-independent-certificate-verifier-v2"
    conformance_version = GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2

    def attestation_ref_v2(self, issuer_ref: str, body_root: str) -> str:
        return _stdlib_attestation_ref(issuer_ref, body_root)

    def verifier_v2(self) -> CommitCertificateIssuerAttestationVerifierV2:
        return _IndependentStdlibVerifier()


class _IndependentStdlibVerifier:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return hmac.compare_digest(
            attestation_ref,
            _stdlib_attestation_ref(issuer_ref, body_root),
        )


def run_governance_commit_certificate_conformance_v2(
    adapter: CommitCertificateConformanceAdapterV2,
) -> CheckResult:
    try:
        if not isinstance(adapter, CommitCertificateConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if (
            adapter.conformance_version
            != GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2
        ):
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        if type(adapter.implementation_id) is not str or not adapter.implementation_id:
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME, False, f"adapter_exception:{type(exc).__name__}"
        )
    problems: list[str] = []
    try:
        _run_matrix(adapter, problems)
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _run_matrix(
    adapter: CommitCertificateConformanceAdapterV2,
    problems: list[str],
) -> None:
    body = _body()
    attestation = adapter.attestation_ref_v2(_ISSUER, body.body_root)
    certificate = _certificate(body, attestation)
    verifier = adapter.verifier_v2()
    if not verify_portable_commit_certificate_v2(
        certificate.to_dict(),
        trusted_verifier=verifier,
        expected_body_root=body.body_root,
        expected_target_ref=body.target_ref,
        expected_candidate_ref=body.candidate_ref,
        expected_claim_root=body.claim_root,
        expected_epoch=body.epoch,
    ):
        problems.append("canonical_round_trip")
    _check_every_body_mutation(certificate, verifier, problems)
    _check_envelope_mutations(certificate, verifier, problems)
    _check_trust_boundary(certificate, verifier, problems)


def _check_every_body_mutation(
    certificate: PortableCommitCertificateV2,
    verifier: CommitCertificateIssuerAttestationVerifierV2,
    problems: list[str],
) -> None:
    mutations: tuple[tuple[str, object], ...] = (
        ("target_ref", "target:forged"),
        ("epoch", certificate.body.epoch + 1),
        ("manifest_root", _root("manifest:forged")),
        ("commit_policy_root", _root("policy:forged")),
        ("decision_receipt_root", _root("decision-receipt:forged")),
        ("decision_inclusion_root", _root("decision-inclusion:forged")),
        ("seal_receipt_root", _root("seal-receipt:forged")),
        ("seal_inclusion_root", _root("seal-inclusion:forged")),
        ("candidate_ref", "candidate:forged"),
        ("claim_root", _root("claim:forged")),
        ("evidence_root", _root("evidence:forged")),
        ("output_payload_root", _root("payload:forged")),
    )
    for field, replacement in mutations:
        payload = certificate.to_dict()
        raw_body = cast(dict[str, object], payload["body"])
        raw_body[field] = replacement
        if verify_portable_commit_certificate_v2(payload, trusted_verifier=verifier):
            problems.append(f"body_mutation:{field}")
    payload = certificate.to_dict()
    raw_body = cast(dict[str, object], payload["body"])
    raw_leaves = cast(list[object], raw_body["authority_leaves"])
    risk = next(
        cast(dict[str, object], item)
        for item in raw_leaves
        if cast(dict[str, object], item)["role"] == "risk"
    )
    risk["head_root"] = _root("risk-head:forged")
    if verify_portable_commit_certificate_v2(payload, trusted_verifier=verifier):
        problems.append("authority_leaf_mutation")


def _check_envelope_mutations(
    certificate: PortableCommitCertificateV2,
    verifier: CommitCertificateIssuerAttestationVerifierV2,
    problems: list[str],
) -> None:
    for field, replacement in (
        ("certificate_id", "certificate:forged"),
        ("issuer_ref", "issuer:forged"),
        ("envelope_nonce", "nonce:forged"),
        ("provenance_ref", "urn:forged"),
        ("issued_at_step", certificate.issued_at_step + 1),
    ):
        payload = certificate.to_dict()
        payload[field] = replacement
        if verify_portable_commit_certificate_v2(payload, trusted_verifier=verifier):
            problems.append(f"envelope_mutation:{field}")
    unknown = certificate.to_dict()
    unknown["authority"] = True
    if verify_portable_commit_certificate_v2(unknown, trusted_verifier=verifier):
        problems.append("unknown_envelope_field")
    boolean = certificate.to_dict()
    boolean["issued_at_step"] = True
    if verify_portable_commit_certificate_v2(boolean, trusted_verifier=verifier):
        problems.append("boolean_integer_substitution")


def _check_trust_boundary(
    certificate: PortableCommitCertificateV2,
    verifier: CommitCertificateIssuerAttestationVerifierV2,
    problems: list[str],
) -> None:
    if verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=verifier,
        expected_epoch=certificate.body.epoch + 1,
    ):
        problems.append("expected_context_binding")
    if verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=cast(
            CommitCertificateIssuerAttestationVerifierV2,
            {"trusted": certificate.body.body_root},
        ),
    ):
        problems.append("raw_mapping_as_authority")


def _body() -> CommitCertificateBodyV2:
    return CommitCertificateBodyV2(
        wire_version="pheroos-commit-wire-v1",
        canonicalization="pheroos-commit-canonical-v1",
        hash_algorithm="sha256",
        domain_root=_root("domain"),
        scope_ref="scope:certificate:conformance",
        profile=CERTIFIED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.CERTIFIED,
        protocol_ref="protocol:certificate:conformance",
        run_ref="run:certificate:conformance",
        target_ref="target:certificate:conformance",
        epoch=7,
        manifest_root=_root("manifest"),
        commit_policy_root=_root("commit-policy"),
        decision_stream_ref="authority:decision:conformance",
        decision_revision=6,
        decision_transition_id="transition:decision:heartbeat:6",
        decision_snapshot_root=_root("decision-snapshot"),
        decision_head_root=_root("decision-head"),
        decision_receipt_root=_root("decision-receipt"),
        decision_inclusion_root=_root("decision-inclusion"),
        seal_transition_id="transition:decision:seal:5",
        seal_revision=5,
        seal_snapshot_root=_root("seal-snapshot"),
        seal_receipt_root=_root("seal-receipt"),
        seal_head_root=_root("seal-head"),
        seal_inclusion_root=_root("seal-inclusion"),
        seal_root=_root("seal"),
        window_root=_root("window"),
        frozen_dependency_root=_root("frozen-dependency"),
        assessment_root=_root("assessment"),
        candidate_ref="candidate:accepted",
        claim_root=_root("claim"),
        evidence_root=_root("evidence"),
        challenge_root=_root("challenge"),
        lease_root=_root("lease"),
        output_contract_root=_root("output-contract"),
        output_payload_root=_root("output-payload"),
        authority_leaves=_leaves(),
    )


def _leaves() -> tuple[CommitCertificateAuthorityLeafV2, ...]:
    return tuple(
        CommitCertificateAuthorityLeafV2(
            role=role,
            stream_ref=f"authority:{role.value}:conformance",
            revision=3,
            transition_id=f"transition:{role.value}:3",
            snapshot_root=_root(f"snapshot:{role.value}"),
            head_root=_root(f"head:{role.value}"),
            receipt_root=_root(f"receipt:{role.value}"),
        )
        for role in CommitCertificateAuthorityRoleV2
    )


def _certificate(
    body: CommitCertificateBodyV2,
    attestation_ref: str,
) -> PortableCommitCertificateV2:
    return PortableCommitCertificateV2(
        certificate_id="certificate:conformance",
        issuer_ref=_ISSUER,
        issued_at_step=9,
        provenance_ref="urn:conformance:certificate",
        envelope_nonce="nonce:conformance:certificate",
        body=body,
        issuer_attestation_refs=(attestation_ref,),
    )


def _stdlib_attestation_ref(issuer_ref: str, body_root: str) -> str:
    digest = sha256(
        b"pheroos-independent-certificate-conformance-v2\x00"
        + issuer_ref.encode("utf-8")
        + b"\x00"
        + body_root.encode("ascii")
    ).hexdigest()
    return "attestation:stdlib:" + digest


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


for _public in (
    CommitCertificateConformanceAdapterV2,
    ReferenceCommitCertificateConformanceAdapterV2,
    IndependentStdlibCommitCertificateConformanceAdapterV2,
    run_governance_commit_certificate_conformance_v2,
):
    _public.__module__ = "pheroos.conformance"
del _public


__all__ = [
    "GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2",
    "CommitCertificateConformanceAdapterV2",
    "IndependentStdlibCommitCertificateConformanceAdapterV2",
    "ReferenceCommitCertificateConformanceAdapterV2",
    "run_governance_commit_certificate_conformance_v2",
]
