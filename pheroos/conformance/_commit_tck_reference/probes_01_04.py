"""Private Commit TCK reference probes 01 04 handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_reference import (
    issue_reference_disposition,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.errors import GovernanceError

from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationPolarity,
    verified_observation_fingerprint,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _binding,
    _evaluate_binding,
    _observation,
    _reference_scenario,
    _risk_trace_sequence,
)


def _probe_case_01(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    group = f"group:{scenario.namespace}:shared-positive"
    observations = tuple(
        _observation(
            scenario,
            index=100 + index,
            principal_index=(index - 1) % len(scenario.principals),
            independence_group=group,
            source_domain=f"domain:{scenario.namespace}:positive:{index}",
        )
        for index in range(1, 4)
    )
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=observations,
        variant="case-01",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=observations,
    )
    contribution = summary.positive_groups[0]
    return _result(
        metrics={
            "raw_positive": contribution.raw_contribution,
            "counted_positive": contribution.counted_contribution,
            "positive_group_cap": collective_commit_policy(
                scenario.policy
            ).evidence_qualification.positive_group_cap,
            "observation_count": len(contribution.observation_fingerprints),
        },
        roots={"evidence_root": binding.evidence_root},
        outcome={
            "cap_enforced": contribution.counted_contribution
            <= collective_commit_policy(
                scenario.policy
            ).evidence_qualification.positive_group_cap
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_02(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    group = f"group:{scenario.namespace}:shared-counter"
    counters = tuple(
        _observation(
            scenario,
            index=200 + index,
            polarity=ObservationPolarity.CONTRADICT,
            independence_group=group,
            source_domain=f"domain:{scenario.namespace}:counter:{index}",
        )
        for index in range(1, 4)
    )
    dispositions = tuple(
        issue_reference_disposition(
            scenario.namespace,
            item,
            index=200 + index,
            kind=CounterevidenceDispositionKind.ACCEPTED,
        )
        for index, item in enumerate(counters, start=1)
    )
    positives = scenario.observations[scenario.leader_id]
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=positives,
        counters=counters,
        dispositions=dispositions,
        variant="case-02",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=positives,
        counters=counters,
        dispositions=dispositions,
    )
    contribution = summary.counter_groups[0]
    return _result(
        metrics={
            "raw_counter": contribution.raw_contribution,
            "counted_counter": contribution.counted_contribution,
            "counter_group_cap": collective_commit_policy(
                scenario.policy
            ).evidence_qualification.counter_group_cap,
            "active_counter_count": len(
                summary.active_counter_observation_fingerprints
            ),
        },
        roots={"counter_root": binding.counter_root},
        outcome={
            "duplicate_amplification_blocked": contribution.counted_contribution
            <= collective_commit_policy(
                scenario.policy
            ).evidence_qualification.counter_group_cap
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_03(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    counter = _observation(
        scenario,
        index=301,
        polarity=ObservationPolarity.CONTRADICT,
        materiality_ppm=1_000_000,
        criticality_ppm=1_000_000,
    )
    disposition = issue_reference_disposition(
        scenario.namespace,
        counter,
        index=301,
        kind=CounterevidenceDispositionKind.UNRESOLVED,
    )
    positives = scenario.observations[scenario.leader_id]
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=positives,
        counters=(counter,),
        dispositions=(disposition,),
        variant="case-03",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=positives,
        counters=(counter,),
        dispositions=(disposition,),
    )
    return _result(
        metrics={
            "positive_evidence": summary.positive_evidence,
            "blocking_critical_count": len(
                summary.blocking_critical_counter_observation_fingerprints
            ),
        },
        roots={
            "evidence_root": binding.evidence_root,
            "counter_root": binding.counter_root,
            "disposition_root": binding.disposition_root,
        },
        outcome={
            "critical_counterevidence_clear": summary.critical_counterevidence_clear,
            "commit_ready": summary.evidence_gates_satisfied,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="unresolved_critical_counterevidence",
    )


def _probe_case_04(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    counter = _observation(
        scenario,
        index=401,
        polarity=ObservationPolarity.CONTRADICT,
    )
    rejected = False
    error_type = ""
    try:
        issue_reference_disposition(
            scenario.namespace,
            counter,
            index=401,
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(),
            resolution_ref="",
        )
    except (GovernanceError, ValueError) as exc:
        rejected = True
        error_type = type(exc).__name__
    return _result(
        metrics={"rebuttal_observation_count": 0},
        roots={"counter_observation_ref": verified_observation_fingerprint(counter)},
        outcome={"rejected": rejected, "error_type": error_type},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="fake_rebuttal_rejected" if rejected else "fake_rebuttal_accepted",
    )
