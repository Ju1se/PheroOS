"""Experimental one-response interface diagnostic; no coordination efficacy claim.

Every view receives the same charged current evidence. Direct answer JSON has
an explicit syntax-only wrapper; it never repairs answer content. The frozen
task validator and hidden objective retain their original meanings.
"""

from collections import Counter
from copy import deepcopy
import time

from . import coordination_repair_v1_tasks as tasks
from .coordination_repair_v1 import declarations, digest, messages, runtime, save, wire


PROFILE = "model_interface_episode_v1"
ARMS = {
    "direct_json_256": {"view": "direct", "max_new_tokens": 256},
    "compact_action_256": {"view": "compact", "max_new_tokens": 256},
    "envelope_256": {"view": "envelope", "max_new_tokens": 256},
    "envelope_1024": {"view": "envelope", "max_new_tokens": 1024},
}
CONTEXT_TOKENS = 2048


def _current(world, materialized):
    public = tasks.public_world(world, tasks.UPDATE_STEP)
    required = [s for s in public["sources"] if s["required"]]
    if (type(materialized) is not list or len(materialized) != len(required)
            or any(not tasks.verify_artifact(world, r) for r in materialized)):
        raise ValueError("complete verified current evidence required")
    by_source = {r["source_id"]: r for r in materialized}
    if len(by_source) != len(materialized) or set(by_source) != {s["source_id"] for s in required}:
        raise ValueError("duplicate or missing evidence source")
    current = [by_source[s["source_id"]] for s in required]
    if any(r["source_version"] != s["source_version"] for r, s in zip(current, required)):
        raise ValueError("stale evidence cannot enter a current diagnostic")
    return public, current


def build_messages(world, arm, materialized):
    public, evidence = _current(world, materialized)
    view = ARMS[arm]["view"]
    citations = [{k: r[k] for k in ("source_id", "source_version")} for r in evidence]
    if view == "envelope":
        return messages(public, "agent0", "submit", evidence, [], submit_only=True,
                        attention=list(reversed(citations)))
    payload = {"world_id": world, "task_version": public["task_version"], "question": public["rule"],
               "answer_shape": public["action_schema"]["submit"]["answer"],
               "sources": [{k: r[k] for k in ("source_id", "source_version", "content")} for r in evidence]}
    for key in ("requested_key", "item_ids", "task_ids"):
        if key in public:
            payload[key] = public[key]
    instruction = "Solve the question using the supplied sources. Return only the JSON answer object matching answer_shape. No Markdown. Do not repeat the question or sources."
    if view == "compact":
        payload["required_citations"] = citations
        instruction = ('Solve the question using the supplied sources. Return exactly one JSON object with '
                       'action="submit", answer matching answer_shape, and citations equal to the required_citations array. '
                       'No extra fields or Markdown. Do not repeat the question or sources.')
    return [{"role": "system", "content": instruction}, {"role": "user", "content": wire(payload)}]


def validate_response(world, arm, raw, materialized):
    """A metered tool: add syntax only, then use the unchanged public validator."""
    direct = ARMS[arm]["view"] == "direct"
    origin = "runtime_supplied" if direct else "model_supplied"
    extra = {"citations_origin": origin, "compiled_action": None}
    if direct:
        try:
            answer, framing = tasks._parse(raw)
        except (ValueError, TypeError, RecursionError) as exc:
            return dict(valid=False, stage="transport_format", feedback=str(exc), artifact=None,
                        normalized_action=None, framing=None, **extra)
        public = tasks.public_world(world, tasks.UPDATE_STEP)
        if not tasks._answer_schema(public, answer):
            return dict(valid=False, stage="action_schema", feedback="Return exactly the declared answer object.",
                        artifact=None, normalized_action=None, framing=framing, **extra)
        # Sources come only from actual materialization. Wrong, absent, duplicate
        # or stale receipts still fail the common validator below.
        action = {"action": "submit", "answer": answer,
                  "citations": [{k: r.get(k) for k in ("source_id", "source_version")}
                                for r in materialized]}
        raw = wire(action)
        extra["compiled_action"] = deepcopy(action)
    parsed = tasks.parse_action(world, tasks.UPDATE_STEP, raw)
    if parsed["valid"] and parsed["normalized_action"]["action"] != "submit":
        return {**parsed, "valid": False, "stage": "action_schema",
                "feedback": "This supplied-evidence diagnostic requires one submission.", **extra}
    return {**tasks.execute(world, tasks.UPDATE_STEP, raw, materialized), **extra}


