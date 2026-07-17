from __future__ import annotations

import pytest

from pheroos._digest import is_canonical_sha256_fingerprint


class _HostileFingerprint(str):
    def __getitem__(self, key: object) -> object:
        if isinstance(key, slice):
            return b"0" * 64
        return super().__getitem__(key)  # type: ignore[index]


@pytest.mark.parametrize(
    "value",
    (
        "sha256:" + "0" * 64,
        "sha256:" + "0123456789abcdef" * 4,
        "sha256:" + "f" * 64,
    ),
)
def test_canonical_sha256_fingerprint_accepts_exact_lowercase_hex(value: str) -> None:
    assert is_canonical_sha256_fingerprint(value)


@pytest.mark.parametrize(
    "value",
    (
        None,
        b"sha256:" + b"0" * 64,
        "",
        "sha256:" + "0" * 63,
        "sha256:" + "0" * 65,
        "sha512:" + "0" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "_" * 64,
        "sha256:" + " " * 64,
        "sha256:" + "é" * 64,
    ),
)
def test_canonical_sha256_fingerprint_rejects_noncanonical_values(
    value: object,
) -> None:
    assert not is_canonical_sha256_fingerprint(value)


def test_canonical_sha256_fingerprint_uses_str_subclass_storage() -> None:
    valid = _HostileFingerprint("sha256:" + "0" * 64)
    invalid = _HostileFingerprint("sha256:" + "g" * 64)

    assert is_canonical_sha256_fingerprint(valid)
    assert not is_canonical_sha256_fingerprint(invalid)
