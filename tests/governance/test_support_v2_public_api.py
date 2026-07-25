from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import pheroos.governance.support_v2 as support_v2
from pheroos.governance.support_v2 import (
    PrincipalVerificationRecordV2,
    VerifiedMembershipSourceV2,
    VerifiedPrincipalVerificationSourceV2,
    VerifiedSupportSourceV2,
)


ROOT = Path(__file__).resolve().parents[2]
FACADE = ROOT / "pheroos/governance/support_v2.py"


def test_support_v2_public_facade_resolves_every_declared_symbol() -> None:
    assert len(support_v2.__all__) == len(set(support_v2.__all__))
    assert all(hasattr(support_v2, name) for name in support_v2.__all__)


def test_support_v2_public_objects_have_native_public_identity() -> None:
    public_objects = tuple(
        getattr(support_v2, name)
        for name in support_v2.__all__
        if inspect.isclass(getattr(support_v2, name))
        or inspect.isfunction(getattr(support_v2, name))
    )
    assert public_objects
    assert all(
        item.__module__ == "pheroos.governance.support_v2" for item in public_objects
    )


def test_support_v2_facade_does_not_reintroduce_legacy_support_owner() -> None:
    source = FACADE.read_text(encoding="utf-8")
    assert "pheroos.governance.support import" not in source
    assert "pheroos.governance._support." not in source
    assert "legacy" not in source.lower().replace("legacy Support owner".lower(), "")


def test_verified_source_handles_are_not_caller_constructible() -> None:
    for source_type in (
        VerifiedPrincipalVerificationSourceV2,
        VerifiedMembershipSourceV2,
        VerifiedSupportSourceV2,
    ):
        with pytest.raises(TypeError):
            source_type()


def test_portable_verification_record_round_trips_only_canonical_wire() -> None:
    root = "sha256:" + "a" * 64
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:public-api",
        cluster_ref="cluster:public-api",
        failure_domain_ref="failure-domain:public-api",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=root,
        evidence_roots=("sha256:" + "b" * 64,),
        issued_at_step=1,
        expires_at_step=10,
        provenance_ref="urn:pheroos:test:public-api",
        source_trace_roots=("sha256:" + "c" * 64,),
    )
    assert PrincipalVerificationRecordV2.from_dict(record.to_dict()) == record
    noncanonical = record.to_dict()
    noncanonical["evidence_roots"] = tuple(record.evidence_roots)
    with pytest.raises(TypeError):
        PrincipalVerificationRecordV2.from_dict(noncanonical)
