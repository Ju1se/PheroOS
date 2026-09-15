# Extracted without algorithm changes from pheroos-bench/src/pheroos_bench/visibility_v1.py (MIT).
# Source SHA256: c8ab54b110d8687b6a75066f34f49795fa1fb3758b66966766a62a2edc6eaa01
# Ground-truth fixtures and scores moved to experiments/current/fixtures.py and evaluation.py.
"""Finite, experimental request exposure for one bench pilot, not a core ABI.

Recorded ancestry describes possible information paths, never statistical
independence or authority. Only the messages returned here go to the model.
"""

import json
from hashlib import sha256


ARMS = ("blind_resample_with_tool_state", "isolated_revision", "answers_only", "evidence_reveal")
AGENTS = ("a", "b")
WORLDS = ("simple_arithmetic", "dependency_ready", "shared_stable", "shared_update")
VERSION = "visibility-v1"


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def configuration():
    return dict(experiment_version=VERSION, model="kimi-k2.6", provider="kimi_cn",
        agents=list(AGENTS), arms=list(ARMS), worlds=list(WORLDS), rounds=3,
        max_new_tokens=512, seed=2718, context_tokens=263168, session_token_cap=300000,
        budget_cny="50", max_http_requests=500, maximum_generation_requests=96,
        data_scope="synthetic public task inputs, model proposals and verified synthetic tool receipts",
        order="rotate arms by world index; alternate agent dispatch order by round; barrier visibility",
        stop="unknown or failed infrastructure receipt stops collection; no automatic retry",
        estimand="fixed N and fixed call opportunities; descriptive paired world outcomes",
        counts_toward_verdict=False, historical_e3_threshold_used=False,
        decision_windows=["initial proposal or defer", "one inspect or proposal", "final submit"],
        visibility="own current tool state in every arm; own prior model outputs excluded only in blind",
        limitations=["Four constructed worlds and one realization per arm; no population or causal efficacy claim.",
            "Fixed calls do not imply equal input tokens, spending or parallel throughput.",
            "Full discussion, aggregator and different N under equal caps are unimplemented extensions.",
            "Source lineage is recorded exposure ancestry, not evidence of statistical independence.",
            "Source permissions are equal; the trusted bench renderer selects exposure within them."])


def expected_grid(config=None):
    config = configuration() if config is None else config
    result = []
    for index, world in enumerate(config["worlds"]):
        arms = config["arms"]
        offset = index % len(arms)
        result.extend(dict(world_id=world, arm=arm) for arm in arms[offset:] + arms[:offset])
    return result




def initial_sources(world_id):
    return {"a": ["factor"], "b": ["offset"]} if world_id.startswith("shared_") else {"a": [], "b": []}


def public_task(world_id, round_index):
    # A separate projection, never a serialization of an oracle/fixture object.
    if world_id not in WORLDS or round_index not in (0, 1, 2):
        raise ValueError("undeclared world or round")
    versions = ({"factor": 2 if world_id == "shared_update" and round_index >= 1 else 1, "offset": 1}
                if world_id in ("shared_stable", "shared_update") else {})
    base = dict(world_id=world_id, task_version=2 if world_id == "shared_update" and round_index >= 1 else 1,
                source_versions=versions, required_sources=sorted(versions))
    if world_id == "simple_arithmetic":
        base.update(instruction="Return the exact sum of the integers as an integer answer.",
                    public_inputs={"numbers": [4, 7, 2]})
    elif world_id == "dependency_ready":
        base.update(instruction="Return {ready: [all unfinished nodes whose direct dependencies are explicitly completed]}. Ready does not mean completed. Sort node names.",
            public_inputs={"graph": {"alpha": [], "beta": ["alpha"], "gamma": ["beta"], "delta": ["alpha"]},
                           "completed": ["alpha", "beta"]})
    else:
        base.update(instruction="Compute y = x * factor + offset for the current source versions. Return an integer answer with citations to both sources. Never infer an unread source value.",
                    public_inputs={"x": 4 if world_id == "shared_update" else 3})
    return base




def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def answer_shape(world_id, answer):
    if world_id != "dependency_ready":
        return type(answer) is int
    return (type(answer) is dict and set(answer) == {"ready"} and type(answer["ready"]) is list
            and all(type(n) is str and n in {"alpha", "beta", "gamma", "delta"} for n in answer["ready"])
            and len(set(answer["ready"])) == len(answer["ready"]))