def run_episode(*, world, arm, seed, output, model, campaign, allocation_id, instrument_only=False):
    """Exactly one attempted model response, through common metered Session APIs."""
    if arm not in ARMS or type(seed) is not int or seed < 0:
        raise ValueError("undeclared interface arm or seed")
    from pathlib import Path

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    public = tasks.public_world(world, tasks.UPDATE_STEP)
    sources, work, inspections = declarations(world, ["agent0"], 1, tasks.UPDATE_STEP, [])
    Session, Driver, Guard = runtime()
    limits = campaign.allocate(allocation_id, output / "session.sqlite", token_cap=2048,
                               max_calls=len(sources) + 3, model_dispatches=1)
    session = None
    prompt, evidence, preparations, response, validation, error = None, [], [], None, None, None
    preflight_tokens = None
    started = time.monotonic_ns()
    stage = "runtime_lease_failure"
    publications = 0
    try:
        session = Session.create(output / "session.sqlite", allocation_id, agents=["agent0"],
            work=work, sources=sources, inspections=inspections, **limits,
            context_bytes=65536, artifact_bytes=65536, max_index_entries=64,
            max_control_operations=1024, manifest_items=8, manifest_bytes=8192,
            feedback_bytes=512, feedback_items=2)
        def source_tool(arguments):
            if arguments["world"] != world:
                raise ValueError("source request belongs to another world")
            result = tasks.inspect(world, tasks.UPDATE_STEP, arguments["source_id"])
            if result["source_version"] != arguments["source_version"]:
                raise ValueError("source version changed before inspection")
            return result

        driver = Driver(session, models={"study_model": model}, tools={
            "inspect_source": source_tool,
            "validate_response": lambda a: validate_response(world, arm, a["raw"], a["materialized"])},
            context_tokens=CONTEXT_TOKENS)
        guarded = Guard(driver, campaign, allocation_id)
        observer = session.claim("agent0", "observe-agent0", lease_seconds=600)
        for source in public["sources"]:
            if not source["required"]:
                continue
            name = f"inspect-1-{source['source_id']}-v{source['source_version']}"
            claim = session.claim_inspection("agent0", name, reuse=False)
            lease = claim["lease"]
            call_id = "prepare-" + source["source_id"]
            reply = driver.evaluate(lease, call_id, "inspect_source", {
                "world": world, "source_id": source["source_id"], "source_version": source["source_version"]})
            ref = session.publish(lease, call_id, reply["artifact"],
                verify=lambda _, value: tasks.verify_artifact(world, value), authorize=driver.authorization)
            publications += 1
            preparations.append({"source_id": source["source_id"], "source_version": source["source_version"],
                                 "artifact_ref": ref, "call_id": call_id})
            evidence.append(session.read(observer, ref, authorize=driver.authorization)["value"])
        prompt = build_messages(world, arm, evidence)
        stage = "context_preflight"
        preflight_tokens = model.count_tokens(prompt)
        maximum = ARMS[arm]["max_new_tokens"]
        if type(preflight_tokens) is not int or preflight_tokens < 1 or preflight_tokens + maximum > CONTEXT_TOKENS:
            raise ValueError("full evidence plus declared output does not fit; no evidence eviction")
        lease = session.claim("agent0", "decision-0", lease_seconds=600)
        stage = "model_dispatch"
        response = guarded.generate(lease, "model-0", "study_model", prompt, max_new_tokens=maximum, seed=seed)
        stage = "public_validation"
        arguments = {"raw": response.get("text"), "materialized": evidence}
        reply = driver.evaluate(lease, "validate-0", "validate_response", arguments)
        validation = reply["artifact"]
        session.publish(lease, "validate-0", validation,
            verify=lambda _, value: wire(value) == wire(validate_response(world, arm, arguments["raw"], evidence)),
            authorize=driver.authorization)
        publications += 1
    except Exception as exc:
        error = {"stage": "capability_permission" if isinstance(exc, PermissionError) else stage,
                 "type": type(exc).__name__, "message": str(exc)}
    finally:
        if session is not None:
            session.cancel()
    snapshot = session.snapshot() if session is not None else None
    coordination = session.coordination_snapshot() if session is not None else None
    status = "INVALID_ABORT" if error else "VALID_KNOWN"
    if snapshot and snapshot["unknown_calls"] and error is None:
        status = "VALID_UNRESOLVED"
    metrics = None
    if snapshot:
        observed = [c for c in snapshot["calls"] if c["state"] in {"received", "response_rejected", "dispatched"}]
        models = [c for c in observed if c["action"] == "model.generate"]
        metrics = dict(model_calls=len(models), tool_calls=sum(c["action"] == "tool.evaluate" for c in observed),
            known_tokens=snapshot["actual_tokens"], unknown_tokens=snapshot["unknown_tokens"], unknown_calls=snapshot["unknown_calls"],
            input_tokens=sum(c["prompt"] for c in models if c["actual"] is not None),
            output_tokens=sum(c["actual"] - c["prompt"] for c in models if c["actual"] is not None),
            control_operations=len(snapshot["events"]) + publications,
            verification_operations=publications, preparation_tools=len(preparations),
            event_bytes=len(wire(snapshot["events"]).encode()),
            model_prompt_bytes=len(wire(prompt).encode()) if prompt else None,
            materialized_bytes=coordination["materialized_bytes"], coordination_request_bytes=coordination["request_bytes"],
            elapsed_ns=time.monotonic_ns() - started, monetary_cost=None,
            monetary_cost_status="not_measured_local_inference" if not instrument_only else "not_applicable_scripted_instrument")
        metrics["call_units"] = metrics["model_calls"] + metrics["tool_calls"] + metrics["control_operations"]
        save(output / "session-snapshot.json", snapshot)
        save(output / "coordination-accounting.json", coordination)
        try:
            campaign.reconcile(allocation_id)
        except Exception as exc:
            status = "INVALID_ABORT"
            error = error or {"stage": "accounting", "type": type(exc).__name__, "message": str(exc)}
    accepted = validation["valid"] if status == "VALID_KNOWN" else None
    submission = validation["artifact"] if validation and validation["valid"] else None
    # Hidden scoring runs only after the single-response execution is terminal.
    success = tasks.score(world, tasks.UPDATE_STEP, submission) if status == "VALID_KNOWN" else None
    result = dict(profile=PROFILE, world_id=world, family=world.split("/")[0], arm=arm, seed=seed, n=1,
        status=status, complete=status == "VALID_KNOWN", counts_toward_verdict=False, instrument_only=instrument_only,
        model_identity=model.identity, max_new_tokens=ARMS[arm]["max_new_tokens"], context_tokens=CONTEXT_TOKENS,
        stop="single_response_complete" if status == "VALID_KNOWN" else "collection_stopped",
        messages=prompt, prompt_sha256=digest(prompt) if prompt else None, preflight_prompt_tokens=preflight_tokens,
        materialized=evidence, preparations=preparations, response=response, validation=validation,
        public_accepted=accepted, objective_success=success, submission=submission,
        citations_origin="runtime_supplied" if ARMS[arm]["view"] == "direct" else "model_supplied",
        model_citation_selection_measured=ARMS[arm]["view"] != "direct",
        output_at_cap=(response["completion_tokens"] == ARMS[arm]["max_new_tokens"]) if response else None,
        error=error, metrics=metrics)
    save(output / "episode.json", result)
    return result


