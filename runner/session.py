"""Durable local tool execution with leases, limits, cancellation and receipts."""

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import time

from pheroos_interaction.records import BudgetExceeded, Lease, LeaseLost, StateError


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an exact integer >= {minimum}")
    return value


def _id(value):
    if type(value) is not str or not value.strip() or len(value.encode()) > 128:
        raise ValueError("nonempty identity of at most 128 bytes required")
    return value


def _duration(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("positive finite duration required")
    return value


class Session:
    def __init__(self, path, *, clock=None):
        self.path, self.clock = str(path), clock or time.time

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @classmethod
    def create(cls, path, run_id, *, agents, work, token_cap, max_calls,
               context_bytes=4096,
               artifact_bytes=8192, clock=None):
        _id(run_id)
        if (type(agents) is not list or not agents or len(set(agents)) != len(agents)
                or type(work) is not list or not work):
            raise ValueError("nonempty unique agents and work required")
        for agent in agents:
            _id(agent)
        declarations = {}
        for item in work:
            if set(item) != {"id", "version", "dependencies", "agents", "actions"}:
                raise ValueError("explicit work identity/version/dependencies/agents/actions required")
            key = _id(item["id"])
            _integer(item["version"], "work version", 1)
            if key in declarations:
                raise ValueError("duplicate work")
            for name in ("dependencies", "agents", "actions"):
                values = item[name]
                if type(values) is not list or len(set(values)) != len(values):
                    raise ValueError("unique declaration lists required")
            if (not item["agents"] or not set(item["agents"]) <= set(agents)
                    or not item["actions"] or not set(item["actions"]) <= {"tool.evaluate"}):
                raise ValueError("undeclared agent or action")
            declarations[key] = item
        def visit(key, ancestors):
            if key not in declarations or key in ancestors:
                raise ValueError("missing or cyclic dependency")
            for parent in declarations[key]["dependencies"]:
                visit(parent, ancestors | {key})
        for key in declarations:
            visit(key, set())
        limits = {"token_cap": token_cap, "max_calls": max_calls, "context_bytes": context_bytes,
                  "artifact_bytes": artifact_bytes}
        for name, value in limits.items():
            _integer(value, name, 0 if name == "token_cap" else 1)
        with Path(path).open("xb"):
            pass
        session = cls(path, clock=clock)
        with session._transaction() as db:
            for sql in (
                "CREATE TABLE run (id INTEGER PRIMARY KEY CHECK(id=1), run_id TEXT, status TEXT, generation INTEGER, enabled INTEGER, agents TEXT, limits TEXT)",
                "CREATE TABLE work (id TEXT PRIMARY KEY, version INTEGER, declaration TEXT, status TEXT, owner TEXT, epoch INTEGER, expires REAL, generation INTEGER)",
                "CREATE TABLE calls (id TEXT PRIMARY KEY, work_id TEXT REFERENCES work(id), version INTEGER, epoch INTEGER, action TEXT, request TEXT, state TEXT, prompt INTEGER, maximum INTEGER, reserved INTEGER, response TEXT, actual INTEGER, permission TEXT)",
                "CREATE TABLE artifacts (ref TEXT PRIMARY KEY, work_id TEXT UNIQUE REFERENCES work(id), version INTEGER, publisher TEXT, value TEXT, call_id TEXT, response_digest TEXT, permission TEXT)",
                "CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)",
            ):
                db.execute(sql)
            db.execute("INSERT INTO run VALUES (1,?,'running',0,1,?,?)", (run_id, _wire(agents), _wire(limits)))
            for item in work:
                db.execute("INSERT INTO work VALUES (?,?,?,'ready',NULL,0,NULL,0)",
                           (item["id"], item["version"], _wire(item)))
            session._event(db, "created", "", {"run_id": run_id, "limits": limits})
        return session

    def _event(self, db, kind, work, payload):
        event = dict(event_type="interaction.session." + kind, task_id=work or "run", details=payload)
        db.execute("INSERT INTO events(value) VALUES (?)", (_wire(event),))

    def _run(self, db):
        return db.execute("SELECT * FROM run").fetchone()

    def _lease(self, db, lease):
        if not isinstance(lease, Lease) or type(lease.version) is not int or type(lease.epoch) is not int:
            raise LeaseLost("exact lease version and epoch required")
        run = self._run(db)
        row = db.execute("SELECT * FROM work WHERE id=?", (lease.task_id,)).fetchone()
        if (lease.run_id != run["run_id"] or not run["enabled"] or run["status"] != "running" or row is None
                or (row["version"], row["owner"], row["epoch"], row["status"], row["generation"])
                != (lease.version, lease.owner, lease.epoch, "leased", run["generation"])
                or row["expires"] <= self.clock()):
            raise LeaseLost("expired, cancelled, revoked or superseded work lease")
        return row

    def _abandon(self, db, work):
        pending = db.execute("SELECT id,reserved FROM calls WHERE work_id=? AND state='reserved'", (work,)).fetchall()
        db.execute("UPDATE calls SET state='abandoned',actual=0 WHERE work_id=? AND state='reserved'", (work,))
        for call in pending:
            self._event(db, "reservation_abandoned", work, {"call_id": call["id"], "released_tokens": call["reserved"]})

    def _recover(self, db):
        if self._run(db)["status"] != "running":
            return
        for row in db.execute("SELECT * FROM work WHERE status='leased' AND expires<=?", (self.clock(),)).fetchall():
            self._abandon(db, row["id"])
            unknown = db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (row["id"],)).fetchone()
            status = "uncertain" if unknown else "ready"
            db.execute("UPDATE work SET status=?,owner=NULL,expires=NULL WHERE id=?", (status, row["id"]))
            self._event(db, "lease_expired", row["id"], {"epoch": row["epoch"], "status": status})

    def recover(self):
        with self._transaction() as db:
            self._recover(db)

    def claim(self, agent, work_id=None, *, lease_seconds=60):
        _duration(lease_seconds)
        with self._transaction() as db:
            run = self._run(db)
            if agent not in json.loads(run["agents"]):
                raise StateError("undeclared agent")
            self._recover(db)
            if run["status"] != "running" or not run["enabled"]:
                return None
            for row in db.execute("SELECT * FROM work WHERE status='ready' ORDER BY rowid").fetchall():
                item = json.loads(row["declaration"])
                if (work_id is not None and row["id"] != work_id) or agent not in item["agents"]:
                    continue
                if any(db.execute("SELECT 1 FROM artifacts WHERE work_id=?", (dep,)).fetchone() is None for dep in item["dependencies"]):
                    continue
                lease = Lease(row["id"], row["version"], agent, row["epoch"] + 1, run["run_id"])
                db.execute("UPDATE work SET status='leased',owner=?,epoch=?,expires=?,generation=? WHERE id=?",
                           (agent, lease.epoch, self.clock() + lease_seconds, run["generation"], row["id"]))
                self._event(db, "claimed", row["id"], asdict(lease))
                return lease
        return None

    def check_current(self, lease):
        """Fence a local read against cancellation, lease expiry and source changes."""
        with self._transaction() as db:
            self._lease(db, lease)

    def reserve(self, lease, call_id, action, payload, *, prompt_tokens, max_new_tokens):
        _id(call_id)
        _integer(prompt_tokens, "prompt_tokens")
        _integer(max_new_tokens, "max_new_tokens")
        if type(payload) is not dict:
            raise ValueError("dictionary request required")
        payload = dict(payload)
        for key, value in (("task_id", lease.task_id), ("version", lease.version)):
            if key in payload and (type(payload[key]) is not type(value) or payload[key] != value):
                raise StateError("request task/version mismatch")
            payload[key] = value
        wire = _wire(payload)
        with self._transaction() as db:
            row = self._lease(db, lease)
            limits = json.loads(self._run(db)["limits"])
            if action not in json.loads(row["declaration"])["actions"] or len(wire.encode()) > limits["context_bytes"]:
                raise StateError("undeclared action or request exceeds context bound")
            prior = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if prior:
                if (prior["work_id"], prior["version"], prior["action"], prior["request"], prior["prompt"], prior["maximum"], prior["state"]) != (lease.task_id, lease.version, action, wire, prompt_tokens, max_new_tokens, "received"):
                    raise StateError("call already exists or is unresolved")
                return call_id
            calls = db.execute("SELECT state,reserved,actual FROM calls").fetchall()
            spent = sum(call["reserved"] if call["state"] in ("reserved", "dispatched") else call["actual"] for call in calls)
            if len(calls) >= limits["max_calls"] or spent + prompt_tokens + max_new_tokens > limits["token_cap"]:
                raise BudgetExceeded("session call/token budget exhausted")
            db.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,'reserved',?,?,?,NULL,NULL,NULL)",
                       (call_id, lease.task_id, lease.version, lease.epoch, action, wire, prompt_tokens, max_new_tokens, prompt_tokens + max_new_tokens))
            self._event(db, "reserved", lease.task_id, {"call_id": call_id,
                "tokens": prompt_tokens + max_new_tokens, "prompt_tokens": prompt_tokens,
                "max_new_tokens": max_new_tokens, "prompt_token_contract": "exact_v1"})
        return call_id

    def _scope_ref(self, db, task_id):
        return "interaction:" + sha256(_wire([self._run(db)["run_id"], task_id]).encode()).hexdigest()

    def _permit(self, db, lease, action, payload):
        """Real local checks for a trusted host; no legacy authority certificate."""
        row = self._lease(db, lease)
        actions = json.loads(row["declaration"])["actions"]
        required = "tool.evaluate" if action == "artifact.publish" else action
        if required not in actions or action not in {"tool.evaluate", "artifact.publish"}:
            raise PermissionError("action is outside this work declaration")
        if (payload.get("task_id") != lease.task_id or type(payload.get("version")) is not int
                or payload["version"] != lease.version):
            raise PermissionError("request is not bound to current work")
        scope_ref = self._scope_ref(db, lease.task_id)
        if "scope_ref" in payload and payload["scope_ref"] != scope_ref:
            raise PermissionError("foreign scope")
        return dict(profile="trusted-host-local-v1", scope_ref=scope_ref,
                    task_id=lease.task_id, version=lease.version, owner=lease.owner, action=action)

    def dispatch(self, lease, call_id):
        with self._transaction() as db:
            self._lease(db, lease)
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None or (call["work_id"], call["version"], call["epoch"], call["state"]) != (lease.task_id, lease.version, lease.epoch, "reserved"):
                raise StateError("dispatch requires this lease's reserved call")
            payload = json.loads(call["request"])
            permission = self._permit(db, lease, call["action"], payload)
            db.execute("UPDATE calls SET state='dispatched',permission=? WHERE id=?", (_wire(permission), call_id))
            self._event(db, "dispatched", lease.task_id, {"call_id": call_id, "permission": permission})
            return payload

    def receive(self, call_id, response):
        wire = _wire(response)
        if type(response) is not dict:
            raise ValueError("dictionary response required")
        prompt = _integer(response.get("prompt_tokens"), "prompt_tokens")
        completion = _integer(response.get("completion_tokens"), "completion_tokens")
        rejected = False
        with self._transaction() as db:
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None:
                raise StateError("unknown call")
            if call["state"] == "received" and call["response"] == wire:
                return
            digest = sha256(wire.encode()).hexdigest()
            if call["state"] == "response_rejected" and json.loads(call["response"])["response_digest"] == digest:
                rejected = True
            else:
                valid_prompt = prompt == call["prompt"]
                if call["state"] != "dispatched" or not valid_prompt or completion > call["maximum"]:
                    raise StateError("conflicting or invalid receipt")
                rejected = len(wire.encode()) > json.loads(self._run(db)["limits"])["artifact_bytes"]
                if rejected:
                    retained = {"response_rejected": "response_bytes_exceeded", "response_digest": digest,
                                "response_bytes": len(wire.encode()), "prompt_tokens": prompt, "completion_tokens": completion}
                    stored, state = _wire(retained), "response_rejected"
                else:
                    stored, state = wire, "received"
                db.execute("UPDATE calls SET state=?,response=?,actual=? WHERE id=?", (state, stored, prompt + completion, call_id))
                self._event(db, state, call["work_id"], {"call_id": call_id, "actual_tokens": prompt + completion,
                                                        "prompt_tokens": prompt, "completion_tokens": completion,
                                                        "prompt_token_contract": "exact_v1",
                                                        "released_tokens": call["reserved"] - prompt - completion,
                                                        "response_digest": digest})
                if self._run(db)["status"] == "running" and not db.execute("SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (call["work_id"],)).fetchone():
                    updated = db.execute("UPDATE work SET status='ready' WHERE id=? AND status='uncertain'", (call["work_id"],)).rowcount
                    if updated:
                        self._event(db, "reconciled", call["work_id"], {"call_id": call_id})
        if rejected:
            raise StateError("response rejected: payload exceeds bound; valid usage durably settled")

    def call(self, call_id):
        with self._transaction() as db:
            row = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if row is None:
                raise StateError("unknown call")
            return {**dict(row), "request": json.loads(row["request"]),
                    "response": json.loads(row["response"]) if row["response"] else None}

    def publish(self, lease, call_id, artifact, *, verify):
        wire = _wire(artifact)
        with self._transaction() as db:
            self._lease(db, lease)
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if (call is None or (call["work_id"], call["version"], call["state"], call["action"]) != (lease.task_id, lease.version, "received", "tool.evaluate")
                    or "artifact" not in json.loads(call["response"]) or _wire(json.loads(call["response"])["artifact"]) != wire
                    or len(wire.encode()) > json.loads(self._run(db)["limits"])["artifact_bytes"]
                    or verify(lease.task_id, json.loads(wire)) is not True):
                raise StateError("artifact lacks matching settled response or independent verification")
            digest = sha256(call["response"].encode()).hexdigest()
            payload = {"task_id": lease.task_id, "version": lease.version, "artifact": json.loads(wire),
                       "call_id": call_id, "response_digest": digest,
                       "scope_ref": self._scope_ref(db, lease.task_id)}
            permission = self._permit(db, lease, "artifact.publish", payload)
            ref = "sha256:" + sha256(_wire(payload).encode()).hexdigest()
            db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?)",
                       (ref, lease.task_id, lease.version, lease.owner, wire, call_id, digest, _wire(permission)))
            self._abandon(db, lease.task_id)
            db.execute("UPDATE work SET status='done',owner=NULL,expires=NULL WHERE id=?", (lease.task_id,))
            self._event(db, "published", lease.task_id, {"artifact_ref": ref, "call_id": call_id,
                        "version": lease.version, "response_digest": digest, "permission": permission})
            if not db.execute("SELECT 1 FROM work WHERE status!='done'").fetchone():
                db.execute("UPDATE run SET status='completed'")
            return ref

    def _stop(self, status):
        with self._transaction() as db:
            if self._run(db)["status"] in ("cancelled", "revoked"):
                return
            db.execute("UPDATE run SET status=?,enabled=0,generation=generation+1", (status,))
            for row in db.execute("SELECT id FROM work WHERE status!='done'").fetchall():
                self._abandon(db, row["id"])
            db.execute("UPDATE work SET status=?,owner=NULL,expires=NULL WHERE status!='done'", (status,))
            self._event(db, status, "", {"generation": self._run(db)["generation"]})

    def cancel(self):
        self._stop("cancelled")


    def snapshot(self):
        with self._transaction() as db:
            calls = [dict(row) for row in db.execute("SELECT * FROM calls ORDER BY rowid")]
            return {"run": dict(self._run(db)), "work": [dict(row) for row in db.execute("SELECT * FROM work ORDER BY rowid")],
                    "calls": calls, "artifacts": [dict(row) for row in db.execute("SELECT * FROM artifacts ORDER BY rowid")],
                    "events": [json.loads(row[0]) for row in db.execute("SELECT value FROM events ORDER BY seq")],
                    "actual_tokens": sum(row["actual"] or 0 for row in calls),
                    "reserved_tokens": sum(row["reserved"] for row in calls if row["state"] == "reserved"),
                    "unknown_tokens": sum(row["reserved"] for row in calls if row["state"] == "dispatched"),
                    "unknown_calls": sum(row["state"] == "dispatched" for row in calls),
                    "call_count": len(calls)}
