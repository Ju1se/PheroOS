from __future__ import annotations

import struct


BYTES_PER_RECORD = 6


def encode_record(sender: int, step: int, value: int) -> bytes:
    """Encode the frozen E2 wire record: three big-endian uint16 fields."""

    if not 0 <= sender <= 0xFFFF or not 0 <= step <= 0xFFFF or not 0 <= value <= 0xFFFF:
        raise ValueError("E2 fixed-width fields must fit uint16")
    return struct.pack(">HHH", sender, step, value)


def encode_direction(direction: int) -> int:
    if direction not in (-1, 0, 1):
        raise ValueError("direction must be -1, 0, or +1")
    return direction + 1