def summarize(records, expected):
    """No valid subset estimate and no new capability admission threshold."""
    identities = [(r["world_id"], r["arm"], r["seed"]) for r in records]
    declared = [(r["world"], r["arm"], r["seed"]) for r in expected]
    valid = (len(identities) == len(set(identities)) and set(identities) == set(declared)
             and all(r["status"] == "VALID_KNOWN" and r["complete"] for r in records))
    base = dict(profile="model_interface_descriptive_v1", counts_toward_verdict=False,
                collaboration_admitted=False, independent_unit="world; seeds are repeated observations within world")
    if not valid:
        return {**base, "status": "INVALID", "reason": "incomplete, duplicate or unresolved declared grid",
                "retained_rows": len(records), "declared_rows": len(expected), "effects": None}
    groups = {}
    for arm in ARMS:
        rows = [r for r in records if r["arm"] == arm]
        groups[arm] = dict(episodes=len(rows), worlds=len({r["world_id"] for r in rows}),
            public_accepted=sum(r["public_accepted"] for r in rows), objective_successes=sum(r["objective_success"] for r in rows),
            output_cap_hits=sum(r["output_at_cap"] for r in rows),
            failure_stages=dict(Counter(r["validation"]["stage"] for r in rows if not r["public_accepted"])),
            totals={k: sum(r["metrics"][k] for r in rows) for k in (
                "model_calls", "tool_calls", "known_tokens", "input_tokens", "output_tokens", "control_operations", "call_units")})
    return {**base, "status": "VALID_KNOWN", "groups": groups,
            "worlds": {w: {a: dict(public_accepted_mean=sum(r["public_accepted"] for r in records if r["world_id"] == w and r["arm"] == a) / sum(r["world_id"] == w and r["arm"] == a for r in records),
                                       objective_success_mean=sum(r["objective_success"] for r in records if r["world_id"] == w and r["arm"] == a) / sum(r["world_id"] == w and r["arm"] == a for r in records))
                            for a in ARMS} for w in sorted({r["world_id"] for r in records})}}
