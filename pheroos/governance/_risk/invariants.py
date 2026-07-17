from __future__ import annotations

from collections.abc import Mapping

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    SUPPORTED_RISK_BANDS,
    CollectiveCommitPolicy,
    CommitAssurance,
    RiskBandPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_risk_bands


def risk_policy_root(
    policy: CollectiveCommitPolicy,
    *,
    profile: str,
) -> str:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("risk policy root requires CollectiveCommitPolicy")
    normalized_profile = require_commit_profile(profile, "risk policy profile")
    _validate_risk_table(policy)
    return commit_payload_fingerprint(
        {
            "risk_bands": {
                name: _risk_band_payload(policy.risk_bands[name])
                for name in SUPPORTED_RISK_BANDS
            }
        },
        schema="pheroos-risk-band-policy-root-v1",
        profile=normalized_profile,
    )

def _validate_bound_record(record: object, field_name: str) -> None:
    profile = require_commit_profile(getattr(record, "profile"), f"{field_name} profile")
    assurance = require_commit_assurance(
        getattr(record, "assurance"),
        f"{field_name} assurance",
    )
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    require_commit_fingerprint(
        getattr(record, "manifest_root"),
        f"{field_name} manifest_root",
    )
    require_commit_fingerprint(
        getattr(record, "commit_policy_root"),
        f"{field_name} commit_policy_root",
    )
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(getattr(record, name), f"{field_name} {name}")
    require_commit_step(getattr(record, "epoch"), f"{field_name} epoch")

def _normalized_bindings(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    field_name: str,
) -> dict[str, object]:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        f"{field_name} assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[
        normalized_assurance.value
    ]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    return {
        "profile": normalized_profile,
        "assurance": normalized_assurance,
        "manifest_root": require_commit_fingerprint(
            manifest_root,
            f"{field_name} manifest_root",
        ),
        "commit_policy_root": require_commit_fingerprint(
            commit_policy_root,
            f"{field_name} commit_policy_root",
        ),
        "protocol_id": require_commit_text(
            protocol_id,
            f"{field_name} protocol_id",
        ),
        "run_id": require_commit_text(run_id, f"{field_name} run_id"),
        "target": require_commit_text(target, f"{field_name} target"),
        "epoch": require_commit_step(epoch, f"{field_name} epoch"),
    }

def _validate_policy_binding(
    policy: object,
    bindings: Mapping[str, object],
) -> str:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("risk issuance requires CollectiveCommitPolicy")
    if policy.target != bindings["target"]:
        raise GovernanceError("risk policy target binding mismatch")
    assurance = bindings["assurance"]
    if type(assurance) is not CommitAssurance or policy.assurance != assurance.value:
        raise GovernanceError("risk policy assurance binding mismatch")
    observed_policy_root = commit_policy_fingerprint(
        policy,
        profile=str(bindings["profile"]),
    )
    if observed_policy_root != bindings["commit_policy_root"]:
        raise GovernanceError("risk commit policy root binding mismatch")
    _validate_risk_table(policy)
    return risk_policy_root(policy, profile=str(bindings["profile"]))

def _validate_risk_table(policy: CollectiveCommitPolicy) -> None:
    diagnostics = validate_risk_bands(policy, path="collective_commit_policy.risk_bands")
    if diagnostics:
        codes = ", ".join(sorted({item.code for item in diagnostics}))
        raise GovernanceError(f"risk policy is invalid or non-monotonic: {codes}")

def _record_bindings_equal(record: object, bindings: Mapping[str, object]) -> bool:
    return all(getattr(record, name) == value for name, value in bindings.items())

def _same_commit_scope(left: object, right: object) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        )
    )

def _risk_band_payload(band: RiskBandPolicy) -> dict[str, object]:
    if type(band) is not RiskBandPolicy:
        raise GovernanceError("risk band must use the Protocol ABI record")
    return {
        "executable_outcomes": tuple(
            require_commit_labels(
                band.executable_outcomes,
                "risk band executable outcomes",
                allow_empty=True,
            )
        ),
        "maximum_counterevidence": band.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            band.maximum_counterevidence_ratio_ppm
        ),
        "minimum_assurance": band.minimum_assurance,
        "minimum_margin": band.minimum_margin,
        "minimum_positive_evidence": band.minimum_positive_evidence,
        "minimum_source_diversity": band.minimum_source_diversity,
        "minimum_support_clusters": band.minimum_support_clusters,
        "minimum_support_ratio_ppm": band.minimum_support_ratio_ppm,
        "publishable_outcomes": tuple(
            require_commit_labels(
                band.publishable_outcomes,
                "risk band publishable outcomes",
                allow_empty=True,
            )
        ),
        "required_challenge_categories": tuple(
            require_commit_labels(
                band.required_challenge_categories,
                "risk band required challenge categories",
            )
        ),
        "stability_steps": band.stability_steps,
    }

def _risk_band_values(band: RiskBandPolicy) -> tuple[object, ...]:
    payload = _risk_band_payload(band)
    return tuple(payload[name] for name in sorted(payload))
