from __future__ import annotations

import math

import pytest

import pheroos.governance.authority_schema_v2 as authority_schema


def test_authority_reader_rejects_non_objects_and_rethrows_typed_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2) as captured:
        authority_schema.read_authority_wire_record_v2([])
    assert (
        captured.value.code is authority_schema.AuthorityWireValidationCodeV2.NOT_OBJECT
    )

    schema = next(iter(authority_schema._AUTHORITY_WIRE_READERS_V2))
    expected = authority_schema.AuthorityWireValidationErrorV2(
        authority_schema.AuthorityWireValidationCodeV2.RECORD_INVALID,
        "/forced",
        "forced typed reader failure",
    )

    def reject(_payload: object) -> object:
        raise expected

    monkeypatch.setitem(authority_schema._AUTHORITY_WIRE_READERS_V2, schema, reject)
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2) as rethrown:
        authority_schema.read_authority_wire_record_v2({"schema": schema})
    assert rethrown.value is expected


def test_authority_json_decoder_rejects_invalid_encoding_shape_and_numbers() -> None:
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2) as malformed:
        authority_schema.loads_authority_wire_record_v2('{"schema":')
    assert (
        malformed.value.code
        is authority_schema.AuthorityWireValidationCodeV2.INVALID_JSON
    )

    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2):
        authority_schema._require_json_text(b"\xff")
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2):
        authority_schema._require_json_text(42)
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2):
        authority_schema._reject_duplicate_keys([("cafe\u0301", 1)])
    with pytest.raises(authority_schema.AuthorityWireValidationErrorV2):
        authority_schema._reject_nonfinite_tree(math.nan)
