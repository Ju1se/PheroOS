"""Orchestration ledger: capability declarations, bounded accounting, derived artifacts.

This mixin adds four things to the platform ledger and nothing else: a durable
per-task capability declaration checked at every reservation and dispatch, a
``bounded_v2`` prompt-usage contract for providers that cannot accept a predeclared
prompt count, a derived-artifact transition with explicit lineage, and a durable
record of which model receipt was consumed by which admitted transition.

Authority comes only from the declarations recorded here by the trusted host. A
model receipt is data: it is parsed, validated against the task's declared schemas
and then either consumed by one admitted transition or recorded as a rejection.
No method here calls a model, runs a tool, reads the network or takes a clock
reading other than the session's own. Publication records what was admitted; it is
not a certificate that an artifact is semantically correct.
"""

from hashlib import sha256
import json

from pheroos_interaction.records import BudgetExceeded, Lease, StateError
from . import contracts
from .contracts import ContractError
from .identity import source_identity
from .platform import PlatformMixin, _text
from .session import Session, _duration, _id, _integer, _wire

CONTRACT = "bounded_v2"
ARTIFACT_KINDS = ("output", "result")
CALL_KINDS = ("model", "tool")
DECISIONS = ("tool", "submit", "abstain", "decompose", "rejected")
VALIDATOR_VERSION = "orchestration-validator-v1"
MODEL_KEY = "message"
TOOL_KEY = "result"


def call_identity(run_id, task_id, version, kind, step, attempt=0):
    """The durable logical operation key; attempt 0 omits the attempt component."""
    if kind not in CALL_KINDS:
        raise ValueError("call kind must be model or tool")
    key = [run_id, task_id, version, kind, step] + ([attempt] if attempt else [])
    return "orch:" + sha256(_wire(key).encode()).hexdigest()


def _digest(value):
    return sha256(_wire(value).encode()).hexdigest()



