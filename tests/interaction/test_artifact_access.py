"""Agent-filtered published values are separate from trusted-host raw receipts."""
from hashlib import sha256
import sqlite3

import pytest

from pheroos_interaction.records import StateError
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.session import _wire


BODY = {"value": 7, "nested": {"items": [1]}}
ARGS = {"source_id": "x"}
FINGERPRINT = sha256(_wire(BODY).encode()).hexdigest()


def make_session(tmp_path, name="one", *, works=("read",), source_readers=None,
                 readers_by_work=None, dependencies=None, generic=(), clock=None,
                 artifact_bytes=8192):
    source_readers = ["a", "b"] if source_readers is None else source_readers
    readers_by_work, dependencies = readers_by_work or {}, dependencies or {}
    work = [{"id": w, "version": 1, "agents": ["a", "b"],
             "actions": ["tool.evaluate"], "dependencies": dependencies.get(w, [])}
            for w in works]
    inspections = [{"work_id": w, "source_id": "x", "source_version": 1,
                    "tool_ref": "inspect", "tool_version": "v1", "arguments": ARGS,
                    "state_fingerprint": FINGERPRINT,
                    "readers": readers_by_work.get(w, source_readers)}
                   for w in works if w not in generic]
    return CoordinationSession.create(
        tmp_path / (name + ".sqlite"), name, agents=["a", "b"], work=work,
        sources=[{"id": "x", "version": 1, "readers": source_readers,
                  "state_fingerprint": FINGERPRINT}], inspections=inspections,
        token_cap=0, max_calls=8, clock=clock, artifact_bytes=artifact_bytes)


def receive(session, work="read", body=BODY):
    lease = session.claim("a", work)
    response = SessionDriver(session, tools={"inspect": lambda _: body}).evaluate(
        lease, work, "inspect", ARGS)
    return lease, response


def publish(session, work="read", body=BODY):
    lease, response = receive(session, work, body)
    return session.publish(lease, work, response["artifact"], verify=lambda _, value: value == body)


def test_unpublished_receipt_is_not_an_agent_artifact_and_reads_have_no_effect(tmp_path):
    now = [0.]
    session = make_session(tmp_path, clock=lambda: now[0])
    lease, response = receive(session)
    now[0] = 100.  # A read must not recover an expired work lease.
    before = session.snapshot()
    assert session.artifacts("b") == []
    assert session.read_artifact("b", "read") is None
    assert session.read_artifact("b", "sha256:missing") is None
    assert session.snapshot() == before
    assert session.call("read")["response"] == response  # Explicit host-only view.
    assert before["work"][0]["status"] == "leased"


def test_completed_artifact_metadata_is_minimal_and_value_is_a_json_copy(tmp_path):
    session = make_session(tmp_path)
    ref = publish(session)
    before = session.snapshot()
    assert before["run"]["status"] == "completed"
    metadata = session.artifacts("b")
    assert len(metadata) == 1
    assert set(metadata[0]) == {"ref", "work_id", "version", "observation_key"}
    assert metadata[0]["ref"] == ref and metadata[0]["work_id"] == "read"
    assert metadata[0]["version"] == 1
    assert len(metadata[0]["observation_key"]) == 64
    value = session.read_artifact("b", ref)
    assert value == BODY
    value["nested"]["items"].append(99)
    metadata[0]["ref"] = "changed"
    assert session.read_artifact("b", ref) == BODY
    assert session.artifacts("b")[0]["ref"] == ref
    assert session.snapshot() == before


@pytest.mark.parametrize("restricted_layer", ["source", "inspection"])
def test_both_reader_layers_filter_values_and_metadata(tmp_path, restricted_layer):
    session = make_session(
        tmp_path, source_readers=["a"] if restricted_layer == "source" else ["a", "b"],
        readers_by_work={"read": ["a"] if restricted_layer == "inspection" else ["a", "b"]})
    ref = publish(session)
    before = session.snapshot()
    assert session.artifacts("b") == []
    assert session.read_artifact("b", ref) is None
    assert session.read_artifact("b", "sha256:missing") is None
    assert session.read_artifact("a", ref) == BODY
    assert session.snapshot() == before


