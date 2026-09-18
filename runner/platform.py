"""Bounded local work transitions; all decisions and reservations commit atomically.

Losses on proposals are caller attestations, not certificates computed here.
The trusted host supplies identities. No messages, provider calls or planner are
implemented by these transitions.
"""

from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile

from .session import Session, _duration, _id, _integer, _wire
from pheroos_interaction.records import BudgetExceeded, Lease, LeaseLost, StateError


def _loss(value, name):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _text(value, maximum=4096):
    if type(value) is not str or not value.strip() or len(value.encode()) > maximum:
        raise ValueError("bounded nonempty text required")
    return value


def _unique(values, name):
    if type(values) is not list:
        raise ValueError(f"{name} must be a list")
    for value in values:
        _id(value)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


class PlatformMixin:
    """Compose with Session or CoordinationSession; the base ledger owns calls."""

    @classmethod
    def create(cls, path, run_id, *, platform=None, **options):
        if platform is not None and type(platform) is not dict:
            raise ValueError("platform options must be a dictionary")
        platform = dict(platform or {})
        limits = {name: platform.pop(name, default) for name, default in
                  (("max_children", 8), ("max_depth", 3), ("max_candidates", 8),
                   ("max_work_items", 1024), ("max_platform_operations", 1024))}
        budgets = platform.pop("budgets", {})
        if platform or type(budgets) is not dict:
            raise ValueError("unknown platform options or invalid budgets")
        for name, value in limits.items():
            _integer(value, name, 1)
        work = options.get("work", [])
        if type(work) is not list or len(work) > limits["max_work_items"]:
            raise ValueError("work exceeds platform capacity")
        ids = {item["id"] for item in work}
        if set(budgets) - ids:
            raise ValueError("budget refers to undeclared work")
        for budget in budgets.values():
            if type(budget) is not dict or set(budget) - {"calls", "tokens"}:
                raise ValueError("budget requires calls/tokens only")
            for name, value in budget.items():
                _integer(value, name)
        # Publish only a fully configured database; a failed initializer cannot
        # leave a usable Session at the requested path. Hard-link refuses replace.
        target = Path(path)
        with tempfile.TemporaryDirectory(prefix=".pheroos-create-", dir=target.parent) as tmp:
            session = super().create(Path(tmp)/"session.sqlite", run_id, **options)
            with session._transaction() as db:
                for sql in (
                    "CREATE TABLE platform_v1 (id INTEGER PRIMARY KEY CHECK(id=1), limits TEXT)",
                    "CREATE TABLE platform_work_v1 (work_id TEXT PRIMARY KEY REFERENCES work(id), created REAL, parent TEXT REFERENCES work(id), depth INTEGER, calls_cap INTEGER, tokens_cap INTEGER, original_calls INTEGER, original_tokens INTEGER)",
                    "CREATE TABLE platform_candidates_v1 (call_id TEXT PRIMARY KEY REFERENCES calls(id), work_id TEXT REFERENCES work(id), version INTEGER, proposer TEXT, certified_loss REAL, artifact_digest TEXT)",
                    "CREATE TABLE platform_no_entry_v1 (work_id TEXT PRIMARY KEY REFERENCES work(id), until REAL, reason TEXT)",
                    "CREATE TABLE platform_decisions_v1 (work_id TEXT PRIMARY KEY REFERENCES work(id), version INTEGER, value TEXT)",
                ):
                    db.execute(sql)
                db.execute("INSERT INTO platform_v1 VALUES (1,?)", (_wire(limits),))
                run_limits = json.loads(session._run(db)["limits"])
                for row in db.execute("SELECT id FROM work").fetchall():
                    b = budgets.get(row["id"], {})
                    calls = b.get("calls", run_limits["max_calls"])
                    tokens = b.get("tokens", run_limits["token_cap"])
                    if calls > run_limits["max_calls"] or tokens > run_limits["token_cap"]:
                        raise ValueError("work budget exceeds session limits")
                    db.execute("INSERT INTO platform_work_v1 VALUES (?,?,NULL,0,?,?,?,?)",
                               (row["id"], session.clock(), calls, tokens, calls, tokens))
            os.link(session.path, target)
            # SQLite FULL commits the file; make its final directory entry durable.
            parent_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            session.path = str(target)
        return session

    def _platform_limits(self, db):
        return json.loads(db.execute("SELECT limits FROM platform_v1 WHERE id=1").fetchone()[0])

    def _event(self, db, kind, work, payload):
        # Release only drains a previously admitted lease; it must work at the
        # limit. Its count is bounded by admitted claims. Settlement also drains.
        if kind == "claimed" or (kind.startswith("platform.") and kind != "platform.released"):
            used = sum(e["event_type"] == "interaction.session.claimed" or
                       (e["event_type"].startswith("interaction.session.platform.") and
                        e["event_type"] != "interaction.session.platform.released")
                       for e in (json.loads(r[0]) for r in db.execute("SELECT value FROM events")))
            if used >= self._platform_limits(db)["max_platform_operations"]:
                raise BudgetExceeded("platform operation budget exhausted")
        super()._event(db, kind, work, payload)

    def _budget_row(self, db, work_id):
        row = db.execute("SELECT * FROM platform_work_v1 WHERE work_id=?", (work_id,)).fetchone()
        if row is None:
            raise StateError("work has no platform budget")
        return row

    def _spent(self, db, work_id):
        calls = db.execute("SELECT state,reserved,actual FROM calls WHERE work_id=?", (work_id,)).fetchall()
        return len(calls), sum(c["reserved"] if c["state"] in ("reserved", "dispatched") else c["actual"] or 0 for c in calls)

    def _reservation_capacity(self, db, lease, prompt_tokens, max_new_tokens):
        super()._reservation_capacity(db, lease, prompt_tokens, max_new_tokens)
        if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (lease.task_id,)).fetchone():
            raise StateError("work still has an unresolved dispatch")
        meta = self._budget_row(db, lease.task_id)
        calls, tokens = self._spent(db, lease.task_id)
        if calls+1 > meta["calls_cap"] or tokens+prompt_tokens+max_new_tokens > meta["tokens_cap"]:
            raise BudgetExceeded("work budget exhausted")

    def _work(self, db, work_id, agent=None):
        _id(work_id)
        run = self._run(db)
        row = db.execute("SELECT * FROM work WHERE id=?", (work_id,)).fetchone()
        if row is None:
            raise StateError("unknown work")
        if not run["enabled"] or run["status"] not in ("running", "completed"):
            raise StateError("session cancelled or revoked")
        if row["status"] in ("superseded", "revoked", "cancelled"):
            raise LeaseLost("work superseded or revoked")
        if agent is not None:
            _id(agent)
            self._publication_access(db, row, agent)
        return row

    def _available(self, db, row, agent, *, mark=True):
        if agent not in json.loads(row["declaration"])["agents"]:
            return False
        try:
            self._publication_access(db, row, agent)
        except (PermissionError, LeaseLost):
            return False
        if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (row["id"],)).fetchone():
            return False
        if any(not db.execute("SELECT 1 FROM artifacts WHERE work_id=?", (dep,)).fetchone()
               for dep in json.loads(row["declaration"])["dependencies"]):
            return False
        held = db.execute("SELECT until FROM platform_no_entry_v1 WHERE work_id=?", (row["id"],)).fetchone()
        return not (mark and held and held[0] > self.clock())

    def ready_work(self, agent):
        """Read-only metadata; expired leases are projected, recovered only on claim."""
        _id(agent)
        with self._transaction() as db:
            run = self._run(db)
            if agent not in json.loads(run["agents"]):
                raise StateError("undeclared agent")
            if run["status"] != "running" or not run["enabled"]:
                return []
            now = self.clock()
            out = []
            for row in db.execute("SELECT * FROM work ORDER BY rowid").fetchall():
                ready = row["status"] == "ready" or (row["status"] == "leased" and row["expires"] <= now)
                if not ready or not self._available(db, row, agent):
                    continue
                meta = self._budget_row(db, row["id"])
                calls, tokens = self._spent(db, row["id"])
                out.append({"id": row["id"], "version": row["version"], "age": max(0., now-meta["created"]),
                            "depth": meta["depth"], "parent": meta["parent"],
                            "remaining": {"calls": meta["calls_cap"]-calls, "tokens": meta["tokens_cap"]-tokens}})
            return out

    def _claim_ready(self, db, agent, work_id, lease_seconds):
        for row in db.execute("SELECT * FROM work WHERE status='ready' ORDER BY rowid").fetchall():
            if (work_id is None or row["id"] == work_id) and self._available(db, row, agent):
                return super()._claim_ready(db, agent, row["id"], lease_seconds)
        return None

    def _claim_received_ready(self, db, agent, work_id, lease_seconds):
        row = db.execute("SELECT * FROM work WHERE id=? AND status='ready'", (work_id,)).fetchone()
        if row is not None and self._available(db, row, agent, mark=False):
            return super()._claim_ready(db, agent, work_id, lease_seconds)
        return None

    def work_calls(self, lease):
        """Same-work recovery context, fenced by current lease and source access."""
        with self._transaction() as db:
            self._lease(db, lease)
            return [{**dict(r), "request": json.loads(r["request"]),
                     "response": json.loads(r["response"]) if r["response"] else None}
                    for r in db.execute("SELECT * FROM calls WHERE work_id=? AND version=? ORDER BY rowid",
                                        (lease.task_id, lease.version)).fetchall()]

    def decompose(self, lease, children, *, parent_depends=True):
        """Transfer caps atomically. Existing artifact dependencies remain mandatory."""
        if parent_depends is not True:
            raise ValueError("parent must wait for its children")
        if type(children) is not list or not children:
            raise ValueError("nonempty children required")
        with self._transaction() as db:
            return self._decompose(db, lease, children)

    def _decompose(self, db, lease, children):
        """Transaction body of decompose; composite admissions share the caller's transaction."""
        # Detach caller-owned objects before validating or storing them.
        children = json.loads(_wire(children))
        parent = self._lease(db, lease)
        meta = self._budget_row(db, lease.task_id)
        limits = self._platform_limits(db)
        if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state IN ('reserved','dispatched')", (lease.task_id,)).fetchone():
            raise StateError("decompose requires no open reservation or unresolved dispatch")
        n_children = db.execute("SELECT COUNT(*) FROM platform_work_v1 WHERE parent=?", (lease.task_id,)).fetchone()[0]
        n_work = db.execute("SELECT COUNT(*) FROM work").fetchone()[0]
        if n_children+len(children) > limits["max_children"] or meta["depth"]+1 > limits["max_depth"] or n_work+len(children) > limits["max_work_items"]:
            raise BudgetExceeded("child, depth or work capacity exceeded")
        declaration = json.loads(parent["declaration"])
        graph = {r["id"]: json.loads(r["declaration"])["dependencies"] for r in db.execute("SELECT id,declaration FROM work")}
        calls, tokens = self._spent(db, lease.task_id)
        give_calls = give_tokens = 0
        ids = []
        for child in children:
            if type(child) is not dict or set(child) != {"id", "version", "dependencies", "agents", "actions", "budget"}:
                raise ValueError("child needs id/version/dependencies/agents/actions/budget")
            key = _id(child["id"])
            _integer(child["version"], "child version", 1)
            if key in graph:
                raise ValueError("duplicate or existing child id")
            for name in ("dependencies", "agents", "actions"):
                _unique(child[name], name)
            if (not child["agents"] or not set(child["agents"]) <= set(declaration["agents"])
                    or not child["actions"] or not set(child["actions"]) <= set(declaration["actions"])):
                raise ValueError("child cannot widen parent agents or actions")
            for agent in child["agents"]:
                self._publication_access(db, parent, agent)
            budget = child["budget"]
            if type(budget) is not dict or set(budget) != {"calls", "tokens"}:
                raise ValueError("explicit child calls/tokens required")
            give_calls += _integer(budget["calls"], "child calls")
            give_tokens += _integer(budget["tokens"], "child tokens")
            ids.append(key)
            graph[key] = child["dependencies"]
        if give_calls+calls > meta["calls_cap"] or give_tokens+tokens > meta["tokens_cap"]:
            raise BudgetExceeded("children exceed parent remaining budget")
        graph[lease.task_id] = declaration["dependencies"]+ids
        # Topological elimination covers cycles through all existing work.
        pending = {key: set(deps) for key, deps in graph.items()}
        if any(deps-set(graph) for deps in pending.values()):
            raise ValueError("missing child dependency")
        while pending:
            leaves = {key for key, deps in pending.items() if not deps}
            if not leaves:
                raise ValueError("cyclic work dependencies")
            pending = {key: deps-leaves for key, deps in pending.items() if key not in leaves}
        inherited = self._inspection(db, lease.task_id) if hasattr(self, "_inspection") else None
        if inherited is not None:
            cap = json.loads(db.execute("SELECT limits FROM coordination_v1 WHERE id=1").fetchone()[0])["max_index_entries"]
            count = db.execute("SELECT COUNT(*) FROM coordination_inspections_v1").fetchone()[0]
            if count+len(children) > cap:
                raise BudgetExceeded("inspection index capacity exceeded")
        for child in children:
            item = {k: child[k] for k in ("id", "version", "dependencies", "agents", "actions")}
            db.execute("INSERT INTO work VALUES (?,?,?,'ready',NULL,0,NULL,?)",
                       (child["id"], child["version"], _wire(item), self._run(db)["generation"]))
            c, t = child["budget"]["calls"], child["budget"]["tokens"]
            db.execute("INSERT INTO platform_work_v1 VALUES (?,?,?,?,?,?,?,?)",
                       (child["id"], self.clock(), lease.task_id, meta["depth"]+1, c, t, c, t))
            if inherited is not None:
                self._inspection_declaration(db, dict(work_id=child["id"], source_id=inherited["source_id"],
                    source_version=inherited["source_version"], tool_ref=inherited["tool_ref"],
                    tool_version=inherited["tool_version"], arguments=json.loads(inherited["arguments"]),
                    state_fingerprint=inherited["fingerprint"], readers=json.loads(inherited["readers"])))
        declaration["dependencies"] = graph[lease.task_id]
        db.execute("UPDATE platform_work_v1 SET calls_cap=calls_cap-?,tokens_cap=tokens_cap-? WHERE work_id=?", (give_calls, give_tokens, lease.task_id))
        db.execute("UPDATE work SET declaration=?,status='ready',owner=NULL,expires=NULL WHERE id=?", (_wire(declaration), lease.task_id))
        self._event(db, "platform.decomposed", lease.task_id,
                    {"children": children, "transferred": {"calls": give_calls, "tokens": give_tokens}, "epoch": lease.epoch})
        return ids

    def release(self, lease):
        with self._transaction() as db:
            self._lease(db, lease)
            self._abandon(db, lease.task_id)
            unknown = db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (lease.task_id,)).fetchone()
            status = "uncertain" if unknown else "ready"
            db.execute("UPDATE work SET status=?,owner=NULL,expires=NULL WHERE id=?", (status, lease.task_id))
            self._event(db, "platform.released", lease.task_id, {"epoch": lease.epoch, "status": status})
            return status

    def renew(self, lease, lease_seconds=60):
        _duration(lease_seconds)
        with self._transaction() as db:
            row = self._lease(db, lease)
            expires = max(row["expires"], self.clock()+lease_seconds)
            _duration(expires)
            if expires != row["expires"]:
                db.execute("UPDATE work SET expires=? WHERE id=?", (expires, lease.task_id))
                self._event(db, "platform.renewed", lease.task_id, {"epoch": lease.epoch, "expires": expires})
            return expires

    def mark_no_entry(self, work_id, until, reason):
        """Host scheduling hint only; explicit receipt recovery remains possible."""
        _duration(until)
        _text(reason)
        with self._transaction() as db:
            work = self._work(db, work_id)
            if work["status"] == "done":
                raise StateError("work already terminal")
            prior = db.execute("SELECT until,reason FROM platform_no_entry_v1 WHERE work_id=?", (work_id,)).fetchone()
            if prior and tuple(prior) == (until, reason):
                return
            db.execute("INSERT OR REPLACE INTO platform_no_entry_v1 VALUES (?,?,?)", (work_id, until, reason))
            self._event(db, "platform.no_entry", work_id, {"until": until, "reason": reason})

    def propose(self, lease, call_id, certified_loss):
        """Record a caller-attested loss for an authorized settled receipt."""
        _id(call_id)
        certified_loss = _loss(certified_loss, "certified_loss")
        with self._transaction() as db:
            self._lease(db, lease)
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None or (call["work_id"], call["version"], call["state"], call["action"]) != (lease.task_id, lease.version, "received", "tool.evaluate"):
                raise StateError("proposal requires a settled receipt for this work/version")
            response = json.loads(call["response"])
            if "artifact" not in response:
                raise StateError("receipt lacks artifact")
            digest = sha256(_wire(response["artifact"]).encode()).hexdigest()
            values = (call_id, lease.task_id, lease.version, lease.owner, certified_loss, digest)
            prior = db.execute("SELECT * FROM platform_candidates_v1 WHERE call_id=?", (call_id,)).fetchone()
            if prior:
                if tuple(prior) != values:
                    raise StateError("conflicting proposal")
                return dict(prior)
            count = db.execute("SELECT COUNT(*) FROM platform_candidates_v1 WHERE work_id=?", (lease.task_id,)).fetchone()[0]
            if count >= self._platform_limits(db)["max_candidates"]:
                raise BudgetExceeded("candidate capacity exceeded")
            db.execute("INSERT INTO platform_candidates_v1 VALUES (?,?,?,?,?,?)", values)
            self._event(db, "platform.proposed", lease.task_id, {"call_id": call_id, "certified_loss": certified_loss,
                       "proposer": lease.owner, "artifact_digest": digest})
            return dict(db.execute("SELECT * FROM platform_candidates_v1 WHERE call_id=?", (call_id,)).fetchone())

    def candidates(self, work_id, agent=None):
        """Current candidate metadata; omitted agent is the trusted-host audit API."""
        with self._transaction() as db:
            work = self._work(db, work_id, agent)
            return self._candidates(db, work)

    def _candidates(self, db, work):
        return [dict(r) for r in db.execute("SELECT * FROM platform_candidates_v1 WHERE work_id=? AND version=? ORDER BY certified_loss,call_id", (work["id"], work["version"]))]

    def _decision(self, db, work):
        row = db.execute("SELECT * FROM platform_decisions_v1 WHERE work_id=?", (work["id"],)).fetchone()
        return json.loads(row["value"]) if row and row["version"] == work["version"] else None

    def _abstain(self, db, lease, result):
        self._lease(db, lease)
        if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (lease.task_id,)).fetchone():
            raise StateError("cannot abandon an unresolved dispatch")
        self._abandon(db, lease.task_id)
        db.execute("UPDATE work SET status='done',owner=NULL,expires=NULL WHERE id=?", (lease.task_id,))
        db.execute("INSERT INTO platform_decisions_v1 VALUES (?,?,?)", (lease.task_id, lease.version, _wire(result)))
        self._event(db, "platform.abstained", lease.task_id, result)
        if not db.execute("SELECT 1 FROM work WHERE status!='done'").fetchone():
            db.execute("UPDATE run SET status='completed'")
        return result

    def abstain(self, lease, *, reason="abstain"):
        _text(reason)
        with self._transaction() as db:
            # A lease transition is always fenced, even after terminalization.
            return self._abstain(db, lease, {"decision": "abstain", "publisher": lease.owner, "reason": reason})

    def commit(self, work_id, agent=None, *, verify, abstain_loss, rule=None, lease_seconds=60):
        """Atomic decision + receipt publication. None abstains; explicit wait waits.

        rule(candidate_metadata, abstain_loss) returns a candidate call id, None,
        or {'decision': 'wait'}. It and verify must be pure local functions.
        """
        abstain_loss = _loss(abstain_loss, "abstain_loss")
        _duration(lease_seconds)
        if not callable(verify) or (rule is not None and not callable(rule)):
            raise ValueError("pure local verifier and optional decision rule required")
        with self._transaction() as db:
            work = self._work(db, work_id, agent)
            prior = self._decision(db, work)
            if prior:
                self._publication_access(db, work, agent or prior["publisher"])
                return prior
            rows = self._candidates(db, work)
            if not rows:
                return {"decision": "no_candidate", "candidates": 0}
            publisher = agent or rows[0]["proposer"]
            chosen = (rows[0]["call_id"] if rows[0]["certified_loss"] < abstain_loss else None) if rule is None else rule(json.loads(_wire(rows)), abstain_loss)
            if chosen == {"decision": "wait"}:
                self._publication_access(db, work, publisher)
                # Stamp the decision so a waiting policy can read elapsed ledger time
                # rather than a count of polls; repeated sweeps do not advance a clock.
                self._event(db, "platform.waited", work_id, {"candidates": len(rows), "abstain_loss": abstain_loss,
                                                             "at": self.clock()})
                return {"decision": "wait", "candidates": len(rows)}
            candidate = next((r for r in rows if r["call_id"] == chosen), None)
            if chosen is not None and candidate is None:
                raise StateError("rule chose a non-candidate")
            if candidate is not None and candidate["certified_loss"] >= abstain_loss:
                raise StateError("rule cannot publish at or above abstention loss")
            if candidate is not None:
                publisher = agent or candidate["proposer"]
                # Same transaction body as publish_received; recovery, verify,
                # publication, platform cap and decision event all roll back.
                ref = self._publish_received(db, publisher, chosen, verify=verify, lease_seconds=lease_seconds)
                result = {"decision": "publish", "call_id": chosen, "artifact_ref": ref,
                          "publisher": publisher, "candidates": len(rows)}
                db.execute("INSERT INTO platform_decisions_v1 VALUES (?,?,?)", (work_id, work["version"], _wire(result)))
                self._event(db, "platform.committed", work_id, result)
                return result
            self._publication_access(db, work, publisher)
            self._recover(db)
            work = db.execute("SELECT * FROM work WHERE id=?", (work_id,)).fetchone()
            if work["status"] == "leased" and work["owner"] == publisher:
                lease = Lease(work_id, work["version"], publisher, work["epoch"], self._run(db)["run_id"])
            elif work["status"] == "ready":
                lease = self._claim_received_ready(db, publisher, work_id, lease_seconds)
            else:
                lease = None
            if lease is None:
                raise StateError("work cannot be reclaimed for abstention")
            return self._abstain(db, lease, {"decision": "abstain", "publisher": publisher,
                                  "candidates": len(rows), "abstain_loss": abstain_loss})

    def _publish(self, db, lease, call_id, artifact, verify):
        self._lease(db, lease)
        if db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (lease.task_id,)).fetchone():
            raise StateError("work still has an unresolved dispatch")
        return super()._publish(db, lease, call_id, artifact, verify)

    def _snapshot_extra(self, db):
        extra = super()._snapshot_extra(db)
        extra["platform"] = {
            "limits": self._platform_limits(db),
            "work": [dict(r) for r in db.execute("SELECT * FROM platform_work_v1 ORDER BY rowid")],
            "candidates": [dict(r) for r in db.execute("SELECT * FROM platform_candidates_v1 ORDER BY rowid")],
            "no_entry": [dict(r) for r in db.execute("SELECT * FROM platform_no_entry_v1 ORDER BY rowid")],
            "decisions": [dict(r) for r in db.execute("SELECT * FROM platform_decisions_v1 ORDER BY rowid")],
        }
        return extra


class PlatformSession(PlatformMixin, Session):
    """Opt-in local platform session; no changes to the inspection planner."""
