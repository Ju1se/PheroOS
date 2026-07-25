from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

import pytest

import pheroos.protocol as protocol
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityV2ProtocolError,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
    loads_governance_authority_read_set_v2,
)


ZERO_ROOT = "sha256:" + ("0" * 64)
ONE_ROOT = "sha256:" + ("1" * 64)


def _entry(
    stream_ref: str = "authority:alpha",
    *,
    revision: int = 0,
    root: str = ZERO_ROOT,
) -> GovernanceReadPreconditionV2:
    return GovernanceReadPreconditionV2(
        stream_ref=stream_ref,
        expected_revision=revision,
        expected_root=root,
    )


def _payload() -> dict[str, object]:
    return {
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
        "entries": [
            {
                "expected_revision": 0,
                "expected_root": ZERO_ROOT,
                "stream_ref": "authority:alpha",
            },
            {
                "expected_revision": 7,
                "expected_root": ONE_ROOT,
                "stream_ref": "authority:éclair",
            },
        ],
        "schema": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    }


def test_authority_v2_constants_and_diagnostics_are_exact() -> None:
    assert AUTHORITY_CANONICAL_VERSION_V2 == "pheroos-authority-canonical-v2"
    assert (
        GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2
        == "pheroos-governance-authority-read-set-v2"
    )
    assert MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2 == 128
    assert MAX_AUTHORITY_REVISION_V2 == 9_007_199_254_740_991
    assert [item.value for item in AuthorityDiagnosticCodeV2] == [
        "authority_profile_unsupported",
        "authority_session_required",
        "authority_session_store_mismatch",
        "authority_scope_mismatch",
        "authority_operation_denied",
        "authority_binding_mismatch",
        "authority_grant_unverified",
        "authority_grant_expired",
        "authority_grant_revoked",
        "governance_read_set_invalid",
        "governance_read_set_stale",
        "governance_transition_conflict",
        "governance_domain_sealed",
        "governance_finality_unavailable",
        "governance_committed_transition_invalid",
        "governance_action_not_authorized",
        "governance_trace_lineage_invalid",
    ]


def test_protocol_facade_reexports_the_canonical_owner_objects() -> None:
    assert protocol.AuthorityDiagnosticCodeV2 is AuthorityDiagnosticCodeV2
    assert protocol.GovernanceReadPreconditionV2 is GovernanceReadPreconditionV2
    assert protocol.GovernanceAuthorityReadSetV2 is GovernanceAuthorityReadSetV2
    assert protocol.AuthorityV2ProtocolError is AuthorityV2ProtocolError


def test_authority_v2_protocol_owner_has_no_governance_or_trace_import() -> None:
    source = (
        Path(__file__).parents[2] / "pheroos" / "protocol" / "authority_v2.py"
    ).read_text(encoding="utf-8")
    assert "pheroos.governance" not in source
    assert "pheroos.trace" not in source


def test_read_precondition_is_frozen_slotted_and_exactly_serialized() -> None:
    value = _entry(revision=MAX_AUTHORITY_REVISION_V2)

    assert not hasattr(value, "__dict__")
    assert value.to_dict() == {
        "expected_revision": MAX_AUTHORITY_REVISION_V2,
        "expected_root": ZERO_ROOT,
        "stream_ref": "authority:alpha",
    }
    assert GovernanceReadPreconditionV2.from_dict(value.to_dict()) == value
    with pytest.raises(FrozenInstanceError):
        value.expected_revision = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("stream_ref", ""),
        ("stream_ref", " authority:alpha"),
        ("stream_ref", "authority:alpha "),
        ("stream_ref", "authority:e\u0301clair"),
        ("expected_revision", True),
        ("expected_revision", 1.0),
        ("expected_revision", -1),
        ("expected_revision", MAX_AUTHORITY_REVISION_V2 + 1),
        ("expected_root", "0" * 64),
        ("expected_root", "sha256:" + ("A" * 64)),
        ("expected_root", "sha256:" + ("0" * 63)),
    ],
)
def test_read_precondition_rejects_noncanonical_fields(
    field: str,
    invalid: object,
) -> None:
    values: dict[str, object] = {
        "stream_ref": "authority:alpha",
        "expected_revision": 0,
        "expected_root": ZERO_ROOT,
    }
    values[field] = invalid

    with pytest.raises(AuthorityV2ProtocolError):
        GovernanceReadPreconditionV2(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "stream_ref": "authority:alpha",
            "expected_revision": 0,
        },
        {
            "stream_ref": "authority:alpha",
            "expected_revision": 0,
            "expected_root": ZERO_ROOT,
            "extension": "forbidden",
        },
        ["not", "an", "object"],
    ],
)
def test_read_precondition_from_dict_requires_the_exact_object(
    payload: object,
) -> None:
    with pytest.raises(AuthorityV2ProtocolError):
        GovernanceReadPreconditionV2.from_dict(payload)


