"""Exact-input offline replay of the retained visibility v1 and factorial v2.

Rebuild projections with extracted policies, source values with fixture tools,
and actions/scores from recorded raw outputs. Historical SQLite is read-only.
Legacy authority fields are retained provenance, not reissued or revalidated.
No provider, credential, adapter, historical import, or new billing ledger is used.
"""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from . import factorial, visibility
from .accounting import CACHED_RATE, CNY_UNITS, INPUT_RATE, OUTPUT_RATE, PRICE_VERSION
from .evaluation import score_v1, score_v2
from .fixtures import source_values_v1, source_values_v2


class ReplayMismatch(ValueError):
    """A recorded boundary differs from the extracted, reconstructed behavior."""


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(value):
    return sha256(_wire(value).encode()).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text())


def _save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def _equal(actual, expected, boundary):
    # Canonical JSON also distinguishes booleans, numbers and container types.
    if _wire(actual) != _wire(expected):
        raise ReplayMismatch(boundary)


def _decoded_call(row):
    return {**row, "request": json.loads(row["request"]),
            "response": json.loads(row["response"]) if row["response"] else None}


def _fixture(world, body, v2):
    if v2:
        return source_values_v2(world, body["source_version"])[body["source_id"]]
    # v1's only advancing source is factor in shared_update; inspect its declared
    # version, not the final world's oracle answer.
    round_index = 0 if world == "shared_update" and body["source_version"] == 1 else 1
    return source_values_v1(world, round_index)[body["source_id"]]


def _roots(world, v2):
    result = [dict(id="root:task:" + world, kind="root", owner="host", readers=["a", "b"],
                   round_index=0 if v2 else -1, body={}, parents=[], provenance_known=True)]
    values = ([source_values_v2(world, v) for v in (1, 2)] if v2 else
              [source_values_v1(world, r) for r in (0, 1, 2)])
    for group in values:
        for body in group.values():
            identifier = f"root:{world}:{body['source_id']}:v{body['source_version']}"
            if any(r["id"] == identifier for r in result):
                continue
            result.append(dict(id=identifier, kind="root", owner="host", readers=["a", "b"],
                round_index=0 if v2 else -1,
                body={k: body[k] for k in ("source_id", "source_version")}, parents=[], provenance_known=True))
    return result


def _price(response, money):
    usage = response["usage"]
    _equal(usage, money["receipt"]["usage"], "raw usage differs between Session and money receipt")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if type(usage[key]) is not int or usage[key] < 0:
            raise ReplayMismatch("invalid raw token usage")
    prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
    _equal(usage["total_tokens"], prompt + completion, "inconsistent total tokens")
    _equal([response["prompt_tokens"], response["completion_tokens"]], [prompt, completion], "Session token fields")
    cached = usage.get("cached_tokens", 0)  # Pricing convention only, never impute a raw receipt field.
    if type(cached) is not int or not 0 <= cached <= prompt:
        raise ReplayMismatch("invalid cache receipt")
    units = (prompt - cached) * INPUT_RATE + cached * CACHED_RATE + completion * OUTPUT_RATE
    cost = format(Decimal(units) / CNY_UNITS, ".7f")
    _equal(units, money["actual"], "money receipt cost calculation")
    _equal(cost, response["cost_cny"], "Session response cost calculation")
    return dict(raw_usage=deepcopy(usage), accounted_cost_cny=cost, cost_units=units,
        cached_tokens_observation=usage.get("cached_tokens"),
        cache_field_status="REPORTED" if "cached_tokens" in usage else "UNKNOWN_PRICED_UNCACHED")


