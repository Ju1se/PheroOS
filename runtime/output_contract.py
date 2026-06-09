from __future__ import annotations

import re
from typing import Any

from runtime.legacy_output_contract import legacy_raw_data_marker_fallback_source, legacy_raw_data_markers
from runtime.swarm.evidence_contract import validate_writer_evidence_contract
from runtime.swarm.stop_policy import action_blocked_by_stop_policy


GLOBAL_RAW_DATA_MARKERS = (
    "raw row",
    "raw_rows",
    "source_rows",
)
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|authorization|bearer|password|passwd|token|secret|credential|cookie)\s*[:=]\s*\S+",
    re.I,
)
SECRET_VALUE_RE = re.compile(r"\b(sk-[A-Za-z0-9._-]{12,}|sk-cp-[A-Za-z0-9._-]{12,}|Bearer\s+\S{8,})\b", re.I)
DEFECT_MEMO_MARKERS = (
    "defect memo",
    "defect report",
    "guardrail report",
    "blocked by governance",
    "publication blocked",
    "not publishable",
    "缺陷备忘录",
    "缺陷报告",
    "不可发布",
    "不能作为最终",
)


def apply_output_policy(text: str, state: dict[str, Any], *, actor: str = "writer") -> str:
    violations = output_policy_violations(text, state, actor=actor)
    if not violations:
        return text
    return "\n".join(
        [
            "# Output Policy Guardrail Report",
            "",
            f"`{actor}` output violates capability-declared OutputPolicy.",
            "",
            "## Policy Violations",
            *[f"- `{item.get('code')}`: {item.get('message')}" for item in violations[:8]],
            "",
            "## Required Action",
            "Regenerate the output using only allowed claims, required caveats, and capability-approved wording.",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def output_policy_violations(text: str, state: dict[str, Any], *, actor: str = "writer") -> list[dict[str, Any]]:
    policy = output_policy_from_state(state)
    evidence_policy = evidence_policy_from_state(state)
    haystack = str(text or "")
    normalized_haystack = normalize_text(haystack)
    violations: list[dict[str, Any]] = []

    if contains_secret_material(haystack):
        violations.append({"code": "secret_material_in_final", "message": "final output contains credential-like text"})

    raw_violation = raw_data_policy_violation(haystack, state)
    if raw_violation:
        violations.append(raw_violation)

    if not policy and not evidence_policy:
        return dedupe_violations(violations)

    for phrase in string_list(policy.get("blocked_phrases")):
        if normalize_text(phrase) and normalize_text(phrase) in normalized_haystack:
            violations.append({"code": "blocked_phrase", "message": phrase})
    for caveat in string_list(policy.get("required_caveats")):
        if normalize_text(caveat) and normalize_text(caveat) not in normalized_haystack:
            violations.append({"code": "missing_required_caveat", "message": caveat})
    violations.extend(committed_candidate_conflict_violations(haystack, state, policy=policy))
    mode = output_mode_from_state(state)
    allowed_modes = string_list(policy.get("allowed_output_modes"))
    if mode and allowed_modes and mode not in allowed_modes:
        violations.append({"code": "output_mode_not_allowed", "message": mode})
    violations.extend(defect_memo_violations(haystack, state, policy=policy, actor=actor))
    violations.extend(evidence_contract_violations(haystack, state, policy=policy, evidence_policy=evidence_policy, actor=actor))
    return dedupe_violations(violations)


def output_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    direct = state.get("output_policy") if isinstance(state.get("output_policy"), dict) else {}
    if direct:
        return direct
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    direct = metadata.get("output_policy") if isinstance(metadata.get("output_policy"), dict) else {}
    if direct:
        return direct
    swarm_plan = swarm_plan_from_state(state)
    policy = swarm_plan.get("output_policy") if isinstance(swarm_plan.get("output_policy"), dict) else {}
    return policy


def evidence_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    direct = state.get("evidence_policy") if isinstance(state.get("evidence_policy"), dict) else {}
    if direct:
        return direct
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    direct = metadata.get("evidence_policy") if isinstance(metadata.get("evidence_policy"), dict) else {}
    if direct:
        return direct
    swarm_plan = swarm_plan_from_state(state)
    policy = swarm_plan.get("evidence_policy") if isinstance(swarm_plan.get("evidence_policy"), dict) else {}
    return policy


def swarm_plan_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return swarm_plan


def output_mode_from_state(state: dict[str, Any]) -> str:
    for source in (
        state,
        state.get("metadata") if isinstance(state.get("metadata"), dict) else {},
        swarm_plan_from_state(state),
    ):
        if not isinstance(source, dict):
            continue
        mode = str(source.get("output_mode") or source.get("final_output_mode") or "").strip()
        if mode:
            return mode
    return ""


def evidence_contract_violations(
    text: str,
    state: dict[str, Any],
    *,
    policy: dict[str, Any],
    evidence_policy: dict[str, Any],
    actor: str,
) -> list[dict[str, Any]]:
    if not evidence_policy and not bool(policy.get("final_claim_evidence_required")):
        return []
    if actor != "final_judge" and not evidence_policy and not bool(policy.get("final_claim_evidence_required")):
        return []
    violations = []
    for item in validate_writer_evidence_contract(text, state):
        code = str(item.get("code") or "")
        if actor != "final_judge" and code in {"forbidden_phrase", "committed_candidate_mismatch"}:
            continue
        violations.append({"code": code, "message": item.get("message")})
    violations.extend(candidate_consistency_violations(text, state, policy=policy, actor=actor))
    return violations


def committed_candidate_conflict_violations(
    text: str,
    state: dict[str, Any],
    *,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    committed = committed_candidate_label(state)
    if not committed:
        return []
    committed_key = normalize_text(committed)
    violations: list[dict[str, Any]] = []
    for rule in policy.get("committed_candidate_conflicts") or []:
        if not isinstance(rule, dict):
            continue
        rule_keys = {
            normalize_text(rule.get("candidate")),
            normalize_text(rule.get("id")),
            normalize_text(rule.get("label")),
        }
        if committed_key not in {key for key in rule_keys if key}:
            continue
        for phrase in string_list(rule.get("blocked_phrases")):
            if phrase_present(text, phrase):
                violations.append(
                    {
                        "code": "committed_candidate_conflict_phrase",
                        "message": f"{committed} blocks `{phrase}`",
                    }
                )
                break
    return violations


def defect_memo_violations(
    text: str,
    state: dict[str, Any],
    *,
    policy: dict[str, Any],
    actor: str,
) -> list[dict[str, Any]]:
    if not bool(policy.get("defect_memo_on_block")):
        return []
    if actor not in {"writer", "final_judge"}:
        return []
    signal = action_blocked_by_stop_policy(state, f"{actor}:publish_report")
    if not signal or is_defect_memo_output(text, policy=policy):
        return []
    target = str(signal.get("target") or "active stop-signal").strip()
    return [
        {
            "code": "defect_memo_required_on_block",
            "message": f"{actor}:publish_report is blocked by {target}; output must be a defect memo",
        }
    ]


def candidate_consistency_violations(
    text: str,
    state: dict[str, Any],
    *,
    policy: dict[str, Any],
    actor: str,
) -> list[dict[str, Any]]:
    checks = {normalize_text(item) for item in string_list(policy.get("final_judge_required_checks"))}
    if actor != "final_judge" or not checks.intersection({"committed_candidate", "candidate_consistency"}):
        return []
    committed = committed_candidate_label(state)
    if not committed:
        return []
    haystack = normalize_text(text)
    candidates = candidate_labels(state)
    conflicting = [label for label in candidates if normalize_text(label) and normalize_text(label) != normalize_text(committed)]
    for label in conflicting:
        if normalize_text(label) in haystack:
            return [{"code": "committed_candidate_conflict", "message": label}]
    return []


def committed_candidate_label(state: dict[str, Any]) -> str:
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    return str(committed.get("label") or committed.get("id") or "").strip()


def candidate_labels(state: dict[str, Any]) -> list[str]:
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    labels = []
    for item in quorum.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        labels.extend([str(item.get("label") or "").strip(), str(item.get("id") or "").strip()])
    if not labels:
        labels = candidate_policy_labels(state)
    return [label for label in labels if label]


def candidate_policy_labels(state: dict[str, Any]) -> list[str]:
    swarm_plan = swarm_plan_from_state(state)
    policy = swarm_plan.get("candidate_policy") if isinstance(swarm_plan.get("candidate_policy"), dict) else {}
    labels: list[str] = []
    for item in policy.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        labels.extend(
            [
                str(item.get("label") or "").strip(),
                str(item.get("id") or item.get("candidate") or "").strip(),
            ]
        )
    return [label for label in labels if label]


def raw_data_policy_violation(text: str, state: dict[str, Any]) -> dict[str, Any] | None:
    evidence_policy = evidence_policy_from_state(state)
    markers, source = raw_data_markers_for_policy(evidence_policy)
    matched = matched_raw_data_markers(text, markers)
    if not matched:
        return None
    declared_allowed = bool(evidence_policy.get("raw_data_allowed_in_final")) if evidence_policy else False
    return {
        "code": "raw_data_not_allowed_in_final",
        "message": "raw data markers are not final-output safe; global safety overrides capability policy",
        "policy_source": source,
        "declared_raw_data_allowed_in_final": declared_allowed,
        "matched_markers": matched[:8],
    }


def raw_data_markers_for_policy(evidence_policy: dict[str, Any]) -> tuple[list[str], str]:
    declared = string_list(evidence_policy.get("raw_data_markers") or evidence_policy.get("raw_output_markers"))
    if declared:
        return unique([*GLOBAL_RAW_DATA_MARKERS, *declared]), "capability_evidence_policy"
    return unique([*GLOBAL_RAW_DATA_MARKERS, *legacy_raw_data_markers()]), legacy_raw_data_marker_fallback_source()


def matched_raw_data_markers(text: str, markers: list[str]) -> list[str]:
    lowered = str(text or "").lower()
    matched: list[str] = []
    for marker in markers:
        needle = str(marker or "").strip().lower()
        if not needle:
            continue
        if needle in lowered and marker not in matched:
            matched.append(marker)
    return matched


def contains_raw_data(text: str, markers: list[str] | None = None) -> bool:
    selected = markers if markers is not None else unique([*GLOBAL_RAW_DATA_MARKERS, *legacy_raw_data_markers()])
    return bool(matched_raw_data_markers(text, selected))


def contains_secret_material(text: str) -> bool:
    value = str(text or "")
    return bool(CREDENTIAL_ASSIGNMENT_RE.search(value) or SECRET_VALUE_RE.search(value))


def is_defect_memo_output(text: str, *, policy: dict[str, Any] | None = None) -> bool:
    value = normalize_text(text)
    declared = string_list((policy or {}).get("defect_memo_markers"))
    markers = [*list(DEFECT_MEMO_MARKERS), *declared]
    return any(normalize_text(marker) in value for marker in markers if normalize_text(marker))


def dedupe_violations(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for violation in violations:
        key = (violation.get("code"), violation.get("message"))
        if key in seen:
            continue
        seen.add(key)
        output.append(violation)
    return output


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def phrase_present(text: str, phrase: str) -> bool:
    needle = str(phrase or "").strip()
    if not needle:
        return False
    haystack = str(text or "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", needle):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
        return re.search(pattern, haystack, re.I) is not None
    return needle.lower() in haystack.lower()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def unique(values: list[str] | tuple[str, ...]) -> list[str]:
    output: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in output:
            output.append(item)
    return output
