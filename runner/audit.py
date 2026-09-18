"""Offline replay of a recorded orchestration run.

Replay opens the ledger read-only, rebuilds every frozen model request from the
recorded spec, receipts and authorized artifacts, re-parses every proposal, checks
that every admitted transition is bound to the receipt it consumed, re-applies the
declared host rules and re-checks the accounting contracts. It instantiates no
transport, executes no tool, takes no clock reading and writes nothing: the counted
model and tool calls are always zero.

Replay verifies the RECORD, not the world. It cannot promise that fresh inference
would produce the same answer, that a provider billed what it reported, or that an
accepted candidate is semantically correct. A changed executable source makes the
audit explicitly LIMITED rather than silently passing; any mismatch is a FAIL.
"""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from . import contracts
from .contracts import ContractError
from .identity import source_identity
from .orchestration import MODEL_KEY, VALIDATOR_VERSION, call_identity
from .runtime import RESULT_FORMAT, Runtime, _binding
from .session import _wire
from .tools import build_registry

AUDIT_FORMAT = "orchestration-audit-v1"
TABLES = ("run", "work", "calls", "artifacts", "events", "platform_v1", "platform_work_v1",
          "platform_decisions_v1", "orchestration_v1",
          "orchestration_artifacts_v1", "orchestration_accounting_v1", "orchestration_decisions_v1")
# Offline audit reads BOTH durable task schemas; the live runtime executes only v2.
# v1 recorded one executor per task in a column named `agent`, v2 records the eligible
# set in `agents`. They are read here and normalized to the v2 name, never rewritten.
TASK_TABLES = ("orchestration_tasks_v2", "orchestration_tasks_v1")


def _digest(value):
    return sha256(_wire(value).encode()).hexdigest()


def read_only(path):
    """Open a recorded ledger read-only; a write attempt fails rather than mutating it."""
    database = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA query_only=ON")
    return database


class ReplayLedger:
    """A read-only projection exposing only the accessors the context builder needs."""

    def __init__(self, path):
        database = read_only(path)
        try:
            self.rows = {}
            for table in TABLES:
                order = "seq" if table in ("events", "orchestration_decisions_v1") else "rowid"
                self.rows[table] = [dict(row) for row in
                                    database.execute(f"SELECT rowid AS row_index, * FROM {table} ORDER BY {order}")]
            self.task_table = None
            for table in TASK_TABLES:
                try:
                    rows = [dict(row) for row in database.execute(
                        f"SELECT rowid AS row_index, * FROM {table} ORDER BY rowid")]
                except sqlite3.OperationalError:
                    continue
                for row in rows:
                    if "agents" not in row:
                        decoded = json.loads(row["agent"])
                        row["agents"] = _wire(decoded if type(decoded) is list else [decoded])
                self.rows["orchestration_tasks"], self.task_table = rows, table
                break
            if self.task_table is None:
                raise ValueError("the ledger declares no orchestration task table")
        finally:
            database.close()
        self._spec = json.loads(self.rows["orchestration_v1"][0]["spec"])
        self.spec_digest = self.rows["orchestration_v1"][0]["spec_digest"]
        self.template_version = self.rows["orchestration_v1"][0]["template_version"]
        self.limit = None

    # ---- accessors used by the shared context builder

    def spec(self):
        return json.loads(_wire(self._spec))

    def task(self, work_id):
        for row in self.rows["orchestration_tasks"]:
            if row["work_id"] == work_id:
                return json.loads(row["declaration"])
        raise KeyError(work_id)

    def claim_owner(self, work_id, version, epoch):
        """The owner the ledger recorded when this work was claimed at this epoch.

        ``claim`` writes a durable ``claimed`` event carrying owner, task, version and
        epoch, so a call that reserved but never dispatched still has an independently
        attested actor. Recovering it here is what lets offline audit verify
        reservation-before-dispatch instead of abandoning a call that produced no
        external effect.
        """
        for row in self.rows["events"]:
            value = json.loads(row["value"])
            if not value["event_type"].endswith(".claimed"):
                continue
            details = value["details"]
            if (details["task_id"], details["version"], details["epoch"]) == (work_id, version, epoch):
                return details["owner"]
        return None

    def decisions(self, work_id=None):
        return [dict(row) for row in self.rows["orchestration_decisions_v1"]
                if work_id is None or row["work_id"] == work_id]

    def call(self, call_id):
        for row in self.rows["calls"]:
            if row["id"] == call_id:
                return {**row, "request": json.loads(row["request"]),
                        "response": json.loads(row["response"]) if row["response"] else None}
        raise KeyError(call_id)

    def calls_of(self, work_id, version=None, before=None):
        out = []
        for row in self.rows["calls"]:
            if row["work_id"] != work_id or (version is not None and row["version"] != version):
                continue
            if before is not None and row["row_index"] >= before:
                continue
            out.append({**row, "request": json.loads(row["request"]),
                        "response": json.loads(row["response"]) if row["response"] else None})
        return out

    def work_calls_of(self, work_id):
        work = self.work(work_id)
        return self.calls_of(work_id, work["version"])

    def work(self, work_id):
        for row in self.rows["work"]:
            if row["id"] == work_id:
                return row
        raise KeyError(work_id)

    def artifact_of(self, work_id):
        for row in self.rows["artifacts"]:
            if row["work_id"] == work_id:
                kind = next((item["kind"] for item in self.rows["orchestration_artifacts_v1"]
                             if item["ref"] == row["ref"]), "output")
                value = json.loads(row["value"])
                return {"ref": row["ref"], "work_id": work_id, "version": row["version"], "kind": kind,
                        "value": value, "digest": _digest(value), "call_id": row["call_id"]}
        return None

    def readable_artifacts(self, work_id, agent, before_step=None):
        out = []
        for producer in self._effective_reads(work_id, before_step):
            item = self.artifact_of(producer)
            if item is not None and item["version"] == self.work(producer)["version"]:
                out.append(item)
        return out

    def _effective_reads(self, work_id, before_step=None):
        reads = list(self.task(work_id)["reads"])
        admitted = next((row for row in self.rows["orchestration_decisions_v1"]
                         if row["work_id"] == work_id and row["decision"] == "decompose"), None)
        if admitted is None or (before_step is not None
                                and (admitted["step"] is None or admitted["step"] >= before_step)):
            return reads
        for row in self.rows["orchestration_tasks"]:
            if row["parent"] == work_id and row["work_id"] not in reads:
                reads.append(row["work_id"])
        return reads

    def snapshot(self):
        return {"orchestration": {"spec_digest": self.spec_digest}}


