"""Current source/version/readers and tool declarations at durable dispatch.

Session owns calls, receipts, cancellation and caps. These source checks also
fence publication when a declaration is superseded or access is revoked.
"""

from hashlib import sha256
import json

from .session import Session, _id, _integer, _wire
from pheroos_interaction.records import LeaseLost, StateError


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
            raise ValueError("explicit inspection declaration required")
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
        # Tool and arguments must match the declaration at the same durable
        # boundary that checks cancellation and current source access.
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
                raise StateError("inspection tool/arguments differ from the declaration")
            permission = self._permit(db, lease, call["action"], payload)
            db.execute(
                "UPDATE calls SET state='dispatched',permission=? WHERE id=?",
                (_wire(permission), call_id),
            )
            self._event(
                db, "dispatched", lease.task_id, {"call_id": call_id, "permission": permission}
            )
            return payload