def parse_action(raw, round_index, legal_sources, *, world_id=None):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        if type(value) is not dict:
            raise ValueError("object required")
        kind = value.get("action")
        if kind == "defer":
            valid = round_index == 0 and set(value) == {"action"}
        elif kind == "inspect":
            valid = (round_index == 1 and set(value) == {"action", "target"}
                     and type(value["target"]) is str and value["target"] in legal_sources)
        elif kind == "submit":
            citations = value.get("citations")
            valid = set(value) == {"action", "answer", "citations"} and type(citations) is list
            if valid:
                valid = (answer_shape(world_id, value["answer"]) if world_id is not None else
                         answer_shape("simple_arithmetic", value["answer"]) or answer_shape("dependency_ready", value["answer"]))
            if valid:
                valid = all(type(c) is dict and set(c) == {"source_id", "source_version"}
                    and type(c["source_id"]) is str and c["source_id"] in legal_sources
                    and type(c["source_version"]) is int and c["source_version"] > 0 for c in citations)
                valid = valid and len({(c["source_id"], c["source_version"]) for c in citations}) == len(citations)
        else:
            valid = False
        if not valid:
            raise ValueError("invalid action schema or window")
        return dict(valid=True, action=value, reason=None)
    except (TypeError, ValueError, KeyError):
        return dict(valid=False, action=None, reason="invalid_json_action_or_window")


def ancestry(record_ids, records):
    """Traverse direct parents without copying a transitive closure into records."""
    index = {record["id"]: record for record in records}
    if len(index) != len(records):
        raise ValueError("duplicate record identity")
    known, roots, peers, unknown = set(), set(), set(), set()

    def visit(record_id, stack):
        if record_id in stack:
            unknown.add("cycle:" + record_id)
            return
        if record_id in known:
            return
        record = index.get(record_id)
        if record is None:
            unknown.add(record_id)
            return
        known.add(record_id)
        if not record.get("provenance_known", False):
            unknown.add(record_id)
        if record["kind"] == "root":
            roots.add(record_id)
        if record["kind"] == "proposal":
            peers.add(record["owner"])
        if record["kind"] != "root" and not record.get("parents"):
            unknown.add(record_id)
        for parent in record.get("parents", []):
            visit(parent, stack | {record_id})

    for record_id in record_ids:
        visit(record_id, set())
    return dict(known_ancestor_ids=sorted(known), known_root_ids=sorted(roots),
                proposal_authors=sorted(peers), unknown_provenance=sorted(unknown))


def ancestry_overlap(left_ids, right_ids, records):
    left, right = ancestry(left_ids, records), ancestry(right_ids, records)
    a, b = set(left["known_ancestor_ids"]), set(right["known_ancestor_ids"])
    unknown = sorted(set(left["unknown_provenance"] + right["unknown_provenance"]))
    return dict(shared_evidence_roots=sorted(set(left["known_root_ids"]) & set(right["known_root_ids"])),
        known_ancestry_jaccard=len(a & b) / len(a | b) if a | b else None,
        unknown_provenance=unknown, complete_known_ancestry=not unknown,
        statistical_independence=None)