def _as_of(ledger, runtime, declaration, call):
    """Rebuild the exact inputs of one model call from rows recorded before it.

    Which eligible agent claimed is an allocation decision, so it is recovered from
    the ledger's own authority records, never from the binding being checked against
    it: reading the actor out of the binding would let the record certify itself.

    Two independent records carry it. A dispatched call carries its execution
    permission. A call that only reserved has no permission, but its claim is still
    attested by the durable ``claimed`` event at the same work, version and epoch, so
    it is reconstructed rather than abandoned: that is what keeps
    reservation-before-dispatch verifiable offline. Returns the claimant and the
    claim-event owner separately so the caller can hold them against each other.
    """
    binding = _binding(call)
    step, version = binding.get("step"), call["version"]
    attested = ledger.claim_owner(call["work_id"], version, call["epoch"])
    claimant = json.loads(call["permission"])["owner"] if call["permission"] else attested
    history = ledger.calls_of(call["work_id"], version, before=call["row_index"])
    decisions = [row for row in ledger.decisions(call["work_id"])
                 if row["version"] == version and (row["step"] is None or row["step"] < step)]
    inputs = ledger.readable_artifacts(call["work_id"], claimant, step)
    state = runtime._state(declaration, history, decisions)
    return history, decisions, inputs, state["remaining"], claimant, attested


