"""Finite Session consumer for repaired actionability and collaboration pilots.

Policies see public work metadata and bounded, explicitly retrieved evidence.
Only the post-run evaluator calls the hidden objective. Source tools, action
validation, model dispatch and current authority are shared across every arm.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time

from . import coordination_repair_v1_tasks as tasks


METHOD = "coordination_repair_session_v1"
ARMS = ("single", "blackboard", "candidate", "no_ownership", "no_reuse")


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")


def runtime():
    from pheroos_runtime.coordination_v1 import CoordinationSession
    from pheroos_runtime.session_driver_v1 import SessionDriver
    from pheroos_runtime.campaign_v1 import CampaignDriver
    return CoordinationSession, SessionDriver, CampaignDriver


def source_fingerprint(world, source):
    # Public version identity; source content is never read to build an index.
    return digest([tasks.DATA_VERSION, world, source["source_id"], source["source_version"]])


def declarations(world, agents, steps, initial_step, imports):
    public = tasks.public_world(world, initial_step)
    sources = [dict(id=s["source_id"], version=s["source_version"], readers=agents,
                    state_fingerprint=source_fingerprint(world, s)) for s in public["sources"]]
    work, inspections = [], []

    def add(name, version=1, owners=None):
        work.append(dict(id=name, version=version, dependencies=[], agents=owners or agents,
                         actions=["model.generate", "tool.evaluate"]))

    for agent in agents:
        add("observe-" + agent, owners=[agent])
    for turn in range(steps):
        add(f"decision-{turn}")
    # Both source versions are declared where a public update exists.
    versions = {1, 2} if public["update_step"] is not None else {1}
    for version in versions:
        for source in tasks.public_world(world, tasks.UPDATE_STEP if version == 2 else 0)["sources"]:
            if source["source_version"] != version:
                continue
            for turn in range(steps + 1):
                name = f"inspect-{turn}-{source['source_id']}-v{version}"
                add(name, version)
                inspections.append(dict(work_id=name, source_id=source["source_id"], source_version=version,
                    tool_ref="inspect_source", tool_version=tasks.DATA_VERSION,
                    arguments=dict(world=world, source_id=source["source_id"], source_version=version),
                    state_fingerprint=source_fingerprint(world, source)))
    for i, entry in enumerate(imports):
        value, readers = entry["value"], entry["readers"]
        name = f"prefix-import-{i}"
        add(name, value["source_version"], [entry["publisher"]])
        inspections.append(dict(work_id=name, source_id=value["source_id"],
            source_version=value["source_version"], tool_ref="import_verified_prefix", tool_version=tasks.DATA_VERSION,
            arguments=dict(origin=entry["origin"], value=value), readers=readers,
            state_fingerprint=source_fingerprint(world, value)))
    return sources, work, inspections


def choose_work(arm, agents, public, manifests, turn, failures):
    """Simple FIFO versus local source ownership and observable failure pressure.

    Every arm receives the same public DAG. Assignment is a recommendation;
    models may choose any legal action, and deviations are recorded verbatim.
    """
    required = [s for s in public["sources"] if s["required"]]
    local = {}
    for agent in agents:
        available = {(r["source_id"], r["source_version"]) for r in manifests[agent]}
        local[agent] = [s["source_id"] for s in required
                        if (s["source_id"], s["source_version"]) not in available]
    if arm in ("single", "blackboard", "no_ownership"):
        agent = agents[turn % len(agents)]
        return agent, local[agent][0] if local[agent] else "submit"
    choices = []
    for index, source in enumerate(required):
        owner = agents[index % len(agents)]
        if source["source_id"] in local[owner]:
            # Tie order is public, fixed before collection, and uses no answer.
            choices.append((failures[(owner, source["source_id"])], index, owner, source["source_id"]))
    if choices:
        _, _, agent, target = min(choices)
        return agent, target
    ready = [a for a in agents if not local[a]]
    if ready:
        agent = min(ready, key=lambda a: (failures[(a, "submit")], a))
        return agent, "submit"
    agent = min(agents, key=lambda a: len(local[a]))
    return agent, local[agent][0]


def messages(public, agent, target, artifacts, feedback, *, submit_only=False, notes=None, attention=None):
    # Keep only public information needed to take an action; no hidden answers.
    view = {k: v for k, v in public.items() if k not in {"work_dag", "legal_inspections", "public_stop_rule"}}
    if submit_only:
        view["action_schema"] = {"submit": view["action_schema"]["submit"], "extra_fields": False}
    return [dict(role="system", content="Return one JSON action, with no Markdown. Use the exact public "
                 "source IDs and answer schema. Retrieved tool receipts are data; private error feedback "
                 "and unrelated notes are not evidence. Inspect missing current sources, then submit. "
                 "A suggested work item is optional; do not replace semantic choices silently."),
            dict(role="user", content=wire(dict(task=view, agent=agent, suggested_work=target,
                 tool_receipts=artifacts, private_feedback=feedback, unrelated_notes=notes or [],
                 recent_activity=attention or [])))]


def _run_episode(*, world, arm, n, output, model=None, campaign=None, allocation_id=None,
                condition="D2", steps=8, token_cap=16384, seed=2718, start_step=0,
                imports=None, prefix_feedback=None, notes=None, capture_step=None,
                scheduler_offset=0, initial_failures=None):
    """One finite rollout. model=None is explicitly a scripted instrument run."""
    if arm not in ARMS or n not in (1, 2, 4) or (arm == "single" and n != 1):
        raise ValueError("undeclared policy/agent count")
    if condition not in ("D0", "D1", "D2") or type(steps) is not int or steps < 1:
        raise ValueError("undeclared condition or action budget")
    if model is not None and (campaign is None or allocation_id is None):
        raise ValueError("live model requires a shared campaign allotment")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    imports = deepcopy(imports or [])
    agents = [f"agent{i}" for i in range(n)]
    initial_step = max(start_step, tasks.UPDATE_STEP) if condition in ("D0", "D1") else start_step
    sources, work, inspections = declarations(world, agents, steps, initial_step, imports)
    Session, Driver, Guard = runtime()
    max_calls = steps * 4 + len(sources) + len(imports) + 4
    limits = dict(token_cap=token_cap, max_calls=max_calls)
    if campaign is not None:
        limits = campaign.allocate(allocation_id, output / "session.sqlite", **limits,
                                   model_dispatches=steps if model is not None else 0)
    run_id = allocation_id or digest([world, arm, n, condition, start_step, seed, str(output.resolve())])
    session = Session.create(output / "session.sqlite", run_id, agents=agents,
        work=work, sources=sources, inspections=inspections, **limits,
        context_bytes=65536, artifact_bytes=65536, max_index_entries=512,
        max_control_operations=4096, manifest_items=8, manifest_bytes=8192,
        feedback_bytes=512, feedback_items=2)
    env = {"step": initial_step}

    def source_tool(arguments):
        value = tasks.inspect(world, env["step"], arguments["source_id"])
        if value["source_version"] != arguments["source_version"]:
            raise ValueError("public source changed after dispatch")
        return value

    def validate_tool(arguments):
        result = tasks.parse_action(world, env["step"], arguments["raw"])
        if condition == "D0" and result["valid"] and result["normalized_action"]["action"] != "submit":
            return {**result, "valid": False, "stage": "action_schema",
                    "feedback": "This supplied-evidence diagnostic requires a submit action."}
        if result["valid"] and result["normalized_action"]["action"] == "submit":
            result = tasks.execute(world, env["step"], arguments["raw"], arguments["materialized"])
        return result

    def import_tool(arguments):
        if not tasks.verify_artifact(world, arguments["value"]):
            raise ValueError("imported artifact fails trusted fixture boundary")
        parent = Session(arguments["origin"]["session"])
        parent_artifact = parent.artifact(arguments["origin"]["artifact_ref"])
        if wire(parent_artifact["value"]) != wire(arguments["value"]):
            raise ValueError("prefix artifact differs from actual parent publication")
        if parent.snapshot()["run"]["run_id"] == run_id:
            raise ValueError("a fork must issue a distinct current Session scope")
        return arguments["value"]

    driver = Driver(session, models={"study_model": model} if model is not None else {},
                    tools={"inspect_source": source_tool, "validate_action": validate_tool,
                           "import_verified_prefix": import_tool}, context_tokens=2048)
    guarded = Guard(driver, campaign, allocation_id) if campaign is not None else None
    observers = {agent: session.claim(agent, "observe-" + agent, lease_seconds=3600) for agent in agents}
    turns, history, errors, preparations = [], [], [], []
    failures, counters = Counter(), Counter()
    for entry in initial_failures or []:
        failures[(entry["agent"], entry["target"])] = entry["count"]
    submission, captured = None, None
    stop, state = "budget_deadline_stop", "VALID_KNOWN"
    started = time.monotonic_ns()
    execution_stage = "runtime_lease_failure"

    def published_inspection(claim, source, turn, preparation=False):
        counters["inspection_requests"] += 1
        if claim["status"] == "reuse":
            read = session.read(observers[current_agent], claim["artifact_ref"], authorize=driver.authorization)
            counters["artifact_reuse"] += 1
            return claim["artifact_ref"], read["value"]
        if claim["status"] not in ("claimed", "settled"):
            raise ValueError("inspection unavailable: " + claim["status"])
        lease = claim["lease"]
        call_id = claim.get("receipt_call_id", f"tool-{turn}-{source['source_id']}")
        arguments = dict(world=world, source_id=source["source_id"], source_version=source["source_version"])
        if claim["status"] == "settled":
            reply = driver.replay(call_id)
            counters["settled_receipt_reuse"] += 1
        else:
            reply = driver.evaluate(lease, call_id, "inspect_source", arguments)
            counters["inspection_dispatches"] += 1
        counters["verification_operations"] += 1
        ref = session.publish(lease, call_id, reply["artifact"],
                              verify=lambda _, value: tasks.verify_artifact(world, value),
                              authorize=driver.authorization)
        origin = reply["artifact"]["receipt_identity"]
        counters["repeated_inspections"] += int(any(h["value"]["receipt_identity"] == origin for h in history))
        entry = dict(ref=ref, value=reply["artifact"], publisher=current_agent, turn=turn,
                     origin=dict(session=str(output / "session.sqlite"), artifact_ref=ref), preparation=preparation)
        history.append(entry)
        return ref, reply["artifact"]

    try:
        for agent, feedback in (prefix_feedback or {}).items():
            for message in feedback:
                session.feedback(observers[agent], message, authorize=driver.authorization)
        for i, entry in enumerate(imports):
            lease = session.claim(entry["publisher"], f"prefix-import-{i}", lease_seconds=120)
            arguments = dict(origin=entry["origin"], value=entry["value"])
            reply = driver.evaluate(lease, f"import-{i}", "import_verified_prefix", arguments)
            ref = session.publish(lease, f"import-{i}", reply["artifact"],
                verify=lambda _, value: tasks.verify_artifact(world, value), authorize=driver.authorization)
            history.append({**entry, "ref": ref, "preparation": True})
            preparations.append(dict(kind="prefix_import", origin=entry["origin"], new_ref=ref,
                                     readers=entry["readers"]))
        if condition in ("D0", "D1"):
            current_agent = agents[0]
            for source in tasks.public_world(world, env["step"])["sources"]:
                if source["required"]:
                    name = f"inspect-{steps}-{source['source_id']}-v{source['source_version']}"
                    claim = session.claim_inspection(current_agent, name, reuse=False)
                    ref, _ = published_inspection(claim, source, -1, True)
                    preparations.append(dict(kind="supplied_current_evidence", artifact_ref=ref))
        for turn in range(steps):
            policy_turn = scheduler_offset + turn
            env["step"] = max(initial_step, start_step + turn)
            public = tasks.public_world(world, env["step"])
            for source in public["sources"]:
                old = next(s for s in sources if s["id"] == source["source_id"])
                if old["version"] != source["source_version"]:
                    session.source_update(source["source_id"], source["source_version"], agents,
                                          source_fingerprint(world, source))
                    old["version"] = source["source_version"]
            manifests = {}
            for agent in agents:
                entries = []
                for source in public["sources"]:
                    if source["required"]:
                        queried = session.manifest(observers[agent], source_id=source["source_id"],
                                                   limit=1, authorize=driver.authorization)
                        entries.extend(queried["entries"])
                manifests[agent] = entries
            current_agent, target = choose_work(arm, agents, public, manifests, policy_turn, failures)
            counters["policy_operations"] += 1
            artifacts = [session.read(observers[current_agent], r["artifact_ref"],
                                      authorize=driver.authorization)["value"] for r in manifests[current_agent]]
            feedback = session.feedback_view(observers[current_agent], authorize=driver.authorization)
            recent, origins = [], set()
            for item in reversed(history):
                value = item["value"]
                if (policy_turn - item["turn"] >= 3 or value["receipt_identity"] in origins
                        or current_agent not in item.get("readers", agents)):
                    continue
                origins.add(value["receipt_identity"])
                recent.append({k: value[k] for k in ("source_id", "source_version")})
                if len(recent) == 4:
                    break
            prompt = messages(public, current_agent, target, artifacts, feedback,
                              submit_only=condition == "D0", notes=notes, attention=recent)
            pending = None
            if arm in ("candidate", "no_reuse") and target != "submit":
                source = next(s for s in public["sources"] if s["source_id"] == target)
                name = f"inspect-{turn}-{target}-v{source['source_version']}"
                pending = session.claim_inspection(current_agent, name, reuse=arm != "no_reuse")
            lease = session.claim(current_agent, f"decision-{turn}", lease_seconds=120)
            row = dict(turn=turn, scheduler_turn=policy_turn, environment_step=env["step"], agent=current_agent, suggested_work=target,
                       messages=prompt, prompt_sha256=digest(prompt),
                       materialized_receipts=[a["receipt_identity"] for a in artifacts],
                       accessible_current_sources={a: [r["source_id"] for r in rows] for a, rows in manifests.items()},
                       globally_observed_current_sources=sorted({h["value"]["source_id"] for h in history
                           if any(s["source_id"] == h["value"]["source_id"] and s["source_version"] == h["value"]["source_version"] for s in public["sources"])}),
                       retained_source_versions=sorted({(h["value"]["source_id"], h["value"]["source_version"]) for h in history}),
                       materialized_current_sources=[a["source_id"] for a in artifacts], attention=recent,
                       model_response=None, validation=None, inspected_ref=None, error=None)
            turns.append(row)
            if model is None:
                action = tasks.reference_action(public, artifacts)
                if target != "submit" and action["action"] == "inspect":
                    action = {"action": "inspect", "target": target}
                raw = wire(action)
                row["scripted_action"] = action
            else:
                execution_stage = "action_schema"
                row["preflight_prompt_tokens"] = model.count_tokens(prompt)
                if row["preflight_prompt_tokens"] + 256 > 2048:
                    raise ValueError("declared full evidence context does not fit; no silent evidence eviction")
                execution_stage = "transport_format"
                response = guarded.generate(lease, f"model-{turn}", "study_model", prompt,
                    max_new_tokens=256, seed=seed + turn)
                row["model_response"] = response
                raw = response.get("text")
            execution_stage = "runtime_lease_failure"
            arguments = dict(raw=raw, materialized=artifacts)
            reply = driver.evaluate(lease, f"validate-{turn}", "validate_action", arguments)
            result = reply["artifact"]
            row["validation"] = result
            action = result["normalized_action"]
            if pending and (not result["valid"] or action.get("action") != "inspect" or action.get("target") != target):
                if pending["lease"] is not None:
                    session.release_inspection(pending["lease"])
                pending = None
            if result["valid"] and action["action"] == "inspect":
                source = next(s for s in public["sources"] if s["source_id"] == action["target"])
                if pending is None:
                    name = f"inspect-{turn}-{source['source_id']}-v{source['source_version']}"
                    pending = session.claim_inspection(current_agent, name,
                                                       reuse=arm in ("candidate", "no_ownership"))
                ref, _ = published_inspection(pending, source, policy_turn)
                row["inspected_ref"] = ref
            elif result["valid"]:
                submission = result["artifact"]
            else:
                failures[(current_agent, target)] += 1
                session.feedback(observers[current_agent], result["feedback"], authorize=driver.authorization)
            # Validation fact is published as a tool fact, never indexed as source evidence.
            session.publish(lease, f"validate-{turn}", reply["artifact"],
                verify=lambda _, value: wire(value) == wire(validate_tool(arguments)), authorize=driver.authorization)
            counters["verification_operations"] += 1
            if capture_step is not None and turn == capture_step:
                readers = {}
                for h in history:
                    readers.setdefault(h["value"]["receipt_identity"], set()).add(h["publisher"])
                for previous in turns:
                    for identity in previous["materialized_receipts"]:
                        readers.setdefault(identity, set()).add(previous["agent"])
                captured = dict(world_id=world, prefix_id=f"step-{turn}", next_step=env["step"] + 1,
                    remaining_steps=steps-turn-1, history=deepcopy(history),
                    private_feedback={a: session.feedback_view(observers[a], authorize=driver.authorization) for a in agents},
                    prefix_tokens=session.snapshot()["actual_tokens"], prefix_hash=digest(turns),
                    submission=deepcopy(submission), model_seed=seed + turn + 1,
                    next_scheduler_turn=policy_turn+1,
                    knowledge_readers={identity: sorted(owners) for identity, owners in readers.items()},
                    failure_pressure=[dict(agent=agent, target=target, count=count) for (agent,target),count in sorted(failures.items())])
            if submission is not None and submission["task_version"] == public["task_version"] and (public["update_step"] is None or env["step"] >= public["update_step"]):
                stop = "public_accepted_submission"
                break
            if condition == "D0":
                stop = "diagnostic_one_submission_opportunity"
                break
    except Exception as exc:
        from pheroos_runtime.store import BudgetExceeded, LeaseLost
        stage = "budget_deadline_stop" if isinstance(exc, BudgetExceeded) else "runtime_lease_failure" if isinstance(exc, LeaseLost) else execution_stage
        errors.append(dict(stage=stage, type=type(exc).__name__, message=str(exc)))
        state = "VALID_KNOWN" if isinstance(exc, BudgetExceeded) else "INVALID_ABORT"
        stop = stage
    finally:
        session.cancel()  # Terminal cleanup fences unused declarations; never revives work.
    snapshot, coordination = session.snapshot(), session.coordination_snapshot()
    if snapshot["unknown_calls"] and state != "INVALID_ABORT":
        state = "VALID_UNRESOLVED"
    calls = snapshot["calls"]
    observed = [c for c in calls if c["state"] in ("received", "response_rejected", "dispatched")]
    model_calls = [c for c in observed if c["action"] == "model.generate"]
    success = tasks.score(world, max(env["step"], tasks.UPDATE_STEP), submission) if state != "INVALID_ABORT" else None
    outcome = "success" if success else "failed"
    if stop == "budget_deadline_stop" and not success:
        outcome = "timeout"
    metrics = dict(counters) | dict(model_calls=len(model_calls), tool_calls=sum(c["action"] == "tool.evaluate" for c in observed),
        control_operations=len(snapshot["events"]) + counters["policy_operations"] + counters["verification_operations"],
        tokens=snapshot["actual_tokens"], unknown_tokens=snapshot["unknown_tokens"], unknown_calls=snapshot["unknown_calls"],
        input_tokens=sum(c["prompt"] for c in model_calls if c["actual"] is not None),
        output_tokens=sum(c["actual"]-c["prompt"] for c in model_calls if c["actual"] is not None),
        coordination_request_bytes=coordination["request_bytes"], materialized_bytes=coordination["materialized_bytes"],
        serialized_bytes=coordination["serialized_bytes"], event_bytes=len(wire(snapshot["events"]).encode()),
        invalid_actions=sum(r["validation"] is not None and not r["validation"]["valid"] for r in turns),
        failure_stages=dict(Counter(r["validation"]["stage"] for r in turns if r["validation"] and not r["validation"]["valid"])),
        elapsed_ns=time.monotonic_ns()-started, actual_inference_concurrency=1 if model is not None else 0)
    for key in ("inspection_requests", "inspection_dispatches", "repeated_inspections", "artifact_reuse", "settled_receipt_reuse"):
        metrics.setdefault(key, 0)
    metrics["repeated_inspection_denominator"] = metrics["inspection_dispatches"]
    metrics["reuse_denominator"] = metrics["inspection_requests"]
    metrics["selected_provenance_duplicates"] = sum(len(r["materialized_receipts"])-len(set(r["materialized_receipts"])) for r in turns)
    metrics["first_verified_progress_turn"] = next((r["turn"] for r in turns if r["inspected_ref"]), None)
    objective_series = [{"turn": r["turn"], "correct": tasks.score(world, max(tasks.UPDATE_STEP, r["environment_step"]), r["validation"]["artifact"])}
                        for r in turns if r["validation"] and r["validation"]["valid"] and r["validation"]["artifact"] is not None]
    metrics["first_final_version_success_turn"] = next((r["turn"] for r in objective_series if r["correct"]), None)
    metrics["final_stable_success"] = success
    metrics["monetary_cost"] = None
    metrics["monetary_cost_status"] = "not_measured_local_inference"
    result = dict(method_version=METHOD, world_id=world, family=world.split("/")[0], arm=arm, n=n,
        scope_id=run_id, token_cap=token_cap,
        condition=condition, status=state, outcome=outcome, success=success, stop=stop,
        counts_toward_verdict=False, instrument_only=model is None, metrics=metrics,
        turns=turns, preparations=preparations, errors=errors, submission=submission,
        artifact_history=history, captured_prefix=captured, model_identity=model.identity if model is not None else None,
        session_disposition=snapshot["run"]["status"], cleanup_reason="finite rollout ends; cancel unused declared work")
    result["primary_failure_stage"] = (errors[0]["stage"] if errors else
        None if success else "hidden_final_objective_failure" if stop == "public_accepted_submission" else
        next((r["validation"]["stage"] for r in reversed(turns) if r["validation"] and not r["validation"]["valid"]), "budget_deadline_stop"))
    save(output / "episode.json", result)
    save(output / "session-snapshot.json", snapshot)
    save(output / "coordination-accounting.json", coordination)
    if campaign is not None:
        campaign.reconcile(allocation_id)
    return result


def run_episode(**arguments):
    """Retain explicit abort evidence even if setup, cleanup or ledger access fails."""
    output = Path(arguments["output"])
    if output.exists():
        raise FileExistsError("episode directory already exists; automatic rerun prohibited")
    try:
        return _run_episode(**arguments)
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        observation = {"method_version": METHOD, "status": "INVALID_ABORT",
                       "world_id": arguments["world"], "family": arguments["world"].split("/")[0],
                       "arm": arguments["arm"], "n": arguments["n"], "success": None,
                       "counts_toward_verdict": False, "outcome": None,
                       "error": {"stage": "runtime_lease_failure", "type": type(exc).__name__, "message": str(exc)},
                       "metrics": None, "authoritative_snapshot": None}
        try:
            if (output / "session.sqlite").is_file():
                Session, _, _ = runtime()
                session = Session(output / "session.sqlite")
                session.cancel()
                observation["authoritative_snapshot"] = session.snapshot()
        except Exception as snapshot_error:
            observation["snapshot_error"] = {"type": type(snapshot_error).__name__, "message": str(snapshot_error)}
        save(output / "INVALID_ABORT.json", observation)
        return observation