def _replay_episode(directory, episode, *, v2):
    """One complete cell; also the small-fixture unit-test boundary."""
    directory = Path(directory)
    module, rounds = (factorial, (1, 2)) if v2 else (visibility, (0, 1, 2))
    world, policy = episode["world_id"], episode["condition" if v2 else "arm"]
    retained = _json(directory / "records.json")
    index = {r["id"]: r for r in retained}
    _equal(len(index), len(retained), "duplicate retained record ID")
    snapshot = _json(directory / "session-snapshot.json")
    tool_receipts = _json(directory / "tool-receipts.json")
    db = sqlite3.connect((directory / "session.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        for table, key in (("calls", "calls"), ("artifacts", "artifacts"), ("work", "work")):
            rows = [dict(r) for r in db.execute("SELECT * FROM " + table + " ORDER BY rowid")]
            _equal(rows, snapshot[key], "SQLite/snapshot " + table)
        _equal([json.loads(r[0]) for r in db.execute("SELECT value FROM events ORDER BY seq")], snapshot["events"], "SQLite/snapshot events")
        _equal(dict(db.execute("SELECT * FROM run").fetchone()), snapshot["run"], "SQLite/snapshot run")
        declarations = {r["work_id"]: dict(r) for r in db.execute("SELECT * FROM coordination_inspections_v1")}
        readers = {r["id"]: json.loads(r["readers"]) for r in db.execute("SELECT * FROM coordination_sources_v1")}
    finally:
        db.close()
    calls = {r["id"]: _decoded_call(r) for r in snapshot["calls"]}
    artifacts = {r["ref"]: r for r in snapshot["artifacts"]}
    events = snapshot["events"]
    publication = {e["lineage"]["artifact_ref"]: i for i, e in enumerate(events) if e["event_type"] == "ext.session.published"}
    claims = {e["lineage"]["task_id"]: i for i, e in enumerate(events) if e["event_type"] == "ext.session.claimed"}
    source_records, expected_claims, reconstructed_tools = {}, [], []
    for receipt in tool_receipts:
        call = calls[receipt["session_call"]["id"]]
        _equal(call, receipt["session_call"], "tool receipt/Session call")
        _equal([call["action"], call["state"], call["actual"]], ["tool.evaluate", "received", 0], "tool settlement")
        body = call["response"]["artifact"]
        _equal(_fixture(world, body, v2), body, "fixture tool result")
        _equal(call["request"]["arguments"], {k: body[k] for k in ("source_id", "source_version")}, "tool arguments")
        work_id = call["work_id"]
        artifact = artifacts[receipt["artifact"]["ref"]]
        _equal(json.loads(artifact["value"]), body, "published source body")
        _equal(artifact["response_digest"], _hash(call["response"]), "published response digest")
        _equal(artifact["call_id"], call["id"], "published call identity")
        original = index[receipt["record_id"]]
        generated = dict(id="source:" + work_id, kind="source", owner=artifact["publisher"],
            readers=["a", "b"], round_index=(1 if work_id.startswith(("inspect-r1", "refresh-")) else 0 if v2 else -1),
            body=deepcopy(body), parents=[f"root:{world}:{body['source_id']}:v{body['source_version']}"],
            provenance_known=True, artifact_ref=artifact["ref"], call_id=call["id"], session_path=original["session_path"])
        _equal(generated, original, "reconstructed source provenance")
        source_records[generated["id"]] = (publication[artifact["ref"]], generated)
        lease = dict(task_id=work_id, version=call["version"], owner=generated["owner"], epoch=call["epoch"])
        expected_claims.append((generated["owner"], _hash(dict(work_id=work_id, reuse=False, lease_seconds=3600)),
                                _hash(dict(status="claimed", lease=lease, artifact_ref=None))))
        reconstructed_tools.append(dict(reason=receipt["reason"], publisher=generated["owner"],
            call_id=call["id"], result=deepcopy(body), cache_hit=False))
    actual_tool_calls = [c for c in calls.values() if c["action"] == "tool.evaluate"]
    _equal(len(tool_receipts), len(actual_tool_calls), "tool executions versus retained receipts")
    for key in ("tool_calls", "actual_tool_executions"):
        _equal(episode[key], len(actual_tool_calls), key)
    actual_claims = [(e["lineage"]["agent"], e["lineage"]["request_digest"], e["lineage"]["result_digest"])
        for e in events if e["event_type"] == "ext.coordination.operation" and e["lineage"]["operation"] == "claim_inspection"]
    _equal(sorted(actual_claims), sorted(expected_claims), "real inspection claims and disabled cache")
    reconstructed, replayed, expected_reads, selected_tool_intents = _roots(world, v2), [], [], []
    call_rows = {(r["round_index"], r["agent"]): r for r in episode["calls"]}
    _equal(sorted(call_rows), sorted((r, a) for r in rounds for a in module.AGENTS), "fixed model opportunities")
    added_sources = set()
    for round_index in rounds:
        barrier_seq = min(claims[f"model-r{round_index}-{a}"] for a in module.AGENTS)
        for identifier, (seq, record) in sorted(source_records.items(), key=lambda item: item[1][0]):
            if seq < barrier_seq and identifier not in added_sources:
                reconstructed.append(record)
                added_sources.add(identifier)
        barrier, projections = deepcopy(reconstructed), {}
        for agent in module.AGENTS:
            row = call_rows[(round_index, agent)]
            intent = _json(directory / f"r{round_index}-{agent}-intent.json")
            actual_reads = []
            task = module.public_task(world) if v2 else module.public_task(world, round_index)

            def materialize(record):
                if record["kind"] != "source":
                    return deepcopy(record["body"])
                artifact = artifacts[record["artifact_ref"]]
                declaration = declarations[artifact["work_id"]]
                if agent not in record["readers"] or agent not in readers[declaration["source_id"]] or agent not in json.loads(declaration["readers"]):
                    raise ReplayMismatch("source reader outside retained scope")
                current = task["source_versions"][declaration["source_id"]] == declaration["source_version"]
                if not current and not v2:
                    raise ReplayMismatch("v1 selected stale evidence")
                metadata = dict(artifact_ref=artifact["ref"], source_id=declaration["source_id"], source_version=declaration["source_version"],
                    tool_ref=declaration["tool_ref"], tool_version=declaration["tool_version"], state_fingerprint=declaration["fingerprint"],
                    current=current, superseded=not current, call_id=artifact["call_id"], response_digest=artifact["response_digest"],
                    publisher=artifact["publisher"], origin_work_id=artifact["work_id"],
                    scope_ref=json.loads(artifact["authority"])["scope_ref"], semantic_truth="not_established_by_provenance")
                result = dict(metadata=metadata, value=json.loads(artifact["value"]))
                read = dict(record_id=record["id"], result=result)
                if v2:
                    read["allow_superseded"] = not current
                actual_reads.append(read)
                expected_reads.append((agent, _hash(dict(artifact_ref=artifact["ref"], allow_superseded=not current)), _hash(result)))
                return result if v2 else result["value"]

            context = module.build_request(world, agent, policy, round_index, barrier, materialize)
            _equal(context, intent["projection"], "full reconstructed projection " + row["call_id"])
            _equal(actual_reads, intent["runtime_reads"], "ordered actual materialization " + row["call_id"])
            binding, call = row["binding"], calls[row["call_id"]]
            _equal(call, binding["session_call"], "model receipt/Session call")
            _equal(call["request"]["messages"], context["messages"], "exact recorded model input")
            for key, expected in (("actual_messages_sha256", module.digest(context["messages"])),
                                  ("session_request_sha256", _hash(call["request"])),
                                  ("response_sha256", _hash(call["response"]))):
                if key in binding:
                    _equal(binding[key], expected, "recorded binding hash " + key)
            if "messages_sha256" in row:
                _equal(row["messages_sha256"], context["messages_sha256"], "recorded row message hash")
            _equal([call["request"]["seed"], call["request"]["max_new_tokens"]], [intent["seed"], intent["max_new_tokens"]], "generation settings")
            _equal(binding["confirmed_sent_record_ids"], context["sent_record_ids"], "confirmed sent parents")
            _equal(binding["confirmed_public_task_sha256"], context["public_task_sha256"], "confirmed public task")
            response = call["response"]
            if call["state"] != "received" or row["status"] != "VALID_KNOWN":
                raise ReplayMismatch("incomplete/unknown call cannot become replayed model evidence")
            parsed = module.parse_action(response["text"], round_index, list(task["source_versions"]), world_id=world)
            _equal(parsed, row["parsed"], "parsed action and rejection reason")
            money = binding["money_call"]
            _equal(money["state"], "settled", "known monetary receipt")
            adapter_id = sha256(json.dumps(["session-v1", snapshot["run"]["run_id"], row["call_id"]], separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            _equal([money["id"], binding["adapter_call_id"], call["request"]["adapter_call_id"]], [adapter_id] * 3, "original request scope identity")
            for key, value in money["receipt"].items():
                _equal(response[key], value, "retained raw provider receipt " + key)
            pricing = _price(response, money)
            correct = score_v2(world, parsed) if v2 else score_v1(world, round_index, parsed)
            citations = module.current_citations(world, parsed, context) if v2 else module.current_citations(world, round_index, parsed, context)
            _equal([correct, citations, correct and citations], [row["quality"], row["current_citations"], row["grounded_correct"]], "independent objective/citation evaluation")
            original = index[row["proposal_id"]]
            proposal = dict(id=f"proposal:r{round_index}:{agent}", kind="proposal", owner=agent, readers=["a", "b"],
                round_index=round_index, body=dict(raw=response["text"], parsed=parsed, task_version=task["task_version"]),
                parents=list(context["sent_record_ids"]) + ["root:task:" + world], provenance_known=True,
                call_id=row["call_id"], session_path=original["session_path"])
            _equal(proposal, original, "direct proposal parents and raw output")
            projections[agent] = proposal
            if parsed["valid"] and parsed["action"]["action"] == "inspect":
                selected_tool_intents.append((row["dispatch_index"], agent, parsed["action"]["target"]))
            replayed.append(dict(mode="offline_replay", provider_called=False, new_provider_receipt=False,
                original_call_id=row["call_id"], agent=agent, round_index=round_index,
                projection=context, parsed=parsed, proposal=proposal, quality=correct,
                current_citations=citations, grounded_correct=correct and citations,
                original_response_id=response["response_id"], **pricing))
        for agent in sorted(module.AGENTS, key=lambda a: call_rows[(round_index, a)]["dispatch_index"]):
            reconstructed.append(projections[agent])
    _equal(reconstructed, retained, "full record order and parent reconstruction")
    actual_reads = [(e["lineage"]["agent"], e["lineage"]["request_digest"], e["lineage"]["result_digest"])
        for e in events if e["event_type"] == "ext.coordination.operation" and e["lineage"]["operation"] == "read"]
    _equal(actual_reads, expected_reads, "ordered actual read operations")
    expected_tools = [(a, target) for _, a, target in sorted(selected_tool_intents)]
    observed_tools = [(t["publisher"], t["result"]["source_id"]) for t in reconstructed_tools if t["reason"] == "model_requested_inspection"]
    _equal(expected_tools, observed_tools, "accepted tool intents versus physical execution")
    _equal(episode["model_calls"], len(replayed), "actual model count")
    _equal(episode["actual_tokens"], sum(r["raw_usage"]["total_tokens"] for r in replayed), "actual token totals")
    return dict(world_id=world, policy=policy, mode="offline_replay", calls=replayed,
                tools=reconstructed_tools, cache_hits=0, records=reconstructed)


def run_replay(run_dir, output_dir):
    """Recompute a complete retained cohort; fail on any boundary difference."""
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    report = dict(mode="offline_replay", status="FAIL", source_run=str(run_dir), provider_called=False,
                  new_provider_receipts=0, id_mapping="none; historical non-prompt provenance strings retained",
                  limitations="Legacy authority roots are historical data, not revalidated compatibility guarantees.")
    try:
        config, rows = _json(run_dir / "frozen-config.json"), _json(run_dir / "records.json")
        v2 = config["experiment_version"] == factorial.VERSION
        module = factorial if v2 else visibility
        _equal(config, module.configuration(), "frozen experiment configuration")
        _equal(_json(run_dir / "expected-grid.json"), module.expected_grid(config), "frozen grid")
        policy_key = "condition" if v2 else "arm"
        _equal([{k: r[k] for k in ("world_id", policy_key)} for r in rows], module.expected_grid(config), "complete ordered cohort")
        _equal(_json(run_dir / "summary.json")["status"], "COMPLETE", "completed source cohort required")
        episodes = []
        for number, row in enumerate(rows):
            directory = (run_dir / row["episode_directory"]).resolve()
            if not directory.is_relative_to(run_dir):
                raise ReplayMismatch("episode escapes retained run directory")
            if not row["complete_rollout"] or row["status"] != "VALID_KNOWN":
                raise ReplayMismatch("unknown or incomplete source episode")
            result = _replay_episode(directory, row, v2=v2)
            _save(output_dir / f"episode-{number:02d}.json", result)
            episodes.append(result)
        units = sum(c["cost_units"] for e in episodes for c in e["calls"])
        total = format(Decimal(units) / CNY_UNITS, ".7f")
        _equal(total, _json(run_dir / "summary.json")["collection_accounted_cost_cny"], "cohort cost total")
        report.update(status="PASS", episodes=len(episodes), model_responses=sum(len(e["calls"]) for e in episodes),
            tool_executions=sum(len(e["tools"]) for e in episodes), cache_hits=0, tariff=PRICE_VERSION,
            accounted_cost_cny=total, raw_cache_fields_missing=sum("cached_tokens" not in c["raw_usage"] for e in episodes for c in e["calls"]))
    except Exception as exc:
        report.update(error_type=type(exc).__name__, mismatch=str(exc) if isinstance(exc, ReplayMismatch) else "invalid retained evidence structure")
        _save(output_dir / "report.json", report)
        if isinstance(exc, ReplayMismatch):
            raise
        raise ReplayMismatch("invalid retained evidence structure") from exc
    _save(output_dir / "report.json", report)
    return report
