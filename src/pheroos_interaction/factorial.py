# Extracted without algorithm changes from /Users/scottxie/Desktop/pheroos-kimi-research/pheroos-bench/src/pheroos_bench/visibility_factorial_v2.py (MIT).
# Source SHA256: 44a3de11d0aa0047ef6c52326fd150554e87bd0a3ac85bdf68cdf3b0ff507e88
# Ground-truth fixtures and scores moved to fixtures.py and evaluation.py.
"""Finite 2x2 evidence-expression/action-cue pilot. No protocol authority changes."""

from .visibility import ancestry, digest, parse_action as _parse_action, wire


AGENTS = ("a", "b")
ROUNDS = (1, 2)
STATES = ("complete", "missing", "stale")
CONDITIONS = ("owner_script", "owner_current", "eligibility_script", "eligibility_current")
WORLDS = tuple(f"{case}/{state}" for case in ("fresh_a", "fresh_b") for state in STATES)
EFFICIENCY_GOAL = "Preserve answer correctness and required current citations while avoiding unnecessary source inspections."
VERSION = "visibility-factorial-v2"


def _case(world_id):
    if world_id not in WORLDS:
        raise ValueError("undeclared world")
    return world_id.split("/")


def configuration():
    return dict(experiment_version=VERSION, model="kimi-k2.6", provider="kimi_cn", thinking="disabled",
        agents=list(AGENTS), rounds=list(ROUNDS), worlds=list(WORLDS), conditions=list(CONDITIONS),
        maximum_generation_requests=96, max_new_tokens=512, seed=31415, session_token_cap=300000,
        context_tokens=263168, budget_cny="50", max_http_requests=500,
        shared_efficiency_goal=EFFICIENCY_GOAL,
        factors={"evidence_expression": ["owner", "eligibility"], "action_cue": ["script", "current"]},
        scope="synthetic public task inputs, genuine synthetic source receipts and own model proposals",
        decision_windows=["r1 one inspect or submit", "r2 final submit"],
        preparation="same true publishers/versions within each world; stale has historical v1 plus own current v2",
        source_cache="disabled for model-requested checks; count intention and execution separately",
        ordering="rotate conditions by world index; r1 agent b then a, r2 a then b; barrier before each round",
        primary_metrics=["complete_state_redundant_inspect", "missing_or_stale_correct_target_inspect",
                         "grounded_correct_submit", "first_grounded_correct_round"],
        counts_toward_verdict=False, historical_e3_threshold_used=False,
        limitations=["Two new numerical instances; three states are repeated manipulations, not six independent tasks.",
            "No r0 model history and a common efficiency goal; comparison with historical v1 is not a single-factor effect.",
            "Two fixed model opportunities; early submission cannot save a generation in this design.",
            "No inference of psychological trust, statistical independence or general swarm superiority.",
            "Known currentness and eligibility are supplied by host/Session, not guessed from an answer."])


def expected_grid(config=None):
    config = configuration() if config is None else config
    result = []
    for index, world_id in enumerate(config["worlds"]):
        conditions = config["conditions"]
        offset = index % len(conditions)
        result.extend(dict(world_id=world_id, condition=c)
                      for c in conditions[offset:] + conditions[:offset])
    return result


def publishers(world_id):
    case, _ = _case(world_id)
    return {"multiplier": "a", "bias": "b"} if case == "fresh_a" else {"multiplier": "b", "bias": "a"}


def initial_sources(world_id):
    owners = publishers(world_id)
    return {agent: [source for source, owner in owners.items() if owner == agent] for agent in AGENTS}




def public_task(world_id):
    case, _ = _case(world_id)
    # State and fixture answer labels are not sent; current source metadata is.
    return dict(task_id=case, task_version=2, instruction="Compute y = x * multiplier + bias. Return an integer answer with citations to both current sources. Do not invent unread values.",
                public_inputs={"x": 5 if case == "fresh_a" else 7},
                source_versions={"multiplier": 2, "bias": 2}, required_sources=["bias", "multiplier"])


def parse_action(raw, round_index, legal_sources, *, world_id=None):
    if round_index not in ROUNDS:
        raise ValueError("undeclared model window")
    if world_id is not None:
        _case(world_id)
    # Existing exact JSON, action-window and integer/citation checks.
    return _parse_action(raw, round_index, legal_sources, world_id="integer_answer")




def _select(world_id, agent, round_index, records):
    _, state = _case(world_id)
    allowed = [r for r in records if agent in r["readers"] and r["kind"] != "root"
               and r["round_index"] < round_index]
    chosen, keys = [], set()
    # Own current state wins after a real inspection. Peer results newly acquired
    # at r1 never rescue another agent at r2; only fixed preparation is shareable.
    for r in allowed:
        if r["kind"] == "source" and r["owner"] == agent and r["body"]["source_version"] == 2:
            key = r["body"]["source_id"]
            if key not in keys:
                chosen.append(r)
                keys.add(key)
    for r in allowed:
        if r["kind"] != "source" or r["owner"] == agent or r["round_index"] >= 1:
            continue
        body = r["body"]
        target_version = 2 if state == "complete" else 1 if state == "stale" else None
        if body["source_version"] == target_version and body["source_id"] not in keys:
            chosen.append(r)
            keys.add(body["source_id"])
    chosen += [r for r in allowed if r["kind"] == "proposal" and r["owner"] == agent]
    return allowed, chosen


