from __future__ import annotations

import math
import struct
import sys

import pytest

from pheroos.governance._hybrid_replay_v2.numeric import (
    HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2,
    decode_binary64_v1,
    encode_binary64_v1,
)


class _FloatSubclass(float):
    pass


class _StrSubclass(str):
    pass


def _binary64_bytes(value: float) -> bytes:
    return struct.pack(">d", value)


def test_numeric_wire_version_is_frozen() -> None:
    assert HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2 == "pheroos-binary64-hex-v1"


@pytest.mark.parametrize(
    "value",
    (
        0.0,
        -0.0,
        1.0,
        -1.0,
        0.1,
        math.pi,
        math.ulp(0.0),
        -math.ulp(0.0),
        float.fromhex("0x0.fffffffffffffp-1022"),
        sys.float_info.min,
        math.nextafter(sys.float_info.max, 0.0),
        sys.float_info.max,
        -sys.float_info.max,
    ),
)
def test_binary64_wire_round_trip_preserves_all_bits(value: float) -> None:
    encoded = encode_binary64_v1(value, "snapshot.metric")

    assert encoded == value.hex()
    assert encoded == encoded.lower()
    assert _binary64_bytes(decode_binary64_v1(encoded, "snapshot.metric")) == (
        _binary64_bytes(value)
    )


def test_negative_zero_is_distinct_and_preserved() -> None:
    encoded = encode_binary64_v1(-0.0, "snapshot.zero")

    assert encoded == "-0x0.0p+0"
    decoded = decode_binary64_v1(encoded, "snapshot.zero")
    assert decoded == 0.0
    assert math.copysign(1.0, decoded) == -1.0
    assert encode_binary64_v1(0.0, "snapshot.zero") == "0x0.0p+0"


@pytest.mark.parametrize(
    "value",
    (
        None,
        False,
        True,
        0,
        1,
        "0x1.0000000000000p+0",
        b"0x1.0000000000000p+0",
        _FloatSubclass(1.0),
    ),
)
def test_encoder_rejects_non_exact_float_values(value: object) -> None:
    with pytest.raises(TypeError, match="snapshot.metric"):
        encode_binary64_v1(value, "snapshot.metric")


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf))
def test_encoder_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="snapshot.metric"):
        encode_binary64_v1(value, "snapshot.metric")


@pytest.mark.parametrize(
    "value",
    (
        None,
        False,
        True,
        0,
        1.0,
        b"0x1.0000000000000p+0",
        _StrSubclass("0x1.0000000000000p+0"),
    ),
)
def test_decoder_rejects_non_exact_string_values(value: object) -> None:
    with pytest.raises(TypeError, match="snapshot.metric"):
        decode_binary64_v1(value, "snapshot.metric")


@pytest.mark.parametrize(
    "value",
    (
        "",
        " ",
        "\t0x1.0000000000000p+0",
        "0x1.0000000000000p+0\n",
        "0x1.0000 000000000p+0",
        "1.0",
        "1",
        "+0x1.0000000000000p+0",
        "0X1.0000000000000P+0",
        "0x1p+0",
        "0x1.0000000000000p0",
        "0x1.0000000000000p+00",
        "0x01.0000000000000p+0",
        "0x1.00000000000000p+0",
        "-0x0.0000000000000p+0",
        "0x0.0000000000000p-1022",
        "nan",
        "NaN",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "0x1.0000000000000p+1024",
        "not-a-number",
    ),
)
def test_decoder_rejects_noncanonical_aliases_and_non_finite_values(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="snapshot.metric"):
        decode_binary64_v1(value, "snapshot.metric")


@pytest.mark.parametrize(
    "canonical",
    (
        "0x0.0000000000001p-1022",
        "-0x0.0000000000001p-1022",
        "0x0.fffffffffffffp-1022",
        "0x1.0000000000000p-1022",
        "0x1.ffffffffffffep+1023",
        "0x1.fffffffffffffp+1023",
        "-0x1.fffffffffffffp+1023",
    ),
)
def test_decoder_accepts_canonical_subnormal_and_boundary_text(
    canonical: str,
) -> None:
    decoded = decode_binary64_v1(canonical, "snapshot.boundary")

    assert decoded.hex() == canonical
    assert encode_binary64_v1(decoded, "snapshot.boundary") == canonical
