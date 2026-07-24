from __future__ import annotations

from pheroos.governance._commit_certificate_v2.portable_envelope import (
    verify_portable_commit_certificate_v2,
)
from pheroos.protocol._validation_primitives import finite_number
from tests.governance.test_commit_certificate_v2_contracts import (
    _certificate,
    _root,
    _verifier,
)


def test_certificate_expected_body_fingerprint_is_an_authority_binding() -> None:
    certificate = _certificate()

    assert not verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=_verifier(certificate),
        expected_body_root=_root("different-certificate-body"),
    )


def test_authority_numeric_validator_rejects_bool_and_nonfinite_values() -> None:
    assert not finite_number(True)
    assert not finite_number(False)
    assert not finite_number(float("nan"))
    assert not finite_number(float("inf"))
    assert finite_number(0)
    assert finite_number(1.5)