def replay_run(path, *, spec_dir=None):
    """Verify a recorded run offline; returns a report and never touches the original."""
    ledger = ReplayLedger(path)
    failures, checks = [], []
    spec_source = ledger.spec()

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name + (": " + detail if detail else ""))
        return ok

    try:
        spec = contracts.workflow_spec(spec_source)
        check("spec_revalidates", True)
    except ContractError as exc:
        check("spec_revalidates", False, str(exc))
        spec = spec_source
    check("spec_digest", _digest(spec_source) == ledger.spec_digest,
          "recomputed %s vs recorded %s" % (_digest(spec_source), ledger.spec_digest))
    check("template_version", ledger.template_version == contracts.TEMPLATE_VERSION,
          "recorded %s" % ledger.template_version)

    configured = next((json.loads(_wire(row)) for row in ledger.rows["events"]
                       if json.loads(row["value"])["event_type"] == "interaction.session.orchestration.configured"),
                      None)
    recorded_identity = (json.loads(configured["value"])["details"].get("source_identity")
                         if configured else None)
    source_match = recorded_identity == source_identity()

    registry = build_registry(spec, Path(spec_dir) if spec_dir else Path(path).parent)
    runtime = Runtime(ledger, registry=registry, transports={})

    model_calls = tool_calls = 0
    for call in ledger.rows["calls"]:
        binding = json.loads(call["request"]).get("binding") or {}
        kind = binding.get("kind")
        record = ledger.call(call["id"])
        record["row_index"] = call["row_index"]
        try:
            declaration = ledger.task(call["work_id"])
        except KeyError:
            check("call_declared:" + call["id"], False, "call belongs to undeclared work")
            continue
        expected = call_identity(ledger.rows["run"][0]["run_id"], call["work_id"], call["version"],
                                 kind, binding.get("step"), binding.get("attempt", 0)) if kind else None
        check("call_identity:" + call["id"], expected == call["id"],
              "logical key %s" % expected)
        if kind == "model":
            model_calls += 1
            history, decisions, inputs, remaining, claimant, attested = _as_of(
                ledger, runtime, declaration, record)
            # A dispatched call carries permission AND must have a matching claim
            # event. Two records of the same authority that disagree is a failure, not
            # a preference: neither can then be trusted to say who executed.
            if call["permission"] and attested is not None:
                check("call_authority_agrees:" + call["id"],
                      json.loads(call["permission"])["owner"] == attested,
                      "permission owner and claim event disagree about the executor")
            if claimant is None:
                check("call_unattested:" + call["id"], False,
                      "a recorded call has neither an execution permission nor a claim event")
                continue
            check("call_claimant:" + call["id"],
                  claimant in contracts.eligible_agents(declaration),
                  "the call was executed by an agent the task does not declare")
            if not call["permission"]:
                # Reserved but never dispatched: the actor is attested, so the claim
                # is verified, but there is no frozen request to rebuild against.
                check("call_undispatched:" + call["id"], call["state"] in ("reserved", "abandoned"),
                      "a call without an execution permission must never have dispatched")
                continue
            rebuilt, rebuilt_binding = runtime.frozen_model_request(
                declaration, call["work_id"], call["version"], history, decisions, inputs,
                remaining, binding.get("step"), binding.get("attempt", 0), ledger.spec_digest,
                claimant)
            stored = json.loads(call["request"])["arguments"]["request"]
            check("request_rebuild:" + call["id"], _wire(rebuilt) == _wire(stored),
                  "rebuilt request differs from the recorded request")
            comparable = {key: value for key, value in binding.items() if key != "budget"}
            check("binding_rebuild:" + call["id"], _wire(rebuilt_binding) == _wire(comparable),
                  "rebuilt binding differs from the recorded binding")
            check("request_digest:" + call["id"],
                  binding.get("request_digest") == contracts.digest(stored))
        elif kind == "tool":
            tool_calls += 1
            payload = json.loads(call["request"])
            check("tool_declared:" + call["id"], payload.get("tool_ref") in declaration["tools"],
                  "tool outside the task declaration")
            check("tool_arguments:" + call["id"],
                  contracts.digest(payload.get("arguments")) == binding.get("arguments_digest"))
            try:
                source = ledger.call(binding.get("model_call_id"))
                bound = sha256(_wire(source["response"]).encode()).hexdigest() == binding.get("receipt_digest")
            except KeyError:
                bound = False
            check("tool_receipt_binding:" + call["id"], bound,
                  "tool call is not bound to a settled model receipt")
        elif call["state"] != "abandoned":
            check("call_kind:" + call["id"], False, "call carries no orchestration binding")

    for row in ledger.rows["orchestration_decisions_v1"]:
        name = "decision:%d" % row["seq"]
        check(name + ":validator", row["validator"] == VALIDATOR_VERSION, row["validator"])
        try:
            source = ledger.call(row["call_id"])
        except KeyError:
            check(name + ":receipt", False, "decision names an unknown call")
            continue
        check(name + ":settled", source["state"] in ("received", "response_rejected"), source["state"])
        if source["state"] != "received":
            continue
        check(name + ":digest", sha256(_wire(source["response"]).encode()).hexdigest() == row["receipt_digest"])
        declaration = ledger.task(row["work_id"])
        try:
            proposal = contracts.parse_proposal(
                source["response"][MODEL_KEY], tools=runtime._tool_schemas(declaration),
                output_schema=declaration["output_schema"],
                decomposition=runtime._tool_schemas(declaration).get("propose_children"))
            parsed = proposal["kind"]
        except (ContractError, KeyError, TypeError):
            parsed = "rejected"
        # A rejection can come from parsing OR from a refused admission, so a well-formed
        # proposal may legitimately carry one; its reason records which. Every other
        # decision must match a fresh parse of the receipt it claims to have consumed.
        check(name + ":proposal", parsed == row["decision"] or row["decision"] == "rejected",
              "receipt re-parses to %s but the ledger recorded %s" % (parsed, row["decision"]))

    for row in ledger.rows["orchestration_artifacts_v1"]:
        name = "artifact:" + row["ref"]
        stored = next((item for item in ledger.rows["artifacts"] if item["ref"] == row["ref"]), None)
        if stored is None:
            check(name, False, "lineage names an unpublished artifact")
            continue
        value = json.loads(stored["value"])
        lineage = json.loads(row["lineage"])
        ok = True
        for item in lineage:
            try:
                source = ledger.call(item["call_id"])
            except KeyError:
                ok = False
                break
            ok = ok and source["state"] == "received" and \
                sha256(_wire(source["response"]).encode()).hexdigest() == item["digest"]
        check(name + ":lineage", ok, "lineage does not match settled receipts")
        declaration = ledger.task(row["work_id"])
        if row["kind"] == "output" and ok:
            source = ledger.call(lineage[0]["call_id"])
            try:
                proposal = contracts.parse_proposal(source["response"][MODEL_KEY], tools={},
                                                    output_schema=declaration["output_schema"])
                matches = proposal["kind"] == "submit" and _wire(proposal["output"]) == _wire(value)
            except (ContractError, KeyError, TypeError):
                matches = False
            check(name + ":output", matches, "artifact differs from the receipt's validated proposal")
        elif row["kind"] == "result":
            rebuilt, rebuilt_lineage, _ = runtime.evaluate_rule(row["work_id"], declaration)
            check(name + ":rule", rebuilt is not None and _wire(rebuilt) == _wire(value),
                  "the declared rule does not reproduce the recorded result")
            check(name + ":result_lineage", rebuilt_lineage is not None
                  and _wire(rebuilt_lineage) == _wire(lineage))
            check(name + ":format", value.get("format") == RESULT_FORMAT)

    violations = []
    for row in ledger.rows["orchestration_accounting_v1"]:
        name = "accounting:" + row["call_id"]
        try:
            call = ledger.call(row["call_id"])
        except KeyError:
            check(name, False, "accounting names an unknown call")
            continue
        if row["violation"]:
            violations.append(row["call_id"])
            check(name + ":unresolved", call["state"] == "dispatched",
                  "a call with an accounting violation must stay dispatched")
            continue
        if call["state"] == "received":
            reported = json.loads(row["reported"]) if row["reported"] else {}
            check(name + ":bound", call["response"]["prompt_tokens"] <= row["prompt_bound"],
                  "settled prompt usage exceeds the declared bound")
            check(name + ":recorded", reported.get("prompt_tokens") == call["response"]["prompt_tokens"])

    published = {row["work_id"] for row in ledger.rows["artifacts"]}
    for row in ledger.rows["work"]:
        if row["id"] in published:
            continue
        decided = any(item["work_id"] == row["id"] for item in ledger.rows["platform_decisions_v1"])
        check("terminal:" + row["id"], decided or row["status"] != "done",
              "work is done with neither an artifact nor a recorded decision")

    # Consumption is durable: a settled model receipt carries exactly one decision, except
    # for the single receipt a still-running task has not consumed yet. A terminal task
    # with an unconsumed receipt means a decision row is missing.
    consumed = {row["call_id"] for row in ledger.rows["orchestration_decisions_v1"]}
    terminal = published | {row["work_id"] for row in ledger.rows["platform_decisions_v1"]}
    unconsumed = {}
    for call in ledger.rows["calls"]:
        binding = json.loads(call["request"]).get("binding") or {}
        if (binding.get("kind") == "model" and call["state"] in ("received", "response_rejected")
                and call["id"] not in consumed):
            unconsumed.setdefault(call["work_id"], []).append(call["id"])
    for work_id, ids in unconsumed.items():
        check("decision_missing:" + work_id, work_id not in terminal and len(ids) == 1,
              "settled model receipts with no recorded decision: " + ", ".join(ids))
    counts = {}
    for row in ledger.rows["orchestration_decisions_v1"]:
        counts[row["call_id"]] = counts.get(row["call_id"], 0) + 1
    for call_id, count in counts.items():
        check("decision_uniqueness:" + call_id, count == 1,
              "the receipt carries %d decisions" % count)

    status = "FAIL" if failures else ("PASS" if source_match else "LIMITED")
    return {"format": AUDIT_FORMAT, "status": status, "mode": "offline replay",
            "source_match": source_match, "spec_digest": ledger.spec_digest,
            "run_id": ledger.rows["run"][0]["run_id"], "run_status": ledger.rows["run"][0]["status"],
            "new_model_calls": 0, "new_tool_calls": 0,
            "checks": len(checks), "failures": failures,
            "accounting_violations": violations,
            "counts": {"model_calls": model_calls, "tool_calls": tool_calls,
                       "artifacts": len(ledger.rows["artifacts"]),
                       "decisions": len(ledger.rows["orchestration_decisions_v1"]),
                       "rejections": sum(row["decision"] == "rejected"
                                         for row in ledger.rows["orchestration_decisions_v1"]),
                       "unknown_calls": sum(row["state"] == "dispatched" for row in ledger.rows["calls"]),
                       "outstanding_reservations": sum(row["state"] == "reserved" for row in ledger.rows["calls"]),
                       "known_tokens": sum(row["actual"] or 0 for row in ledger.rows["calls"])}}
