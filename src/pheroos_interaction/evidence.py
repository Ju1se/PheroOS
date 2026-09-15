"""Version-aware source access extracted from runtime/coordination_v1.py (MIT).

One Session owns calls/artifacts/budgets. Retains current reader checks, real
historical reads, declared pure-inspection keys, ownership/release and optional
reuse. Manifest/feedback interfaces and core authorization are not shipped.
"""

from dataclasses import asdict
from hashlib import sha256
import json

from .session import Session, _duration, _id, _integer, _wire
from .records import BudgetExceeded, Lease, LeaseLost, StateError


class CoordinationSession(Session):
    """Scoped local evidence; no claim of legacy protocol compatibility."""

    @classmethod
    def create(
        cls,
        path,
        run_id,
        *,
        sources,
        inspections,
        max_index_entries=256,
        max_control_operations=4096,
        **session_options,
    ):
        limits = dict(
            max_index_entries=max_index_entries,
            max_control_operations=max_control_operations,
        )
        for name, value in limits.items():
            _integer(value, name, 1)
        session = super().create(path, run_id, **session_options)
        with session._transaction() as db:
            for sql in (
                "CREATE TABLE coordination_v1 (id INTEGER PRIMARY KEY CHECK(id=1), limits TEXT)",
                "CREATE TABLE coordination_sources_v1 (id TEXT PRIMARY KEY, version INTEGER, readers TEXT, fingerprint TEXT)",
                "CREATE TABLE coordination_inspections_v1 (work_id TEXT PRIMARY KEY REFERENCES work(id), key TEXT, source_id TEXT REFERENCES coordination_sources_v1(id), source_version INTEGER, tool_ref TEXT, tool_version TEXT, arguments TEXT, fingerprint TEXT, readers TEXT)",
                "CREATE INDEX coordination_key_v1 ON coordination_inspections_v1(key)",
                "CREATE TABLE coordination_operations_v1 (seq INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT, agent TEXT, request_bytes INTEGER, materialized_bytes INTEGER, serialized_bytes INTEGER, outcome TEXT)",
            ):
                db.execute(sql)
            db.execute("INSERT INTO coordination_v1 VALUES (1,?)", (_wire(limits),))
            if len(sources) > max_index_entries or len(inspections) > max_index_entries:
                raise ValueError("finite source/index capacity exceeded")
            for source in sources:
                session._source_declaration(db, source)
                db.execute(
                    "INSERT INTO coordination_sources_v1 VALUES (?,?,?,?)",
                    (
                        source["id"],
                        source["version"],
                        _wire(source["readers"]),
                        source["state_fingerprint"],
                    ),
                )
            for item in inspections:
                session._inspection_declaration(db, item)
            session._coord_event(
                db,
                "configured",
                {"limits": limits, "source_count": len(sources), "index_count": len(inspections)},
            )
        return session

    def _limits(self, db):
        return json.loads(db.execute("SELECT limits FROM coordination_v1").fetchone()[0])

    def _coord_event(self, db, kind, payload):
        event = dict(event_type="interaction.evidence." + kind, details=payload)
        db.execute("INSERT INTO events(value) VALUES (?)", (_wire(event),))

    def _source_declaration(self, db, source):
        if set(source) != {"id", "version", "readers", "state_fingerprint"}:
            raise ValueError("explicit source identity/version/readers/fingerprint required")
        _id(source["id"])
        _id(source["state_fingerprint"])
        _integer(source["version"], "source version", 1)
        readers = source["readers"]
        if (
            type(readers) is not list
            or len(set(readers)) != len(readers)
            or not set(readers) <= set(json.loads(self._run(db)["agents"]))
        ):
            raise ValueError("source access must name distinct declared agents")

    def _inspection_declaration(self, db, item):
        required = {
            "work_id",
            "source_id",
            "source_version",
            "tool_ref",
            "tool_version",
            "arguments",
            "state_fingerprint",
        }
        if set(item) - {"readers"} != required or type(item["arguments"]) is not dict:
            raise ValueError("explicit pure-inspection equivalence declaration required")
        for field in ("work_id", "source_id", "tool_ref", "tool_version", "state_fingerprint"):
            _id(item[field])
        _integer(item["source_version"], "source version", 1)
        work = db.execute("SELECT * FROM work WHERE id=?", (item["work_id"],)).fetchone()
        source = db.execute(
            "SELECT * FROM coordination_sources_v1 WHERE id=?", (item["source_id"],)
        ).fetchone()
        if (
            work is None
            or source is None
            or "tool.evaluate" not in json.loads(work["declaration"])["actions"]
        ):
            raise ValueError("inspection requires declared work, tool action and source")
        if (
            len(_wire(item["arguments"]).encode())
            > json.loads(self._run(db)["limits"])["context_bytes"]
        ):
            raise ValueError("inspection arguments exceed request bound")
        readers = item.get("readers", json.loads(source["readers"]))
        if (
            type(readers) is not list
            or len(set(readers)) != len(readers)
            or not set(readers) <= set(json.loads(self._run(db)["agents"]))
        ):
            raise ValueError("inspection readers must be distinct declared agents")
        key = sha256(
            _wire(
                {
                    "scope": self._run(db)["run_id"],
                    "work_version": work["version"],
                    **{name: item[name] for name in required - {"work_id"}},
                }
            ).encode()
        ).hexdigest()
        db.execute(
            "INSERT INTO coordination_inspections_v1 VALUES (?,?,?,?,?,?,?,?,?)",
            (
                item["work_id"],
                key,
                item["source_id"],
                item["source_version"],
                item["tool_ref"],
                item["tool_version"],
                _wire(item["arguments"]),
                item["state_fingerprint"],
                _wire(readers),
            ),
        )

    def _inspection(self, db, work_id):
        return db.execute(
            "SELECT * FROM coordination_inspections_v1 WHERE work_id=?", (work_id,)
        ).fetchone()

    def _access(self, db, agent, source_id):
        run = self._run(db)
        if not run["enabled"] or run["status"] not in ("running", "completed"):
            raise PermissionError("session cancelled or revoked")
        source = db.execute(
            "SELECT * FROM coordination_sources_v1 WHERE id=?", (source_id,)
        ).fetchone()
        if source is None or agent not in json.loads(source["readers"]):
            raise PermissionError("source is inaccessible in this scope")
        return source

    def _current(self, db, item, agent):
        source = self._access(db, agent, item["source_id"])
        return (item["source_version"], item["fingerprint"]) == (
            source["version"],
            source["fingerprint"],
        )

    def _lease(self, db, lease):
        work = super()._lease(db, lease)
        # During inherited create() no lease is evaluated before schema creation.
        item = self._inspection(db, lease.task_id)
        if item is not None and not self._current(db, item, lease.owner):
            raise LeaseLost("inspection source/version/state superseded")
        return work

    def source_update(self, source_id, version, readers, state_fingerprint):
        """Trusted host control; never routed through attention or model output."""
        source = dict(
            id=source_id, version=version, readers=readers, state_fingerprint=state_fingerprint
        )
        with self._transaction() as db:
            self._source_declaration(db, source)
            old = db.execute(
                "SELECT * FROM coordination_sources_v1 WHERE id=?", (source_id,)
            ).fetchone()
            if old is None or version < old["version"]:
                raise StateError("missing source or reordered older source update")
            if version == old["version"] and state_fingerprint != old["fingerprint"]:
                raise StateError("source content change requires a newer version")
            db.execute(
                "UPDATE coordination_sources_v1 SET version=?,readers=?,fingerprint=? WHERE id=?",
                (version, _wire(readers), state_fingerprint, source_id),
            )
            for item in db.execute(
                "SELECT i.*,w.status,w.owner FROM coordination_inspections_v1 i JOIN work w ON w.id=i.work_id WHERE i.source_id=?",
                (source_id,),
            ).fetchall():
                stale = item["source_version"] < version or (
                    item["source_version"] == version and item["fingerprint"] != state_fingerprint
                )
                revoked = item["owner"] is not None and item["owner"] not in readers
                if item["status"] not in ("done", "cancelled", "revoked", "superseded") and (
                    stale or revoked
                ):
                    self._abandon(db, item["work_id"])
                    unknown = db.execute(
                        "SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'",
                        (item["work_id"],),
                    ).fetchone()
                    status = "superseded" if stale else ("uncertain" if unknown else "ready")
                    db.execute(
                        "UPDATE work SET status=?,owner=NULL,expires=NULL,epoch=epoch+1 WHERE id=?",
                        (status, item["work_id"]),
                    )
            self._coord_event(db, "source_updated", source)

    def dispatch(self, lease, call_id):
        # An inspection's equivalent key is a trusted declaration, so the actual
        # tool/arguments must match it at the same cancellation-serialized boundary.
        with self._transaction() as db:
            self._lease(db, lease)
            call = db.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
            if call is None or (call["work_id"], call["version"], call["epoch"], call["state"]) != (
                lease.task_id,
                lease.version,
                lease.epoch,
                "reserved",
            ):
                raise StateError("dispatch requires this lease's reserved call")
            payload = json.loads(call["request"])
            item = self._inspection(db, lease.task_id)
            if (
                item is not None
                and call["action"] == "tool.evaluate"
                and (
                    payload.get("tool_ref") != item["tool_ref"]
                    or _wire(payload.get("arguments")) != item["arguments"]
                )
            ):
                raise StateError("inspection tool/arguments differ from the declared reuse key")
            permission = self._permit(db, lease, call["action"], payload)
            db.execute(
                "UPDATE calls SET state='dispatched',permission=? WHERE id=?",
                (_wire(permission), call_id),
            )
            self._event(
                db, "dispatched", lease.task_id, {"call_id": call_id, "permission": permission}
            )
            return payload

    def _operation(self, operation, agent, request, body):
        """Commit denied operations as well as successful ones; bounded by cap."""
        failure = None
        result = None
        with self._transaction() as db:
            limits = self._limits(db)
            count = db.execute("SELECT COUNT(*) FROM coordination_operations_v1").fetchone()[0]
            if count >= limits["max_control_operations"]:
                raise BudgetExceeded("coordination control-operation cap reached")
            request_bytes = len(_wire(request).encode())
            db.execute("SAVEPOINT coordination_body")
            try:
                if request_bytes > json.loads(self._run(db)["limits"])["context_bytes"]:
                    raise ValueError("control request exceeds declared context bound")
                result = body(db)
                encoded = _wire(result)
                outcome = "ok"
            except (ValueError, StateError, LeaseLost, PermissionError, BudgetExceeded) as exc:
                db.execute("ROLLBACK TO coordination_body")
                failure = exc
                result = {"error": type(exc).__name__, "message": str(exc)}
                encoded = _wire(result)
                outcome = "denied"
            db.execute("RELEASE coordination_body")
            size = len(encoded.encode())
            db.execute(
                "INSERT INTO coordination_operations_v1(operation,agent,request_bytes,materialized_bytes,serialized_bytes,outcome) VALUES (?,?,?,?,?,?)",
                (operation, agent, request_bytes, size, size, outcome),
            )
            self._coord_event(
                db,
                "operation",
                {
                    "operation": operation,
                    "agent": agent,
                    "request_bytes": request_bytes,
                    "materialized_bytes": size,
                    "serialized_bytes": size,
                    "request_digest": sha256(_wire(request).encode()).hexdigest(),
                    "result_digest": sha256(encoded.encode()).hexdigest(),
                    "outcome": outcome,
                },
            )
        if failure is not None:
            raise failure
        return result

    def _checked_access(self, db, lease, operation, request):
        work = self._lease(db, lease)
        if "tool.evaluate" not in json.loads(work["declaration"])["actions"]:
            raise PermissionError("evidence access requires declared tool.evaluate")
        payload = {
            "task_id": lease.task_id,
            "version": lease.version,
            "tool_ref": f"coordination.{operation}.v1",
            "arguments": request,
        }
        permission = self._permit(db, lease, "tool.evaluate", payload)
        self._coord_event(
            db,
            "access_permitted",
            {
                "operation": operation,
                "work_id": lease.task_id,
                "version": lease.version,
                "permission": permission,
            },
        )
        return permission

    def _metadata(self, db, row):
        source = db.execute(
            "SELECT * FROM coordination_sources_v1 WHERE id=?", (row["source_id"],)
        ).fetchone()
        current = (row["source_version"], row["fingerprint"]) == (
            source["version"],
            source["fingerprint"],
        )
        return {
            "artifact_ref": row["ref"],
            "source_id": row["source_id"],
            "source_version": row["source_version"],
            "tool_ref": row["tool_ref"],
            "tool_version": row["tool_version"],
            "state_fingerprint": row["fingerprint"],
            "current": current,
            "superseded": not current,
            "call_id": row["call_id"],
            "response_digest": row["response_digest"],
            "publisher": row["publisher"],
            "origin_work_id": row["work_id"],
            "scope_ref": json.loads(row["permission"])["scope_ref"],
            "semantic_truth": "not_established_by_provenance",
        }


    def read(self, lease, artifact_ref, *, allow_superseded=False):
        request = dict(artifact_ref=artifact_ref, allow_superseded=allow_superseded)

        def body(db):
            self._checked_access(db, lease, "read", request)
            if type(allow_superseded) is not bool:
                raise ValueError("exact allow_superseded boolean required")
            row = db.execute(
                "SELECT i.*,a.ref,a.call_id,a.response_digest,a.publisher,a.permission,a.value FROM coordination_inspections_v1 i JOIN artifacts a ON a.work_id=i.work_id WHERE a.ref=?",
                (artifact_ref,),
            ).fetchone()
            if row is None:
                raise PermissionError("artifact is not indexed in this scope")
            self._access(db, lease.owner, row["source_id"])
            if lease.owner not in json.loads(row["readers"]):
                raise PermissionError("artifact is private to other readers")
            metadata = self._metadata(db, row)
            if not metadata["current"] and not allow_superseded:
                raise StateError("superseded artifact requires explicit historical read")
            return {"metadata": metadata, "value": json.loads(row["value"])}

        return self._operation("read", lease.owner, request, body)



    def claim_inspection(self, agent, work_id, *, reuse=True, lease_seconds=60):
        request = dict(work_id=work_id, reuse=reuse, lease_seconds=lease_seconds)

        def body(db):
            _duration(lease_seconds)
            if type(reuse) is not bool:
                raise ValueError("exact reuse boolean required")
            item = self._inspection(db, work_id)
            if item is None:
                raise StateError("undeclared pure inspection")
            current = self._current(db, item, agent)
            if not current:
                return {"status": "stale", "lease": None, "artifact_ref": None}
            self._recover(db)
            candidates = (
                db.execute(
                    "SELECT w.*,i.key,i.readers FROM work w JOIN coordination_inspections_v1 i ON i.work_id=w.id WHERE i.key=? ORDER BY w.rowid",
                    (item["key"],),
                ).fetchall()
                if reuse
                else [db.execute("SELECT * FROM work WHERE id=?", (work_id,)).fetchone()]
            )
            if reuse:
                candidates = [row for row in candidates if agent in json.loads(row["readers"])]
                for row in candidates:
                    artifact = db.execute(
                        "SELECT ref FROM artifacts WHERE work_id=?", (row["id"],)
                    ).fetchone()
                    if artifact is not None:
                        return {"status": "reuse", "lease": None, "artifact_ref": artifact["ref"]}
                for row in candidates:
                    if (
                        row["status"] == "uncertain"
                        or db.execute(
                            "SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'",
                            (row["id"],),
                        ).fetchone()
                    ):
                        return {"status": "unknown", "lease": None, "artifact_ref": None}
                    if row["status"] == "leased":
                        return {"status": "busy", "lease": None, "artifact_ref": None}
            for row in candidates:
                declaration = json.loads(row["declaration"])
                if row["status"] != "ready" or agent not in declaration["agents"]:
                    continue
                if any(
                    db.execute("SELECT 1 FROM artifacts WHERE work_id=?", (dep,)).fetchone() is None
                    for dep in declaration["dependencies"]
                ):
                    continue
                lease = Lease(row["id"], row["version"], agent, row["epoch"] + 1, self._run(db)["run_id"])
                db.execute(
                    "UPDATE work SET status='leased',owner=?,epoch=?,expires=?,generation=? WHERE id=?",
                    (
                        agent,
                        lease.epoch,
                        self.clock() + lease_seconds,
                        self._run(db)["generation"],
                        row["id"],
                    ),
                )
                self._event(db, "claimed", row["id"], asdict(lease))
                settled = db.execute(
                    "SELECT id FROM calls WHERE work_id=? AND action='tool.evaluate' AND state='received' ORDER BY rowid",
                    (row["id"],),
                ).fetchone()
                if settled is not None:
                    return {
                        "status": "settled",
                        "lease": asdict(lease),
                        "artifact_ref": None,
                        "receipt_call_id": settled["id"],
                    }
                return {"status": "claimed", "lease": asdict(lease), "artifact_ref": None}
            status = (
                "unknown"
                if any(row["status"] == "uncertain" for row in candidates)
                else "unavailable"
            )
            return {"status": status, "lease": None, "artifact_ref": None}

        result = self._operation("claim_inspection", agent, request, body)
        if result["lease"] is not None:
            result["lease"] = Lease(**result["lease"])
        return result

    def release_inspection(self, lease):
        """Release unused/settled work; unresolved dispatch remains owned/unknown."""

        def body(db):
            self._lease(db, lease)
            if self._inspection(db, lease.task_id) is None:
                raise StateError("release requires declared pure inspection")
            if db.execute(
                "SELECT 1 FROM calls WHERE work_id=? AND state='dispatched'", (lease.task_id,)
            ).fetchone():
                raise StateError("cannot release unresolved dispatch for re-execution")
            self._abandon(db, lease.task_id)
            db.execute(
                "UPDATE work SET status='ready',owner=NULL,expires=NULL,epoch=epoch+1 WHERE id=?",
                (lease.task_id,),
            )
            self._coord_event(db, "released", {"lease": asdict(lease)})
            return {"status": "released"}

        return self._operation("release_inspection", lease.owner, asdict(lease), body)

    def coordination_snapshot(self):
        """Trusted observer accounting; never supplied as an agent transcript."""
        with self._transaction() as db:
            operations = [
                dict(row)
                for row in db.execute("SELECT * FROM coordination_operations_v1 ORDER BY seq")
            ]
            return {
                "schema": "interaction.evidence.v1",
                "limits": self._limits(db),
                "operations": operations,
                "control_operations": len(operations),
                "request_bytes": sum(row["request_bytes"] for row in operations),
                "materialized_bytes": sum(row["materialized_bytes"] for row in operations),
                "serialized_bytes": sum(row["serialized_bytes"] for row in operations),
                "denied_operations": sum(row["outcome"] == "denied" for row in operations),
            }