def build_request(world_id, agent, condition, round_index, records, materialize):
    if condition not in CONDITIONS or agent not in AGENTS or round_index not in ROUNDS:
        raise ValueError("undeclared receiver, condition or window")
    task = public_task(world_id)
    expression, cue = condition.split("_")
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("duplicate record identity")
    allowed, chosen = _select(world_id, agent, round_index, records)
    materialized, selected, visible, current_sources, historical_sources = [], [], [], [], []
    for position, record in enumerate(chosen):
        actual = materialize(record)
        if record["kind"] == "source":
            body, metadata = actual["value"], actual["metadata"]
            current = body["source_version"] == task["source_versions"][body["source_id"]]
            if (wire(body) != wire(record["body"]) or metadata["current"] is not current
                    or metadata["superseded"] is not (not current) or metadata["publisher"] != record["owner"]
                    or any(key in metadata and metadata[key] != body[key]
                           for key in ("source_id", "source_version"))):
                raise ValueError("source content, publisher or currentness differs from Session read")
            projection = "owner_source" if expression == "owner" else "eligibility_source"
            if expression == "owner":
                content = dict(record_id=record["id"], owner=record["owner"],
                               verified_source=body, current=current)
            else:
                content = dict(record_id=record["id"], publisher=record["owner"], recipient=agent,
                               source_receipt=body, current=current, eligible_for_current_citation=current)
            (current_sources if current else historical_sources).append(body["source_id"])
        else:
            if wire(actual) != wire(record["body"]):
                raise ValueError("proposal differs from stored public output")
            projection = "own_public_output"
            content = dict(record_id=record["id"], owner=record["owner"],
                           public_output=actual["raw"], target_version=actual["task_version"])
        selected.append(dict(record_id=record["id"], projection=projection))
        materialized.append(dict(record_id=record["id"], projection=projection, position=position,
            record_sha256=digest(record), content_sha256=digest(content), content=content))
        visible.append(content)
    common = ('Return exactly one JSON action, no Markdown. Submit schema: '
        '{"action":"submit","answer":<integer>,"citations":[{"source_id":<id>,"source_version":<int>}]}. '
        'Cite only currently valid source versions actually included here. A historical receipt is not current evidence. '
        'This rollout begins at round 1 without any round 0 model output. '
        + EFFICIENCY_GOAL + ' ')
    if cue == "script":
        instruction = ('Initial round 0: submit or {"action":"defer"}; no inspect is available yet. '
            'Round 1: submit or {"action":"inspect","target":<source id>}; inspect returns one current source before round 2. '
            'Round 2: submit the final answer. All agents can inspect any declared source in round 1. '
            'Proposals do not terminate earlier rounds.')
    else:
        instruction = ('Current legal actions: submit, or {"action":"inspect","target":<source id>}. '
            'At most one source inspection is available in this decision. All agents can inspect any declared source.') if round_index == 1 else 'Current legal action: submit the final answer. No inspection is available in this decision.'
    messages = [dict(role="system", content=common + instruction),
                dict(role="user", content=wire(dict(task=task, agent=agent, round_index=round_index,
                    visible=visible, legal_inspection_targets=sorted(task["source_versions"]) if round_index == 1 else [])))]
    root_id = "root:task:" + world_id
    sent_ids = [r["id"] for r in chosen]
    return dict(schema_version=VERSION, recipient=agent, policy=condition, round_index=round_index,
        allowed_ids=[r["id"] for r in allowed], selected=selected, materialized=materialized,
        messages=messages, messages_sha256=digest(messages), sent_record_ids=sent_ids,
        public_task_sha256=digest(task), truncation="none",
        base_exposure=dict(record_id=root_id, public_task_sha256=digest(task), system_sha256=digest(messages[0]["content"])),
        diagnostics=ancestry([root_id, *sent_ids], records),
        state_diagnostics=dict(current_sources=sorted(current_sources), historical_sources=sorted(historical_sources),
            missing_current_sources=sorted(set(task["required_sources"]) - set(current_sources))),
        boundary="State diagnostics, permissions list and ancestry are audit metadata; only messages are sent.")


def current_citations(world_id, parsed, context):
    if not parsed.get("valid") or parsed["action"]["action"] != "submit":
        return False
    current = public_task(world_id)["source_versions"]
    citations = {(c["source_id"], c["source_version"]) for c in parsed["action"]["citations"]}
    visible = set()
    for item in context["materialized"]:
        content = item["content"]
        body = content.get("verified_source", content.get("source_receipt"))
        if body is not None and content["current"]:
            visible.add((body["source_id"], body["source_version"]))
    return citations == set(current.items()) and citations <= visible
