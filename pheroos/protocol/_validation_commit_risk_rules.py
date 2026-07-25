from __future__ import annotations

from collections.abc import Mapping

from pheroos.protocol._validation_commit_constants import COMMIT_ASSURANCE_ORDER
from pheroos.protocol._validation_commit_primitives import authority_integer_in_range
from pheroos.protocol._validation_primitives import (
    canonical_string_set,
    validation_error,
)
from pheroos.protocol.commit_models import (
    MAX_AUTHORITY_INTEGER,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_RISK_BANDS,
    SUPPORTED_TERMINAL_OUTCOMES,
    WEIGHT_SCALE,
    CollectiveCommitPolicy,
    CommitWindowPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.models import ValidationDiagnostic


def validate_risk_bands(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not isinstance(policy.risk_bands, Mapping) or set(policy.risk_bands) != set(
        SUPPORTED_RISK_BANDS
    ):
        return [
            validation_error(
                "commit_risk_band_coverage_invalid",
                "risk policy must declare exactly LOW, MODERATE, HIGH, and CRITICAL",
                path,
            )
        ]
    previous: RiskBandPolicy | None = None
    for band_name in SUPPORTED_RISK_BANDS:
        band = policy.risk_bands[band_name]
        band_path = f"{path}.{band_name}"
        if not isinstance(band, RiskBandPolicy):
            diagnostics.append(
                validation_error(
                    "commit_risk_band_type_invalid",
                    "risk band must use the canonical Protocol ABI declaration",
                    band_path,
                )
            )
            previous = None
            continue
        diagnostics.extend(_validate_risk_band_declaration(band, band_path))
        diagnostics.extend(_validate_risk_band_authority(policy, band, band_path))
        diagnostics.extend(_validate_risk_band_actions(policy, band, band_path))

        if previous is not None and _risk_monotonicity_invalid(band, previous):
            diagnostics.append(
                validation_error(
                    "commit_risk_monotonicity_invalid",
                    "risk thresholds, assurance, challenges, and action authority must strengthen monotonically",
                    band_path,
                )
            )
        previous = band
    return diagnostics


def _validate_risk_band_declaration(
    band: RiskBandPolicy,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum, maximum in (
        (
            "minimum_positive_evidence",
            band.minimum_positive_evidence,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "maximum_counterevidence",
            band.maximum_counterevidence,
            0,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "maximum_counterevidence_ratio_ppm",
            band.maximum_counterevidence_ratio_ppm,
            0,
            WEIGHT_SCALE,
        ),
        (
            "minimum_support_clusters",
            band.minimum_support_clusters,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        ("minimum_support_ratio_ppm", band.minimum_support_ratio_ppm, 1, WEIGHT_SCALE),
        (
            "minimum_source_diversity",
            band.minimum_source_diversity,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        ("minimum_margin", band.minimum_margin, 1, MAX_AUTHORITY_INTEGER),
        ("stability_steps", band.stability_steps, 1, MAX_AUTHORITY_INTEGER),
    ):
        if not authority_integer_in_range(value, minimum, maximum):
            diagnostics.append(
                validation_error(
                    "commit_risk_numeric_invalid",
                    f"{name} is outside the declared commit numeric bounds",
                    f"{path}.{name}",
                )
            )
    if band.minimum_assurance not in SUPPORTED_COMMIT_ASSURANCES:
        diagnostics.append(
            validation_error(
                "commit_risk_assurance_invalid",
                "risk band minimum assurance is unsupported",
                f"{path}.minimum_assurance",
            )
        )
    if not canonical_string_set(
        band.required_challenge_categories, require_nonempty=True
    ):
        diagnostics.append(
            validation_error(
                "commit_risk_challenges_invalid",
                "risk band challenge categories must be unique canonical strings",
                f"{path}.required_challenge_categories",
            )
        )
    for name, outcomes in (
        ("publishable_outcomes", band.publishable_outcomes),
        ("executable_outcomes", band.executable_outcomes),
    ):
        if not canonical_string_set(outcomes) or not set(outcomes).issubset(
            SUPPORTED_TERMINAL_OUTCOMES
        ):
            diagnostics.append(
                validation_error(
                    "commit_risk_outcomes_invalid",
                    f"{name} must contain unique supported outcomes",
                    f"{path}.{name}",
                )
            )
    return diagnostics


def _validate_risk_band_authority(
    policy: CollectiveCommitPolicy,
    band: RiskBandPolicy,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    evidence = policy.evidence_qualification
    if isinstance(evidence, EvidenceQualificationPolicy) and (
        band.minimum_positive_evidence < evidence.minimum_positive_evidence
        or band.maximum_counterevidence > evidence.maximum_counterevidence
        or band.maximum_counterevidence_ratio_ppm
        > evidence.maximum_counterevidence_ratio_ppm
        or band.minimum_source_diversity < evidence.minimum_source_diversity
        or not set(band.required_challenge_categories).issuperset(
            evidence.required_challenge_categories
        )
    ):
        diagnostics.append(
            validation_error(
                "commit_risk_evidence_weakened",
                "risk band cannot weaken the evidence qualification baseline",
                path,
            )
        )
    support = policy.support_lease
    if isinstance(support, SupportLeasePolicy) and (
        band.minimum_support_clusters < support.minimum_support_clusters
        or band.minimum_support_ratio_ppm < support.support_ratio_ppm
    ):
        diagnostics.append(
            validation_error(
                "commit_risk_support_weakened",
                "risk band cannot weaken the support lease baseline",
                path,
            )
        )
    return diagnostics


def _validate_risk_band_actions(
    policy: CollectiveCommitPolicy,
    band: RiskBandPolicy,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    window = policy.commit_window
    if isinstance(window, CommitWindowPolicy):
        if band.stability_steps < window.minimum_stability_steps:
            diagnostics.append(
                validation_error(
                    "commit_risk_window_weakened",
                    "risk band cannot weaken the stability baseline",
                    f"{path}.stability_steps",
                )
            )
        if band.stability_steps > window.deliberation_deadline_steps:
            diagnostics.append(
                validation_error(
                    "commit_risk_window_unreachable",
                    "risk-band stability cannot exceed the deliberation deadline",
                    f"{path}.stability_steps",
                )
            )
    terminal = policy.terminal_outcome
    if isinstance(terminal, TerminalOutcomePolicy) and (
        not set(band.publishable_outcomes).issubset(terminal.publishable_outcomes)
        or not set(band.executable_outcomes).issubset(terminal.executable_outcomes)
    ):
        diagnostics.append(
            validation_error(
                "commit_risk_action_ceiling_exceeded",
                "risk-band action outcomes must stay inside the terminal policy ceiling",
                path,
            )
        )
    if not set(band.executable_outcomes).issubset({"evidence_commit"}):
        diagnostics.append(
            validation_error(
                "commit_risk_execution_unsafe",
                "risk bands may execute only an evidence commit",
                f"{path}.executable_outcomes",
            )
        )
    return diagnostics


def _risk_monotonicity_invalid(
    band: RiskBandPolicy,
    previous: RiskBandPolicy,
) -> bool:
    weaker_minimum = any(
        current < prior
        for current, prior in (
            (band.minimum_positive_evidence, previous.minimum_positive_evidence),
            (band.minimum_support_clusters, previous.minimum_support_clusters),
            (band.minimum_support_ratio_ppm, previous.minimum_support_ratio_ppm),
            (band.minimum_source_diversity, previous.minimum_source_diversity),
            (band.minimum_margin, previous.minimum_margin),
            (band.stability_steps, previous.stability_steps),
        )
    )
    weaker_maximum = (
        band.maximum_counterevidence > previous.maximum_counterevidence
        or band.maximum_counterevidence_ratio_ppm
        > previous.maximum_counterevidence_ratio_ppm
    )
    weaker_challenge = not set(band.required_challenge_categories).issuperset(
        previous.required_challenge_categories
    )
    weaker_assurance = COMMIT_ASSURANCE_ORDER.get(
        band.minimum_assurance, -1
    ) < COMMIT_ASSURANCE_ORDER.get(previous.minimum_assurance, -1)
    expanded_actions = not set(band.publishable_outcomes).issubset(
        previous.publishable_outcomes
    ) or not set(band.executable_outcomes).issubset(previous.executable_outcomes)
    return (
        weaker_minimum
        or weaker_maximum
        or weaker_challenge
        or weaker_assurance
        or expanded_actions
    )
