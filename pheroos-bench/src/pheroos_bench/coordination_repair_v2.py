"""Additive diagnostics and stop-on-failure forks over the frozen v1 consumer.

The executable policy/task/runtime path remains v1. This module never rewrites
its JSON or changes model choices, authority, receipts, costs or hidden scoring.
The v2 pilot explicitly supplies its separately selected model adapter.
"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from . import coordination_repair_v1 as v1
from . import coordination_repair_v1_tasks as tasks
from .coordination_repair_v1_forks import BRANCHES, prepare_prefix


METHOD = "coordination_repair_session_v2"
FORK_METHOD = "coordination_repair_fork_execution_v2"
_DISPATCHED = {"dispatched", "received", "response_rejected"}
_TERMINAL_STOPS = {"public_accepted_submission", "budget_deadline_stop",
                   "diagnostic_one_submission_opportunity"}


def _object(value):
    return json.loads(value) if isinstance(value, str) else value


def _communication(snapshot):
    """Mailbox sends and dispatched prompt exposures are different channels.

    v1 does not consume mailbox messages. No sends proves zero mailbox delivery
    in this closed finite consumer. Unexpected sends leave delivery repetition
    unknown: Session v1 does not record each mailbox materialization/delivery.
    Repeated exported event rows must never masquerade as repeated deliveries.
    """
    events = snapshot["events"]
    sent = [e for e in events if e["event_type"] == "ext.session.message_sent"]
    calls = [c for c in snapshot["calls"]
             if c["action"] == "model.generate" and c["state"] in _DISPATCHED]
    seen, exposures, repeats = set(), 0, 0
    for call in calls:
        for message in _object(call["request"])["messages"]:
            # Role+exact content, across this Session; no semantic deduplication.
            identity = v1.digest(message)
            exposures += 1
            repeats += int(identity in seen)
            seen.add(identity)
    return dict(
        mailbox_messages_sent=len(sent),
        message_delivery_count=None if sent else 0,
        message_duplicate_count=None if sent else 0,
        message_duplicate_denominator=None if sent else 0,
        message_duplicate_rate=None,
        message_measurement_status="UNOBSERVED_DELIVERIES" if sent else "CHANNEL_NOT_USED",
        message_duplicate_identity="session scope, recipient, message_id; requires actual delivery observations",
        prompt_message_exposures=exposures,
        repeated_prompt_message_exposures=repeats,
        repeated_prompt_message_denominator=exposures,
        repeated_prompt_message_rate=repeats / exposures if exposures else None,
        prompt_message_basis="exact message JSON per dispatched model request; not inter-agent deliveries or independent evidence",
    )


def _progress(raw, snapshot, arguments):
    """First newly published required source, including charged preparation.

    Imported prefix artifacts are prior knowledge, not new branch progress.
    A receipt must match an actual settled publication and its current public
    source version at that operation. Future hidden correctness is never used.
    """
    artifacts = {a["ref"]: a for a in snapshot["artifacts"]}
    history = {h["ref"]: h for h in raw.get("artifact_history", [])}
    preparations = {p.get("artifact_ref", p.get("new_ref")): (i, p)
                    for i, p in enumerate(raw.get("preparations", []))}
    turns = {r["scheduler_turn"]: r for r in raw.get("turns", [])}
    initial = arguments.get("start_step", 0)
    if arguments.get("condition", "D2") in {"D0", "D1"}:
        initial = max(initial, tasks.UPDATE_STEP)
    for ordinal, event in enumerate(snapshot["events"]):
        if event["event_type"] != "ext.session.published":
            continue
        ref = event["lineage"]["artifact_ref"]
        if ref not in history or ref not in artifacts:
            continue
        h, artifact = history[ref], artifacts[ref]
        value = _object(artifact["value"])
        preparation_index, preparation = preparations.get(ref, (None, {}))
        if preparation.get("kind") == "prefix_import":
            continue
        turn = turns.get(h["turn"])
        if preparation.get("kind") == "supplied_current_evidence":
            phase, step, decision_turn = "preparation", initial, None
        elif turn is not None:
            phase, step, decision_turn = "rollout", turn["environment_step"], turn["turn"]
        else:
            continue
        public = tasks.public_world(raw["world_id"], step)
        required = {(s["source_id"], s["source_version"])
                    for s in public["sources"] if s["required"]}
        if (value.get("source_id"), value.get("source_version")) not in required:
            continue
        if v1.wire(value) != v1.wire(h["value"]) or not tasks.verify_artifact(raw["world_id"], value):
            raise ValueError("progress history differs from verified publication")
        return dict(phase=phase, preparation_index=preparation_index,
                    decision_turn=decision_turn, environment_step=step,
                    event_ordinal=ordinal, artifact_ref=ref,
                    source_id=value["source_id"], source_version=value["source_version"],
                    receipt_identity=value["receipt_identity"])
    return None


def _correct(raw, snapshot, arguments):
    result = deepcopy(raw)
    result["raw_method_version"] = raw.get("method_version")
    result["method_version"] = METHOD
    result["record_profile"] = "coordination_repair_episode_v2"
    result["raw_primary_failure_stage"] = raw.get("primary_failure_stage")
    errors = result.get("errors", [result["error"]] if "error" in result else [])
    for error in errors:
        error["raw_stage"] = error.get("stage")
        if error.get("type") == "PermissionError":
            error["stage"] = "capability_permission"
            error["classification_basis"] = "PermissionError; does not by itself identify which permission layer denied access"
    if errors:
        result["primary_failure_stage"] = errors[0]["stage"]
        if result.get("stop") == errors[0]["raw_stage"]:
            result["stop"] = errors[0]["stage"]
    metrics = result.get("metrics")
    configured = int(arguments.get("model") is not None)
    if snapshot is None:
        result.update(raw_status=raw["status"], status="INVALID_ABORT", success=None,
                      outcome=None, complete_rollout=False, stop="instrumentation_error")
        result.setdefault("primary_failure_stage", "runtime_lease_failure")
        if result["primary_failure_stage"] is None:
            result["primary_failure_stage"] = "runtime_lease_failure"
        result["diagnostics"] = {"status": "UNAVAILABLE", "reason": "no retained Session snapshot",
                                 "configured_inference_concurrency": configured}
        return result
    dispatched = sum(c["action"] == "model.generate" and c["state"] in _DISPATCHED
                     for c in snapshot["calls"])
    diagnostics = dict(status="OBSERVED", configured_inference_concurrency=configured,
        model_dispatches=dispatched, actual_inference_concurrency=int(dispatched > 0),
        inference_concurrency_basis="synchronous model-dispatch boundary, not measured GPU utilization",
        prefix_import_tool_dispatches=sum(c["action"] == "tool.evaluate" and c["state"] in _DISPATCHED
            and _object(c["request"]).get("tool_ref") == "import_verified_prefix" for c in snapshot["calls"]),
        first_verified_progress=_progress(raw, snapshot, arguments), **_communication(snapshot))
    result["diagnostics"] = diagnostics
    if metrics is not None:
        metrics["v1_actual_inference_concurrency"] = metrics.get("actual_inference_concurrency")
        metrics["actual_inference_concurrency"] = diagnostics["actual_inference_concurrency"]
        metrics["configured_inference_concurrency"] = configured
        metrics["first_verified_progress"] = diagnostics["first_verified_progress"]
        # The old turn-only value is preserved and explicitly narrowed.
        metrics["first_verified_progress_turn_basis"] = "v1 decision turns only; use first_verified_progress for preparation"
        metrics.update(_communication(snapshot))
    result["complete_rollout"] = (result["status"] == "VALID_KNOWN"
                                   and snapshot["unknown_calls"] == 0
                                   and result.get("stop") in _TERMINAL_STOPS)
    return result


def run_episode(**arguments):
    """Write additive episode-v2.json after the untouched v1 execution finishes."""
    raw = v1.run_episode(**arguments)
    output = Path(arguments["output"])
    raw_path = output / ("episode.json" if (output / "episode.json").exists() else "INVALID_ABORT.json")
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)  # Bind the derivative to retained JSON, including list/tuple normalization.
    snapshot_path = output / "session-snapshot.json"
    snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else raw.get("authoritative_snapshot")
    try:
        result = _correct(raw, snapshot, arguments)
    except (KeyError, TypeError, ValueError) as exc:
        # An instrumentation failure must not turn known accounting into zero.
        result = deepcopy(raw)
        result.update(method_version=METHOD, raw_method_version=raw.get("method_version"),
            record_profile="coordination_repair_episode_v2", status="INVALID_ABORT", success=None,
            outcome=None, primary_failure_stage="runtime_lease_failure", stop="instrumentation_error", complete_rollout=False,
            diagnostics={"status": "INVALID_ABORT", "type": type(exc).__name__, "reason": str(exc)})
    result.setdefault("complete_rollout", False)
    result["raw_record"] = {"file": raw_path.name, "sha256": sha256(raw_bytes).hexdigest()}
    v1.save(output / "episode-v2.json", result)
    return result


def full_rollouts(parent, *, output, model=None, campaign=None, verify_frozen=None):
    """Preserve v1 fork treatment; stop dispatching after invalid/unknown rows.

    A small new loop is required: wrapping v1.full_rollouts after it returns
    would already have dispatched later branches. Eligibility, imports, seed,
    knowledge, budget and source schedule remain the same as v1.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prefix = prepare_prefix(parent)
    v1.save(output / "prefix-v2.json", prefix)
    if not prefix["eligible"]:
        v1.save(output / "rollout-records-v2.json", [])
        return prefix, [], []
    agents = [f"agent{i}" for i in range(parent["n"])]
    optional_bytes = len(v1.wire([i["value"] for i in prefix["current_imports"]
                                 if len(i["baseline_readers"]) < len(agents)]).encode())
    remaining = max(0, parent["token_cap"] - prefix["prefix_tokens"])
    records, episodes = [], []
    halted = None if parent["status"] == "VALID_KNOWN" else "parent_" + parent["status"]
    for branch in BRANCHES:
        imports = [{**deepcopy(item), "readers": agents if branch == "relevant" else item["baseline_readers"]}
                   for item in prefix["current_imports"]]
        notes = ["UNRELATED NON-AUTHORITATIVE ARCHIVE LABEL: " + "circular " * (optional_bytes // 9)] if branch == "irrelevant" else []
        record = dict(method_version=FORK_METHOD, world_id=parent["world_id"], prefix_id=prefix["prefix_id"],
            branch=branch, parent_scope=parent["scope_id"], prefix_hash=prefix["prefix_hash"],
            prefix_tokens=prefix["prefix_tokens"], remaining_token_cap=remaining,
            remaining_steps=prefix["remaining_steps"], note_bytes=len(v1.wire(notes).encode()),
            optional_artifact_bytes=optional_bytes, counts_toward_verdict=False,
            irrelevant_matching_basis="approximate optional-artifact serialized bytes; actual prompt-token residual separately reported",
            exogenous_update_schedule="original absolute public steps")
        if halted is not None:
            record.update(status="UNSTARTED", execution_started=False, complete_rollout=False,
                          stop=halted, success=None, branch_scope=None, incremental_tokens=None,
                          unknown_calls=None, invalid_actions=None, first_prompt_tokens=None,
                          branch_setup_tool_calls=None)
        else:
            episode, execution_started = None, False
            boundary = "before_branch_source_check"
            try:
                if verify_frozen is not None:
                    verify_frozen()
                boundary = "branch_invocation_error"
                execution_started = True
                episode = run_episode(world=parent["world_id"], arm=parent["arm"], n=parent["n"],
                    output=output / branch, model=model, campaign=campaign,
                    allocation_id="fork-v2-" + v1.digest([parent["scope_id"], prefix["prefix_id"], branch])[:40],
                    steps=prefix["remaining_steps"], token_cap=remaining, seed=prefix["model_seed"],
                    start_step=prefix["next_step"], imports=imports, prefix_feedback=prefix["private_feedback"],
                    notes=notes, scheduler_offset=prefix["next_scheduler_turn"], initial_failures=prefix["failure_pressure"])
                boundary = "after_branch_source_check"
                if verify_frozen is not None:
                    verify_frozen()
            except Exception as exc:
                # Setup/sidecar failure may follow real work; never invent zero usage.
                previous = deepcopy(episode) if episode is not None else {"metrics": None}
                episode = {**previous, "method_version": METHOD, "raw_status": previous.get("status"),
                    "status": "INVALID_ABORT", "success": None, "outcome": None,
                    "complete_rollout": False, "stop": boundary,
                    "raw_episode_directory": str(output / branch),
                    "error": {"type": type(exc).__name__, "message": str(exc)}}
            metrics = episode.get("metrics")
            complete = (episode["status"] == "VALID_KNOWN" and metrics is not None
                    and metrics["unknown_calls"] == 0 and episode.get("complete_rollout", False)
                    and episode.get("stop") in _TERMINAL_STOPS)
            if episode["status"] == "VALID_KNOWN" and not complete:
                episode = {**deepcopy(episode), "raw_status": episode["status"],
                           "status": "INVALID_ABORT", "success": None, "outcome": None,
                           "stop": "incomplete_rollout", "complete_rollout": False}
            episodes.append(episode)
            record.update(status=episode["status"], execution_started=execution_started,
                complete_rollout=complete, stop=episode.get("stop"),
                success=episode["success"], branch_scope=episode.get("scope_id"),
                incremental_tokens=metrics["tokens"] if metrics else None,
                unknown_calls=metrics["unknown_calls"] if metrics else None,
                invalid_actions=metrics["invalid_actions"] if metrics else None,
                first_prompt_tokens=episode["turns"][0].get("preflight_prompt_tokens") if episode.get("turns") else None,
                branch_setup_tool_calls=episode.get("diagnostics", {}).get("prefix_import_tool_dispatches"))
            if "error" in episode:
                record["error"] = episode["error"]
            if "raw_status" in episode:
                record["raw_status"] = episode["raw_status"]
            if episode["status"] != "VALID_KNOWN" or not record["complete_rollout"]:
                halted = "collection_stopped_after_" + branch + "_" + episode["status"]
        records.append(record)
        # Keep preceding rows if a later host interruption prevents final return.
        v1.save(output / (branch + "-record-v2.json"), record)
    reference_tokens = records[0]["first_prompt_tokens"]
    for record in records:
        count = record["first_prompt_tokens"]
        record["token_length_difference_from_relevant"] = count - reference_tokens if count is not None and reference_tokens is not None else None
    v1.save(output / "rollout-records-v2.json", records)
    return prefix, records, episodes