@pytest.mark.parametrize("restricted_layer", ["source", "inspection"])
def test_both_reader_layers_gate_execution_without_changing_claim(tmp_path, restricted_layer):
    session = make_session(
        tmp_path, source_readers=["a"] if restricted_layer == "source" else ["a", "b"],
        readers_by_work={"read": ["a"] if restricted_layer == "inspection" else ["a", "b"]})
    lease = session.claim("b", "read")
    assert lease is not None
    calls = []
    driver = SessionDriver(session, tools={"inspect": lambda _: calls.append(True) or BODY})
    with pytest.raises(PermissionError):
        driver.evaluate(lease, "denied", "inspect", ARGS)
    assert calls == [] and session.snapshot()["calls"] == []


def test_private_artifact_metadata_does_not_leak_among_visible_artifacts(tmp_path):
    session = make_session(tmp_path, works=("private", "public"),
                           readers_by_work={"private": ["a"]})
    private = publish(session, "private")
    public = publish(session, "public")
    assert [x["ref"] for x in session.artifacts("b")] == [public]
    assert session.read_artifact("b", private) is None
    assert len(session.artifacts("a")) == 2


@pytest.mark.parametrize("change", ["reader_revoked", "version", "fingerprint"])
def test_current_source_changes_remove_published_visibility(tmp_path, change):
    session = make_session(tmp_path)
    ref = publish(session)
    if change == "reader_revoked":
        session.source_update("x", 1, ["a"], FINGERPRINT)
    elif change == "version":
        session.source_update("x", 2, ["a", "b"], FINGERPRINT)
    else:
        # An inconsistent stored fingerprint must also fail closed. Legitimate
        # source updates require a version increase when content changes.
        with sqlite3.connect(session.path) as db:
            db.execute("UPDATE coordination_sources_v1 SET fingerprint='changed'")
    before = session.snapshot()
    assert session.artifacts("b") == []
    assert session.read_artifact("b", ref) is None
    assert session.snapshot() == before


@pytest.mark.parametrize("stop", ["cancelled", "revoked"])
def test_stopped_session_rejects_all_agent_artifact_reads(tmp_path, stop):
    session = make_session(tmp_path)
    ref = publish(session)
    session._stop(stop)
    before = session.snapshot()
    with pytest.raises(PermissionError):
        session.artifacts("a")
    with pytest.raises(PermissionError):
        session.read_artifact("a", ref)
    assert session.snapshot() == before


def test_undeclared_reader_rejected_even_for_missing_ref(tmp_path):
    session = make_session(tmp_path)
    before = session.snapshot()
    with pytest.raises(PermissionError):
        session.artifacts("outsider")
    with pytest.raises(PermissionError):
        session.read_artifact("outsider", "sha256:missing")
    assert session.snapshot() == before


def test_foreign_session_reference_and_unindexed_artifact_are_not_exposed(tmp_path):
    one = make_session(tmp_path, "one")
    two = make_session(tmp_path, "two", generic=("read",))
    foreign = publish(one)
    generic = publish(two)
    assert two.artifacts("a") == []
    assert two.read_artifact("a", foreign) is None
    assert two.read_artifact("a", generic) is None
    assert one.read_artifact("a", generic) is None


def test_rejected_oversized_receipt_never_enters_agent_artifact_view(tmp_path):
    session = make_session(tmp_path, artifact_bytes=128)
    lease = session.claim("a", "read")
    with pytest.raises(StateError, match="response rejected"):
        SessionDriver(session, tools={"inspect": lambda _: {"value": "x" * 256}}).evaluate(
            lease, "huge", "inspect", ARGS)
    assert session.call("huge")["state"] == "response_rejected"
    assert session.artifacts("b") == []
    assert session.read_artifact("b", "huge") is None


def test_dag_consumer_uses_supported_view_after_dependency_publication(tmp_path):
    producer = make_session(tmp_path, works=("read", "consume"),
                            dependencies={"consume": ["read"]}, generic=("consume",))
    consumer = CoordinationSession(producer.path)
    lease, response = receive(producer)
    assert consumer.claim("b", "consume") is None
    assert consumer.artifacts("b") == []
    ref = producer.publish(lease, "read", response["artifact"], verify=lambda _, value: value == BODY)
    next_lease = consumer.claim("b", "consume")
    assert next_lease is not None
    before = producer.snapshot()
    metadata = consumer.artifacts("b")
    assert [row["ref"] for row in metadata] == [ref]
    assert consumer.read_artifact("b", metadata[0]["ref"]) == BODY
    assert producer.snapshot() == before
    reply = SessionDriver(consumer, tools={
        "consume": lambda args: {"doubled": consumer.read_artifact("b", args["ref"])["value"] * 2}
    }).evaluate(next_lease, "consume", "consume", {"ref": ref})
    assert reply["artifact"] == {"doubled": 14}
