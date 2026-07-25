"""Private, independent Commit TCK reference handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.conformance.commit_tck_v2_protocol import CommitTckRequest
from pheroos.conformance._commit_tck_reference.probes_01_04 import (
    _probe_case_01,
    _probe_case_02,
    _probe_case_03,
    _probe_case_04,
)

from pheroos.conformance._commit_tck_reference.probes_05_07 import (
    _probe_case_05,
    _probe_case_06,
    _probe_case_07,
)

from pheroos.conformance._commit_tck_reference.probes_08_13 import (
    _probe_case_08,
    _probe_case_09,
    _probe_case_10,
    _probe_case_11,
    _probe_case_12,
    _probe_case_13,
)

from pheroos.conformance._commit_tck_reference.probes_14 import (
    _probe_case_14,
)

from pheroos.conformance._commit_tck_reference.probes_15_20 import (
    _probe_case_15,
    _probe_case_16,
    _probe_case_17,
    _probe_case_18,
    _probe_case_19,
    _probe_case_20,
)

from pheroos.conformance._commit_tck_reference.probes_21_26 import (
    _probe_case_21,
    _probe_case_22,
    _probe_case_23,
    _probe_case_24,
    _probe_case_25,
    _probe_case_26,
)

from pheroos.conformance._commit_tck_reference.probes_27_30 import (
    _probe_case_27,
    _probe_case_28,
    _probe_case_29,
    _probe_case_30,
)

from pheroos.conformance._commit_tck_reference.probes_31_34 import (
    _probe_case_31,
    _probe_case_32,
    _probe_case_33,
    _probe_case_34,
)

from pheroos.conformance._commit_tck_reference.probes_35_38 import (
    _probe_case_35,
    _probe_case_36,
    _probe_case_37,
    _probe_case_38,
)

MATRIX_PROBES: dict[int, Callable[[CommitTckRequest], dict[str, Any]]] = {
    1: _probe_case_01,
    2: _probe_case_02,
    3: _probe_case_03,
    4: _probe_case_04,
    5: _probe_case_05,
    6: _probe_case_06,
    7: _probe_case_07,
    8: _probe_case_08,
    9: _probe_case_09,
    10: _probe_case_10,
    11: _probe_case_11,
    12: _probe_case_12,
    13: _probe_case_13,
    14: _probe_case_14,
    15: _probe_case_15,
    16: _probe_case_16,
    17: _probe_case_17,
    18: _probe_case_18,
    19: _probe_case_19,
    20: _probe_case_20,
    21: _probe_case_21,
    22: _probe_case_22,
    23: _probe_case_23,
    24: _probe_case_24,
    25: _probe_case_25,
    26: _probe_case_26,
    27: _probe_case_27,
    28: _probe_case_28,
    29: _probe_case_29,
    30: _probe_case_30,
    31: _probe_case_31,
    32: _probe_case_32,
    33: _probe_case_33,
    34: _probe_case_34,
    35: _probe_case_35,
    36: _probe_case_36,
    37: _probe_case_37,
    38: _probe_case_38,
}

__all__ = ["MATRIX_PROBES"]