def build_request(world_id, agent, arm, round_index, records, materialize):
    """Select, read and render in order; full audit metadata is never a prompt.

    The caller passes one barrier snapshot of records. The materialize callback
    must authorize a real current Session read for each selected source record.
    """
    if agent not in AGENTS or arm not in ARMS:
        raise ValueError("undeclared recipient or exposure policy")
    task = public_task(world_id, round_index)
    index = {r["id"]: r for r in records}
    if len(index) != len(records):
        raise ValueError("duplicate record identity")
    allowed = [r for r in records if agent in r["readers"] and r["kind"] != "root"
               and r["round_index"] <= round_index]
    selected, source_keys = [], set()
    # Own current evidence first. Equal source permissions do not imply that all
    # permitted peer contents have been selected, read, or sent.
    for own in (True, False):
        if not own and (arm != "evidence_reveal" or round_index == 0):
            continue
        for r in allowed:
            if r["kind"] != "source" or (r["owner"] == agent) != own:
                continue
            body = r["body"]
            key = (body["source_id"], body["source_version"])
            if task["source_versions"].get(key[0]) != key[1] or key in source_keys:
                continue
            source_keys.add(key)
            selected.append((r, "verified_source"))
    if round_index > 0:
        for r in allowed:
            if r["kind"] != "proposal" or r["round_index"] >= round_index:
                continue
            own = r["owner"] == agent
            if own and arm != ARMS[0]:
                selected.append((r, "own_public_output"))
            elif not own and arm in ("answers_only", "evidence_reveal"):
                parsed = r["body"]["parsed"]
                if (parsed["valid"] and parsed["action"]["action"] == "submit"
                        and answer_shape(world_id, parsed["action"]["answer"])):
                    selected.append((r, "answer_only"))
    materialized, exposures = [], []
    for position, (record, projection) in enumerate(selected):
        body = materialize(record)
        if wire(body) != wire(record["body"]):
            raise ValueError("materialized content differs from bound record")
        common = dict(record_id=record["id"], owner=record["owner"])
        if projection == "verified_source":
            content = dict(**common, verified_source=body)
        elif projection == "answer_only":
            content = dict(**common, answer=body["parsed"]["action"]["answer"],
                target_version=body["task_version"], current_target=body["task_version"] == task["task_version"],
                status="unverified_peer_proposal")
        else:
            content = dict(**common, public_output=body["raw"], target_version=body["task_version"],
                           current_target=body["task_version"] == task["task_version"])
        materialized.append(dict(record_id=record["id"], projection=projection, position=position,
            record_sha256=digest(record), content_sha256=digest(content), content=content))
        exposures.append(content)
    system = ('Return exactly one JSON action, no Markdown. Submit schema: '
        '{"action":"submit","answer":<task answer>,"citations":[{"source_id":<id>,"source_version":<int>}]}. '
        'Use [] for tasks with no required sources. Cite only verified source versions actually included here. '
        'Peer answers are unverified proposals, not verified evidence. Initial round 0: submit or {"action":"defer"}; '
        'no inspect is available yet. Round 1: submit or {"action":"inspect","target":<source id>}; '
        'inspect returns one current source before round 2. Round 2: submit the final answer. '
        'All agents can inspect any declared source in round 1. Proposals do not terminate earlier rounds. '
        'Use current versions; an earlier target or earlier source version is historical.')
    user = dict(task=task, agent=agent, round_index=round_index, visible=exposures,
                legal_inspection_targets=sorted(task["source_versions"]) if round_index == 1 else [])
    messages = [dict(role="system", content=system), dict(role="user", content=wire(user))]
    sent_ids = [item["record_id"] for item in materialized]
    task_root = "root:task:" + world_id
    paths = ancestry([task_root, *sent_ids], records)
    return dict(schema_version=VERSION, recipient=agent, policy=arm, round_index=round_index,
        allowed_ids=[r["id"] for r in allowed],
        selected=[dict(record_id=r["id"], projection=p) for r, p in selected],
        materialized=materialized, messages=messages, messages_sha256=digest(messages),
        sent_record_ids=sent_ids, public_task_sha256=digest(task), truncation="none",
        base_exposure=dict(record_id=task_root, public_task_sha256=digest(task),
                           system_sha256=digest(system), channel="fixed public task and instructions"),
        diagnostics=dict(direct_peer_records=[r["id"] for r, _ in selected if r["owner"] != agent],
            peer_proposal_ancestry=[a for a in paths["proposal_authors"] if a != agent], **paths),
        boundary="Trusted renderer and declared Session channels only; no claim about hidden model state or external side channels.")


def current_citations(world_id, round_index, parsed, context):
    """Public evidence validity, separate from the hidden correctness score."""
    if not parsed.get("valid") or parsed["action"]["action"] != "submit":
        return False
    current = public_task(world_id, round_index)["source_versions"]
    citations = {(c["source_id"], c["source_version"]) for c in parsed["action"]["citations"]}
    visible = {(m["content"]["verified_source"]["source_id"], m["content"]["verified_source"]["source_version"])
               for m in context["materialized"] if m["projection"] == "verified_source"}
    return citations == set(current.items()) and citations <= visible