def test_read_set_is_frozen_slotted_and_exactly_serialized() -> None:
    value = GovernanceAuthorityReadSetV2(
        entries=(
            _entry(),
            _entry("authority:éclair", revision=7, root=ONE_ROOT),
        )
    )

    assert not hasattr(value, "__dict__")
    assert value.to_dict() == _payload()
    assert GovernanceAuthorityReadSetV2.from_dict(value.to_dict()) == value
    with pytest.raises(FrozenInstanceError):
        value.entries = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "entries",
    [
        (),
        [_entry()],
        (_entry(), _entry()),
        (_entry("authority:beta"), _entry("authority:alpha")),
        tuple(_entry(f"authority:{index:03d}") for index in range(129)),
        (object(),),
    ],
)
def test_read_set_constructor_rejects_invalid_entry_collections(
    entries: object,
) -> None:
    with pytest.raises(AuthorityV2ProtocolError):
        GovernanceAuthorityReadSetV2(entries=entries)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("canonical_version", "pheroos-authority-canonical-v1"),
        ("schema", "pheroos-governance-authority-read-set-v1"),
    ],
)
def test_read_set_rejects_inexact_discriminators(
    field: str,
    invalid: str,
) -> None:
    values: dict[str, object] = {"entries": (_entry(),)}
    values[field] = invalid

    with pytest.raises(AuthorityV2ProtocolError):
        GovernanceAuthorityReadSetV2(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
            "entries": [_entry().to_dict()],
        },
        {
            "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
            "entries": [_entry().to_dict()],
            "schema": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
            "extension": "forbidden",
        },
        {
            "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
            "entries": (_entry().to_dict(),),
            "schema": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        },
        ["not", "an", "object"],
    ],
)
def test_read_set_from_dict_requires_the_exact_object(payload: object) -> None:
    with pytest.raises(AuthorityV2ProtocolError):
        GovernanceAuthorityReadSetV2.from_dict(payload)


def test_read_set_canonical_bytes_and_root_are_exact() -> None:
    value = GovernanceAuthorityReadSetV2.from_dict(_payload())
    expected = (
        '{"canonical_version":"pheroos-authority-canonical-v2","entries":['
        '{"expected_revision":0,"expected_root":"'
        + ZERO_ROOT
        + '","stream_ref":"authority:alpha"},'
        '{"expected_revision":7,"expected_root":"'
        + ONE_ROOT
        + '","stream_ref":"authority:éclair"}],'
        '"schema":"pheroos-governance-authority-read-set-v2"}'
    ).encode()

    assert value.canonical_bytes() == expected
    assert value.root() == "sha256:" + sha256(expected).hexdigest()
    assert b"\\u00e9" not in expected
    assert not expected.startswith(b"\xef\xbb\xbf")
    assert not expected.endswith(b"\n")


@pytest.mark.parametrize(
    "rendered",
    [
        '{"canonical_version":"pheroos-authority-canonical-v2",'
        '"canonical_version":"pheroos-authority-canonical-v2",'
        '"entries":[],"schema":"pheroos-governance-authority-read-set-v2"}',
        '{"canonical_version":"pheroos-authority-canonical-v2","entries":['
        '{"expected_revision":0,"expected_revision":1,"expected_root":"'
        + ZERO_ROOT
        + '","stream_ref":"authority:alpha"}],'
        '"schema":"pheroos-governance-authority-read-set-v2"}',
        '{"canonical_version":"pheroos-authority-canonical-v2","entries":['
        '{"expected_revision":NaN,"expected_root":"'
        + ZERO_ROOT
        + '","stream_ref":"authority:alpha"}],'
        '"schema":"pheroos-governance-authority-read-set-v2"}',
        '{"canonical_version":"pheroos-authority-canonical-v2","entries":['
        '{"expected_revision":1.0,"expected_root":"'
        + ZERO_ROOT
        + '","stream_ref":"authority:alpha"}],'
        '"schema":"pheroos-governance-authority-read-set-v2"}',
        '{"canonical_version":"pheroos-authority-canonical-v2","entries":[],'
        '"schema":"pheroos-governance-authority-read-set-v2","extra":null}',
    ],
)
def test_json_loader_rejects_duplicate_extra_float_and_nonfinite_values(
    rendered: str,
) -> None:
    with pytest.raises(AuthorityV2ProtocolError):
        loads_governance_authority_read_set_v2(rendered)


def test_json_loader_accepts_text_utf8_bytes_and_bytearray() -> None:
    rendered = json.dumps(_payload(), ensure_ascii=False)
    expected = GovernanceAuthorityReadSetV2.from_dict(_payload())

    assert loads_governance_authority_read_set_v2(rendered) == expected
    assert loads_governance_authority_read_set_v2(rendered.encode()) == expected
    assert (
        loads_governance_authority_read_set_v2(bytearray(rendered.encode())) == expected
    )


@pytest.mark.parametrize(
    "value",
    [
        b"\xff",
        b"\xef\xbb\xbf{}",
        memoryview(b"{}"),
        None,
    ],
)
def test_json_loader_rejects_non_utf8_bom_and_unsupported_inputs(
    value: object,
) -> None:
    with pytest.raises(AuthorityV2ProtocolError):
        loads_governance_authority_read_set_v2(value)  # type: ignore[arg-type]
