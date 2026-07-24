"""Private authority-field validation for Commit Decision v2 outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pheroos.governance._commit_decision_v2.common import (
    _require_bool,
    _require_root,
    _require_text,
)


if TYPE_CHECKING:

    class _OutcomeAuthorityFieldsV2(Protocol):
        @property
        def candidate_ref(self) -> str: ...

        @property
        def claim_root(self) -> str: ...

        @property
        def output_contract_root(self) -> str: ...

        @property
        def output_payload_root(self) -> str: ...

        @property
        def finality_root(self) -> str: ...

        @property
        def epistemically_committed(self) -> bool: ...

        @property
        def delivery_eligible(self) -> bool: ...

        @property
        def publication_eligible(self) -> bool: ...

        @property
        def execution_eligible(self) -> bool: ...
else:

    class _OutcomeAuthorityFieldsV2(Protocol):
        pass


def _validate_outcome_authority_fields_impl_v2(
    value: _OutcomeAuthorityFieldsV2,
) -> None:
    _require_text(value.candidate_ref, "commit outcome candidate", allow_empty=True)
    for field in (
        "claim_root",
        "output_contract_root",
        "output_payload_root",
        "finality_root",
    ):
        _require_root(
            getattr(value, field), f"commit outcome {field}", allow_empty=True
        )
    for field in (
        "epistemically_committed",
        "delivery_eligible",
        "publication_eligible",
        "execution_eligible",
    ):
        _require_bool(getattr(value, field), f"commit outcome {field}")
    if not value.delivery_eligible:
        raise ValueError("every committed decision outcome must be deliverable")
    if value.publication_eligible or value.execution_eligible:
        raise ValueError("commit decision cannot authorize publication or execution")