class OrchestrationMixin:
    """Compose with PlatformMixin and Session; the base ledger still owns every call."""

    @classmethod
    def create(cls, path, *, spec, clock=None):
        """Create a ledger from a validated workflow spec; tasks become platform work."""
        spec = contracts.workflow_spec(spec)
        limits = spec["limits"]
        agents = [agent["id"] for agent in spec["agents"]] + [contracts.HOST_AGENT]
        work, budgets = [], {}
        for task in spec["tasks"]:
            work.append({"id": task["id"], "version": task["version"],
                         "dependencies": list(task["dependencies"]),
                         "agents": contracts.eligible_agents(task), "actions": ["tool.evaluate"]})
            budgets[task["id"]] = ({"calls": 0, "tokens": 0} if task["kind"] == "host"
                                   else {"calls": task["limits"]["calls"], "tokens": task["limits"]["tokens"]})
        session = super().create(
            path, spec["run_id"], agents=agents, work=work,
            token_cap=limits["token_cap"], max_calls=limits["max_calls"],
            context_bytes=limits["context_bytes"], artifact_bytes=limits["artifact_bytes"], clock=clock,
            platform={"budgets": budgets, "max_children": limits["max_children"],
                      "max_depth": limits["max_depth"], "max_work_items": limits["max_work_items"],
                      "max_candidates": 1, "max_platform_operations": limits["max_platform_operations"]})
        with session._transaction() as db:
            for sql in (
                "CREATE TABLE orchestration_v1 (id INTEGER PRIMARY KEY CHECK(id=1), spec TEXT, spec_digest TEXT, template_version TEXT, validator TEXT)",
                "CREATE TABLE orchestration_tasks_v2 (work_id TEXT PRIMARY KEY REFERENCES work(id), version INTEGER, kind TEXT, agents TEXT, declaration TEXT, parent TEXT, origin TEXT)",
                "CREATE TABLE orchestration_artifacts_v1 (ref TEXT PRIMARY KEY REFERENCES artifacts(ref), work_id TEXT REFERENCES work(id), version INTEGER, kind TEXT, lineage TEXT)",
                "CREATE TABLE orchestration_accounting_v1 (call_id TEXT PRIMARY KEY REFERENCES calls(id), contract TEXT, prompt_bound INTEGER, reported TEXT, violation TEXT)",
                "CREATE TABLE orchestration_decisions_v1 (seq INTEGER PRIMARY KEY AUTOINCREMENT, work_id TEXT REFERENCES work(id), version INTEGER, call_id TEXT, receipt_digest TEXT, step INTEGER, decision TEXT, reason TEXT, validator TEXT)",
            ):
                db.execute(sql)
            db.execute("INSERT INTO orchestration_v1 VALUES (1,?,?,?,?)",
                       (_wire(spec), _digest(spec), contracts.TEMPLATE_VERSION, VALIDATOR_VERSION))
            for task in spec["tasks"]:
                db.execute("INSERT INTO orchestration_tasks_v2 VALUES (?,?,?,?,?,NULL,'spec')",
                           (task["id"], task["version"], task["kind"],
                            _wire(contracts.eligible_agents(task)), _wire(task)))
            session._event(db, "orchestration.configured", "",
                           {"spec_digest": _digest(spec), "tasks": [t["id"] for t in spec["tasks"]],
                            "template_version": contracts.TEMPLATE_VERSION, "validator": VALIDATOR_VERSION,
                            "source_identity": source_identity()})
        return session

    # ------------------------------------------------------------ declarations

    def _orchestration(self, db):
        return db.execute("SELECT * FROM orchestration_v1 WHERE id=1").fetchone()

    def spec(self):
        with self._transaction() as db:
            return json.loads(self._orchestration(db)["spec"])

    def _task_row(self, db, work_id):
        return db.execute("SELECT * FROM orchestration_tasks_v2 WHERE work_id=?", (work_id,)).fetchone()

    def _declaration(self, db, work_id, version=None):
        row = self._task_row(db, work_id)
        if row is None:
            raise StateError("work has no orchestration declaration")
        if version is not None and row["version"] != version:
            raise StateError("task declaration version differs from the work version")
        return json.loads(row["declaration"])

    def task(self, work_id):
        with self._transaction() as db:
            return self._declaration(db, work_id)

    def tasks(self):
        with self._transaction() as db:
            return [{"work_id": row["work_id"], "version": row["version"], "kind": row["kind"],
                     "agents": json.loads(row["agents"]), "parent": row["parent"], "origin": row["origin"],
                     "declaration": json.loads(row["declaration"])}
                    for row in db.execute("SELECT * FROM orchestration_tasks_v2 ORDER BY rowid")]

    # ------------------------------------------------------------ authorized reads

    def _effective_reads(self, db, work_id, declaration, before_step=None):
        """Declared reads plus the children this task admitted; declarations never mutate.

        A parent reads its own children's artifacts without its declaration changing,
        so the context of an earlier step stays reconstructible: ``before_step`` keeps
        only children admitted strictly before that step, which is what the live run
        could see at the time.
        """
        reads = list(declaration["reads"])
        admitted = db.execute("SELECT step FROM orchestration_decisions_v1 "
                              "WHERE work_id=? AND decision='decompose' ORDER BY seq LIMIT 1",
                              (work_id,)).fetchone()
        if admitted is None or (before_step is not None
                                and (admitted["step"] is None or admitted["step"] >= before_step)):
            return reads
        for row in db.execute("SELECT work_id FROM orchestration_tasks_v2 WHERE parent=? ORDER BY rowid",
                              (work_id,)).fetchall():
            if row["work_id"] not in reads:
                reads.append(row["work_id"])
        return reads

    def _artifact_rows(self, db, work_id, version, before_step=None):
        """Artifacts the task may read now: one per effective read, at the current version."""
        declaration = self._declaration(db, work_id, version)
        out = []
        for producer in self._effective_reads(db, work_id, declaration, before_step):
            row = db.execute("SELECT a.*, o.kind AS artifact_kind FROM artifacts a "
                             "LEFT JOIN orchestration_artifacts_v1 o ON o.ref=a.ref "
                             "WHERE a.work_id=?", (producer,)).fetchone()
            if row is None:
                continue
            work = db.execute("SELECT version FROM work WHERE id=?", (producer,)).fetchone()
            if work is None or work["version"] != row["version"]:
                continue
            out.append({"ref": row["ref"], "work_id": producer, "version": row["version"],
                        "kind": row["artifact_kind"] or "output", "value": json.loads(row["value"]),
                        "digest": _digest(json.loads(row["value"])), "call_id": row["call_id"]})
        return out

    def work_calls_of(self, work_id):
        """Trusted-host audit read of a work's calls; not an agent content interface.

        The host runtime uses this to bind a finalization to receipts of the tasks it
        declared as dependencies. Agents never reach it: their inputs come from
        ``readable_artifacts`` and their tools from the resolver.
        """
        _id(work_id)
        with self._transaction() as db:
            work = db.execute("SELECT version FROM work WHERE id=?", (work_id,)).fetchone()
            if work is None:
                raise StateError("unknown work")
            return [{**dict(row), "request": json.loads(row["request"]),
                     "response": json.loads(row["response"]) if row["response"] else None}
                    for row in db.execute("SELECT * FROM calls WHERE work_id=? AND version=? ORDER BY rowid",
                                          (work_id, work["version"])).fetchall()]

    def work_budget(self, work_id):
        """Remaining call and token capacity, derived only from this work's durable rows."""
        with self._transaction() as db:
            meta = self._budget_row(db, work_id)
            calls, tokens = self._spent(db, work_id)
            return {"calls": meta["calls_cap"] - calls, "tokens": meta["tokens_cap"] - tokens,
                    "calls_cap": meta["calls_cap"], "tokens_cap": meta["tokens_cap"]}

    def reserve_tool_call(self, lease, call_id, payload, *, source_call_id, step):
        """Reserve a tool call and record the model receipt it consumes, atomically."""
        _id(source_call_id)
        with self._transaction() as db:
            source = db.execute("SELECT * FROM calls WHERE id=?", (source_call_id,)).fetchone()
            if source is None or source["work_id"] != lease.task_id or source["state"] != "received":
                raise StateError("a tool call consumes a settled receipt of this task")
            if any(row["call_id"] == source_call_id for row in self._decisions(db, lease.task_id, lease.version)):
                raise StateError("this receipt already has a recorded decision")
            self._reserve(db, lease, call_id, "tool.evaluate", payload, 0, 0, "exact_v1")
            self._record_decision(db, lease.task_id, lease.version, source_call_id,
                                  sha256(source["response"].encode()).hexdigest(), step, "tool",
                                  "tool call " + call_id)
            return call_id

    def abstain_task(self, lease, *, source_call_id=None, step=None, reason="agent_abstain"):
        """Terminate the task with no artifact, recording the receipt it consumed."""
        _text(reason)
        with self._transaction() as db:
            if source_call_id is not None:
                source = db.execute("SELECT * FROM calls WHERE id=?", (source_call_id,)).fetchone()
                if source is None or source["work_id"] != lease.task_id or source["state"] != "received":
                    raise StateError("an abstention consumes a settled receipt of this task")
                if any(row["call_id"] == source_call_id for row in self._decisions(db, lease.task_id, lease.version)):
                    raise StateError("this receipt already has a recorded decision")
                self._record_decision(db, lease.task_id, lease.version, source_call_id,
                                      sha256(source["response"].encode()).hexdigest(), step, "abstain", reason)
            return self._abstain(db, lease, {"decision": "abstain", "publisher": lease.owner, "reason": reason})

    def readable_artifacts(self, work_id, agent, before_step=None):
        """The task's authorized inputs; access is rechecked, a stale context grants nothing."""
        with self._transaction() as db:
            work = self._work(db, work_id, agent)
            return self._artifact_rows(db, work_id, work["version"], before_step)

    # ------------------------------------------------------------ admission

    def _binding(self, payload):
        binding = payload.get("binding")
        if type(binding) is not dict:
            raise StateError("orchestration requests must carry a binding")
        return binding

    def _reservation_request(self, db, lease, call_id, action, payload):
        """Durable capability admission; also re-run at dispatch, so a stale context fails."""
        super()._reservation_request(db, lease, call_id, action, payload)
        row = self._task_row(db, lease.task_id)
        if row is None:
            return
        declaration = json.loads(row["declaration"])
        if lease.owner not in contracts.eligible_agents(declaration):
            raise StateError("the claiming agent is not eligible for this task")
        if row["kind"] == "host":
            raise StateError("a host task performs no calls")
        binding = self._binding(payload)
        kind, step = binding.get("kind"), binding.get("step")
        attempt = binding.get("attempt", 0)
        if (kind not in CALL_KINDS or type(step) is not int or step < 0
                or type(attempt) is not int or attempt < 0):
            raise StateError("binding requires an exact call kind, step and attempt")
        run_id = self._run(db)["run_id"]
        if call_id != call_identity(run_id, lease.task_id, lease.version, kind, step, attempt):
            raise StateError("call id is not the logical operation key of its binding")
        if binding.get("spec_digest") != self._orchestration(db)["spec_digest"]:
            raise StateError("binding does not carry the current workflow digest")
        if binding.get("task_version") != lease.version:
            raise StateError("binding does not carry the current task version")
        limits = declaration["limits"]
        if step >= limits["model_steps"]:
            raise BudgetExceeded("task model step limit exhausted")
        history = [row for row in db.execute(
            "SELECT * FROM calls WHERE work_id=? AND version=? ORDER BY rowid",
            (lease.task_id, lease.version)).fetchall() if row["id"] != call_id]
        if kind == "model":
            self._admit_model(db, declaration, payload, binding, history, step)
        else:
            self._admit_tool(db, declaration, payload, binding, history, limits)
        for item in binding.get("inputs", []):
            if type(item) is not dict or set(item) != {"producer", "ref", "digest", "version"}:
                raise StateError("each binding input needs producer, ref, digest and version")
        current = {row["ref"]: row for row in self._artifact_rows(db, lease.task_id, lease.version)}
        for item in binding.get("inputs", []):
            live = current.get(item["ref"])
            if live is None or (live["work_id"], live["version"], live["digest"]) != (
                    item["producer"], item["version"], item["digest"]):
                raise StateError("a bound input is no longer authorized or has changed")

    def _admit_model(self, db, declaration, payload, binding, history, step):
        if payload.get("tool_ref") != contracts.MODEL_TOOL_REF:
            raise StateError("a model call must declare the model tool reference")
        offered = binding.get("tools")
        if type(offered) is not list:
            raise StateError("a model binding must list the offered tools")
        names = [item.get("name") if type(item) is dict else None for item in offered]
        allowed = set(declaration["tools"]) | {"submit_output", "abstain"}
        if declaration.get("decomposition"):
            allowed.add("propose_children")
        if len(set(names)) != len(names) or not set(names) <= allowed:
            raise StateError("offered tools exceed the task declaration")
        request = payload.get("arguments", {}).get("request")
        if type(request) is not dict:
            raise StateError("a model call must carry its frozen request")
        if {tool.get("name") for tool in request.get("tools", []) if type(tool) is dict} != set(names):
            raise StateError("the frozen request offers tools the binding does not declare")
        if any(call["id"] for call in history
               if json.loads(call["request"]).get("binding", {}).get("kind") == "model"
               and json.loads(call["request"])["binding"].get("step") == step
               and call["state"] in ("received", "dispatched", "reserved")):
            raise StateError("this model step already has an unresolved or settled call")

    def _admit_tool(self, db, declaration, payload, binding, history, limits):
        name = payload.get("tool_ref")
        if name not in declaration["tools"]:
            raise StateError("tool is outside the task declaration")
        for field in ("tool_version", "schema_digest", "arguments_digest", "proposal_digest"):
            if type(binding.get(field)) is not str or not binding[field]:
                raise StateError("a tool binding needs the tool version and argument digests")
        source = db.execute("SELECT * FROM calls WHERE id=?", (binding.get("model_call_id"),)).fetchone()
        if source is None or source["work_id"] != declaration["id"] or source["state"] != "received":
            raise StateError("a tool call must consume a settled model receipt of this task")
        if sha256(source["response"].encode()).hexdigest() != binding.get("receipt_digest"):
            raise StateError("tool binding does not match its model receipt")
        if _digest(payload.get("arguments")) != binding["arguments_digest"]:
            raise StateError("tool arguments differ from the bound digest")
        # Bind to the proposal the receipt carries, not only to its digest: the tool
        # and arguments dispatched must be the ones the model actually asked for.
        content = json.loads(source["response"]).get(MODEL_KEY, {}).get("content")
        uses = [block for block in content or [] if block.get("type") == "tool_use"]
        if len(uses) != 1 or uses[0].get("name") != name:
            raise StateError("the receipt does not propose exactly this tool")
        if _digest(uses[0].get("input")) != binding["arguments_digest"]:
            raise StateError("the receipt proposes different arguments")
        spent = sum(1 for call in history
                    if json.loads(call["request"]).get("binding", {}).get("kind") == "tool"
                    and call["state"] in ("received", "dispatched", "response_rejected"))
        if spent >= limits["tool_calls"]:
            raise BudgetExceeded("task tool call limit exhausted")

    # ------------------------------------------------------------ accounting

    def _prompt_contract(self, db, call):
        row = db.execute("SELECT contract FROM orchestration_accounting_v1 WHERE call_id=?", (call["id"],)).fetchone()
        return row["contract"] if row else super()._prompt_contract(db, call)

    def _prompt_settles(self, contract, call, prompt):
        if contract != CONTRACT:
            return super()._prompt_settles(contract, call, prompt)
        return prompt <= call["prompt"]

    def reserve_bounded(self, lease, call_id, action, payload, *, prompt_token_bound, max_new_tokens):
        """Reserve under ``bounded_v2``: the reservation is the declared bound, not a promise.

        The provider reports prompt usage after the fact, so the ledger reserves the
        host's declared upper bound and settles the reported usage when it does not
        exceed it. A report above the bound is refused by ``receive`` and belongs in
        ``record_accounting_violation``; the call then stays dispatched.
        """
        _integer(prompt_token_bound, "prompt_token_bound")
        with self._transaction() as db:
            self._reserve(db, lease, call_id, action, payload, prompt_token_bound, max_new_tokens, CONTRACT)
            db.execute("INSERT OR IGNORE INTO orchestration_accounting_v1 VALUES (?,?,?,NULL,NULL)",
                       (call_id, CONTRACT, prompt_token_bound))
            return call_id

    def _settled(self, db, call_id, call, response, state):
        """Record the reported usage in the settlement transaction itself.

        A separate write could be lost to a crash between the two transactions, which
        would leave a legitimate run looking like a tampered one to an audit. Settling
        the receipt and recording what the provider reported therefore commit together.
        """
        super()._settled(db, call_id, call, response, state)
        if db.execute("SELECT 1 FROM orchestration_accounting_v1 WHERE call_id=?", (call_id,)).fetchone() is None:
            return
        message = response.get(MODEL_KEY)
        reported = {"contract": CONTRACT, "state": state,
                    "prompt_tokens": response["prompt_tokens"],
                    "completion_tokens": response["completion_tokens"],
                    "usage": message["usage"] if type(message) is dict and "usage" in message else None}
        db.execute("UPDATE orchestration_accounting_v1 SET reported=? WHERE call_id=?",
                   (_wire(contracts.finite_json(reported)), call_id))

    def record_accounting_violation(self, call_id, reported, response_digest):
        """Record a usage report that exceeds the declared bound; the call stays dispatched.

        The ledger cannot settle a charge it did not admit, so it records the report
        instead of inventing a settlement. After a violation the token cap no longer
        bounds what the provider may bill for this call.
        """
        _id(call_id)
        _id(response_digest)
        reported = contracts.finite_json(reported)
        with self._transaction() as db:
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None or call["state"] != "dispatched":
                raise StateError("an accounting violation belongs to a dispatched call")
            row = db.execute("SELECT violation FROM orchestration_accounting_v1 WHERE call_id=?", (call_id,)).fetchone()
            record = {"reported": reported, "response_digest": response_digest,
                      "prompt_bound": call["prompt"], "max_new_tokens": call["maximum"]}
            if row is not None and row["violation"] == _wire(record):
                return record
            db.execute("UPDATE orchestration_accounting_v1 SET violation=? WHERE call_id=?", (_wire(record), call_id))
            self._event(db, "orchestration.accounting_violation", call["work_id"], {"call_id": call_id, **record})
            return record

    def accounting(self):
        with self._transaction() as db:
            return [{"call_id": row["call_id"], "contract": row["contract"], "prompt_bound": row["prompt_bound"],
                     "reported": json.loads(row["reported"]) if row["reported"] else None,
                     "violation": json.loads(row["violation"]) if row["violation"] else None}
                    for row in db.execute("SELECT * FROM orchestration_accounting_v1 ORDER BY rowid")]

    # ------------------------------------------------------------ decisions

    def _record_decision(self, db, work_id, version, call_id, receipt_digest, step, decision, reason):
        if decision not in DECISIONS:
            raise ValueError("unknown decision")
        db.execute("INSERT INTO orchestration_decisions_v1 VALUES (NULL,?,?,?,?,?,?,?,?)",
                   (work_id, version, call_id, receipt_digest, step, decision, reason, VALIDATOR_VERSION))
        self._event(db, "orchestration.decision", work_id,
                    {"call_id": call_id, "receipt_digest": receipt_digest, "step": step,
                     "decision": decision, "reason": reason, "validator": VALIDATOR_VERSION})

    def record_rejection(self, lease, call_id, reason):
        """Record that a settled model receipt failed validation; it is consumed, not executed."""
        _id(call_id)
        _text(reason)
        with self._transaction() as db:
            self._lease(db, lease)
            declaration = self._declaration(db, lease.task_id, lease.version)
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None or call["work_id"] != lease.task_id or call["state"] not in ("received", "response_rejected"):
                raise StateError("a rejection records a settled receipt of this task")
            prior = self._decisions(db, lease.task_id, lease.version)
            if any(row["call_id"] == call_id for row in prior):
                raise StateError("this receipt already has a recorded decision")
            rejected = sum(row["decision"] == "rejected" for row in prior)
            if rejected >= declaration["limits"]["rejections"]:
                raise BudgetExceeded("task rejection limit exhausted")
            step = json.loads(call["request"]).get("binding", {}).get("step")
            self._record_decision(db, lease.task_id, lease.version, call_id,
                                  sha256(call["response"].encode()).hexdigest(), step, "rejected", reason)

    def _decisions(self, db, work_id, version):
        return db.execute("SELECT * FROM orchestration_decisions_v1 WHERE work_id=? AND version=? ORDER BY seq",
                          (work_id, version)).fetchall()

    def decisions(self, work_id=None):
        with self._transaction() as db:
            sql = "SELECT * FROM orchestration_decisions_v1"
            rows = (db.execute(sql + " WHERE work_id=? ORDER BY seq", (work_id,)) if work_id
                    else db.execute(sql + " ORDER BY seq"))
            return [dict(row) for row in rows]

    # ------------------------------------------------------------ derived artifacts

    def _derived_lease(self, db, work, agent, lease_seconds):
        self._recover(db)
        work = db.execute("SELECT * FROM work WHERE id=?", (work["id"],)).fetchone()
        if work["status"] == "leased" and work["owner"] == agent:
            return Lease(work["id"], work["version"], agent, work["epoch"], self._run(db)["run_id"])
        if work["status"] == "ready":
            return self._claim_received_ready(db, agent, work["id"], lease_seconds)
        return None

    def publish_derived(self, agent, work_id, *, kind, value, source_call_id, lineage,
                        binding=None, lease_seconds=60):
        """Publish a host-derived artifact with explicit lineage, atomically.

        ``kind`` is ``output`` (the typed result of a validated ``submit_output``
        proposal of this task) or ``result`` (a host task's finalization, derived
        from settled receipts of its dependencies). Nothing is fabricated: the
        value must equal the proposal the receipt carries, or be derived from
        receipts named in ``lineage``, all of which must be settled. A work with an
        unresolved call publishes nothing. Repeating the call returns the same
        reference after rechecking access, without revalidating.
        """
        _id(agent)
        _id(source_call_id)
        _duration(lease_seconds)
        if kind not in ARTIFACT_KINDS:
            raise ValueError("artifact kind must be output or result")
        value = contracts.finite_json(value)
        lineage = contracts.finite_json(lineage)
        if type(lineage) is not list or not lineage:
            raise ValueError("explicit lineage required")
        with self._transaction() as db:
            work = self._work(db, work_id, agent)
            declaration = self._declaration(db, work_id, work["version"])
            prior = db.execute("SELECT * FROM artifacts WHERE work_id=?", (work_id,)).fetchone()
            if prior is not None:
                if prior["value"] != _wire(value) or prior["call_id"] != source_call_id:
                    raise StateError("work was published from a different derivation")
                return prior["ref"]
            if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state IN ('reserved','dispatched')",
                          (work_id,)).fetchone():
                raise StateError("work still has an open reservation or unresolved dispatch")
            source, digest = self._verify_derivation(db, declaration, work, kind, value, source_call_id, lineage)
            if len(_wire(value).encode()) > json.loads(self._run(db)["limits"])["artifact_bytes"]:
                raise StateError("derived artifact exceeds the artifact bound")
            lease = self._derived_lease(db, work, agent, lease_seconds)
            if lease is None:
                raise StateError("work cannot be claimed for derived publication")
            record = {"kind": kind, "lineage": lineage, "validator": VALIDATOR_VERSION,
                      **({} if binding is None else {"binding": contracts.finite_json(binding)})}
            ref = self._record_artifact(db, lease, _wire(value), source_call_id, digest, record)
            db.execute("INSERT INTO orchestration_artifacts_v1 VALUES (?,?,?,?,?)",
                       (ref, work_id, work["version"], kind, _wire(lineage)))
            if kind == "output":
                self._record_decision(db, work_id, work["version"], source_call_id, digest,
                                      json.loads(source["request"]).get("binding", {}).get("step"),
                                      "submit", "submit_output admitted")
            return ref

    def _verify_derivation(self, db, declaration, work, kind, value, source_call_id, lineage):
        source = db.execute("SELECT * FROM calls WHERE id=?", (source_call_id,)).fetchone()
        if source is None or source["state"] != "received":
            raise StateError("derivation requires a settled receipt")
        digest = sha256(source["response"].encode()).hexdigest()
        if kind == "output":
            if source["work_id"] != work["id"] or source["version"] != work["version"]:
                raise StateError("an output derives from a receipt of its own task")
            if any(row["call_id"] == source_call_id for row in self._decisions(db, work["id"], work["version"])):
                raise StateError("this receipt already has a recorded decision")
            response = json.loads(source["response"])
            if MODEL_KEY not in response:
                raise StateError("an output derives from a model receipt")
            proposal = contracts.parse_proposal(
                response[MODEL_KEY], tools={}, output_schema=declaration["output_schema"])
            if proposal["kind"] != "submit" or _wire(proposal["output"]) != _wire(value):
                raise StateError("value differs from the receipt's validated proposal")
            if lineage != [{"call_id": source_call_id, "digest": digest, "role": "proposal"}]:
                raise StateError("an output's lineage is exactly its proposal receipt")
            return source, digest
        dependencies = set(declaration["dependencies"])
        seen = set()
        for item in lineage:
            if type(item) is not dict or set(item) != {"call_id", "digest", "role"}:
                raise StateError("each lineage entry needs call_id, digest and role")
            row = db.execute("SELECT * FROM calls WHERE id=?", (item["call_id"],)).fetchone()
            if row is None or row["state"] != "received" or row["work_id"] not in dependencies:
                raise StateError("result lineage must name settled receipts of declared dependencies")
            if sha256(row["response"].encode()).hexdigest() != item["digest"]:
                raise StateError("lineage digest differs from the settled receipt")
            seen.add(item["call_id"])
        if source_call_id not in seen:
            raise StateError("the source receipt must appear in the lineage")
        return source, digest

    def artifact_records(self):
        with self._transaction() as db:
            return [{"ref": row["ref"], "work_id": row["work_id"], "version": row["version"],
                     "kind": row["kind"], "lineage": json.loads(row["lineage"])}
                    for row in db.execute("SELECT * FROM orchestration_artifacts_v1 ORDER BY rowid")]

    def commit(self, work_id, agent=None, **options):
        """Orchestration work has no candidate arbitration locus and never uses one.

        Each task declares one agent and the platform is created with
        ``max_candidates`` of one, so there is nothing to arbitrate. Stating that
        explicitly keeps the boundary loud rather than emergent from the fact that a
        model receipt happens to carry no artifact key.
        """
        with self._transaction() as db:
            if self._task_row(db, work_id) is not None:
                raise StateError("orchestration work does not use candidate arbitration")
        return super().commit(work_id, agent, **options)

    def _publish_received(self, db, agent, call_id, *, verify, lease_seconds=60):
        """Orchestration artifacts are derived; a model or tool receipt is not publishable.

        A receipt here carries ``message`` or ``result``, never ``artifact``, so the
        platform's own candidate path cannot reach one either: ``propose`` refuses it
        for the same structural reason.
        """
        call = db.execute("SELECT work_id FROM calls WHERE id=?", (call_id,)).fetchone()
        if call is not None and self._task_row(db, call["work_id"]) is not None:
            raise StateError("orchestration work publishes only through the derived transition")
        return super()._publish_received(db, agent, call_id, verify=verify, lease_seconds=lease_seconds)

    # ------------------------------------------------------------ decomposition

    def admit_children(self, lease, source_call_id, children, *, join_reserve=None, lease_seconds=60):
        """Admit a validated propose_children proposal: narrowing checks, then decompose.

        The host calls this, never the model. Child capabilities are intersected with
        the parent's, the parent keeps its declared join reserve, and the whole graph
        is validated by the existing platform transition inside one transaction, so a
        rejection leaves no child, no budget transfer and no consumed receipt.
        """
        _id(source_call_id)
        children = contracts.finite_json(children)
        if type(children) is not list or not children:
            raise ValueError("nonempty children required")
        with self._transaction() as db:
            self._lease(db, lease)
            declaration = self._declaration(db, lease.task_id, lease.version)
            config = declaration.get("decomposition")
            if not config:
                raise StateError("this task is not in decomposition mode")
            source = db.execute("SELECT * FROM calls WHERE id=?", (source_call_id,)).fetchone()
            if source is None or source["work_id"] != lease.task_id or source["state"] != "received":
                raise StateError("admission consumes a settled receipt of this task")
            recorded = self._decisions(db, lease.task_id, lease.version)
            if any(row["call_id"] == source_call_id for row in recorded):
                raise StateError("this receipt already has a recorded decision")
            if any(row["decision"] == "decompose" for row in recorded):
                raise StateError("this task version already admitted a decomposition")
            existing = db.execute("SELECT COUNT(*) FROM orchestration_tasks_v2 WHERE parent=?",
                                  (lease.task_id,)).fetchone()[0]
            if existing + len(children) > config["max_children"]:
                raise BudgetExceeded("children exceed the task's declared decomposition bound")
            reserve = config["join_reserve"] if join_reserve is None else join_reserve
            meta = self._budget_row(db, lease.task_id)
            spent_calls, spent_tokens = self._spent(db, lease.task_id)
            spent_steps = sum(json.loads(row["request"]).get("binding", {}).get("kind") == "model"
                              for row in db.execute(
                                  "SELECT request FROM calls WHERE work_id=? AND version=? "
                                  "AND state IN ('received','dispatched','response_rejected')",
                                  (lease.task_id, lease.version)).fetchall())
            if declaration["limits"]["model_steps"] - spent_steps < reserve["model_steps"]:
                raise BudgetExceeded("children would consume the parent's join reserve of model steps")
            names, prepared = set(), []
            siblings = {self._child_id(lease.task_id, child.get("name")) for child in children}
            for child in children:
                prepared.append(self._child_declaration(db, declaration, lease, child, names, siblings))
            give_calls = sum(item["budget"]["calls"] for item in prepared)
            give_tokens = sum(item["budget"]["tokens"] for item in prepared)
            if (meta["calls_cap"] - spent_calls - give_calls < reserve["calls"]
                    or meta["tokens_cap"] - spent_tokens - give_tokens < reserve["tokens"]):
                raise BudgetExceeded("children would consume the parent's join reserve")
            ids = self._decompose(db, lease, [item["work"] for item in prepared])
            for item in prepared:
                db.execute("INSERT INTO orchestration_tasks_v2 VALUES (?,?,?,?,?,?,'decomposition')",
                           (item["task"]["id"], item["task"]["version"], "model",
                            _wire(contracts.eligible_agents(item["task"])), _wire(item["task"]),
                            lease.task_id))
            self._record_decision(db, lease.task_id, lease.version, source_call_id,
                                  sha256(source["response"].encode()).hexdigest(),
                                  json.loads(source["request"]).get("binding", {}).get("step"),
                                  "decompose", "children admitted: " + ", ".join(ids))
            return ids

    def _child_id(self, parent, name):
        if type(name) is not str or not contracts.CHILD_NAME.match(name):
            raise ContractError("child name must match " + contracts.CHILD_NAME.pattern)
        return parent + "." + name

    def _child_declaration(self, db, parent, lease, child, names, siblings):
        key = self._child_id(lease.task_id, child["name"])
        if key in names:
            raise ContractError("duplicate child name")
        names.add(key)
        limits = parent["limits"]
        requested = child["limits"]
        for field in ("model_steps", "tool_calls", "rejections"):
            if requested[field] > limits[field]:
                raise ContractError("a child cannot widen the parent's " + field)
        if not set(child["tools"]) <= set(parent["tools"]):
            raise ContractError("a child cannot widen the parent's tools")
        dependencies = [self._child_id(lease.task_id, name) for name in child["dependencies"]]
        if not set(dependencies) <= siblings - {key}:
            raise ContractError("a child may depend only on its siblings")
        reads = []
        for name in child["reads"]:
            # The parent's own reads are matched first and by their exact task id, so a
            # read whose id is not a legal child name stays requestable and a sibling
            # name cannot shadow it.
            if name in parent["reads"]:
                reads.append(name)
                continue
            derived = (self._child_id(lease.task_id, name)
                       if contracts.CHILD_NAME.match(name) else None)
            if derived is not None and derived in siblings - {key}:
                reads.append(derived)
            else:
                raise ContractError("a child may read only the parent's reads and its siblings")
        if not set(reads) <= set(dependencies) | set(parent["reads"]):
            raise ContractError("a child may read only what it depends on")
        task = contracts.task_spec({
            "id": key, "version": 1, "kind": "model",
            "agents": contracts.eligible_agents(parent),
            "instructions": child["instructions"], "tools": list(child["tools"]),
            "dependencies": sorted(set(dependencies) | (set(reads) & set(parent["reads"]))),
            "reads": reads, "output_schema": parent["decomposition"]["child_output_schema"],
            "limits": requested, "decomposition": None})
        work = {"id": key, "version": 1, "dependencies": task["dependencies"],
                "agents": contracts.eligible_agents(parent), "actions": ["tool.evaluate"],
                "budget": {"calls": requested["calls"], "tokens": requested["tokens"]}}
        return {"task": task, "work": work, "budget": work["budget"]}

    # ------------------------------------------------------------ projection

    def blocked_work(self):
        """Non-terminal work whose declared dependency ended without an artifact.

        A dependency that abstained, was cancelled or was superseded publishes
        nothing, so the dependent can never be claimed. Reporting it is how a host
        terminates instead of polling; nothing here fabricates an artifact or
        abstains on the dependent's behalf.
        """
        with self._transaction() as db:
            out = []
            for row in db.execute("SELECT * FROM work ORDER BY rowid").fetchall():
                if row["status"] == "done":
                    continue
                for producer in json.loads(row["declaration"])["dependencies"]:
                    parent = db.execute("SELECT * FROM work WHERE id=?", (producer,)).fetchone()
                    if parent is None:
                        continue
                    published = db.execute("SELECT 1 FROM artifacts WHERE work_id=?", (producer,)).fetchone()
                    if published:
                        continue
                    if parent["status"] in ("done", "cancelled", "revoked", "superseded"):
                        out.append({"work": row["id"], "dependency": producer, "status": parent["status"]})
                        break
            return out

    def _snapshot_extra(self, db):
        extra = super()._snapshot_extra(db)
        extra["orchestration"] = {
            "spec_digest": self._orchestration(db)["spec_digest"],
            "template_version": self._orchestration(db)["template_version"],
            "tasks": [dict(r) for r in db.execute("SELECT * FROM orchestration_tasks_v2 ORDER BY rowid")],
            "artifacts": [dict(r) for r in db.execute("SELECT * FROM orchestration_artifacts_v1 ORDER BY rowid")],
            "accounting": [dict(r) for r in db.execute("SELECT * FROM orchestration_accounting_v1 ORDER BY rowid")],
            "decisions": [dict(r) for r in db.execute("SELECT * FROM orchestration_decisions_v1 ORDER BY seq")],
        }
        return extra


class OrchestrationSession(OrchestrationMixin, PlatformMixin, Session):
    """Opt-in orchestration ledger; the inspection CLI never creates one.

    These tables are a domain extension of the platform ledger, not a layer beneath
    it: every call, lease, budget and candidate transition is still the platform's.
    """
