"""The E4 shared-capacity fixture: does the 2x2 identify an allocation effect at all?

This is the round BEFORE the experiment. Nothing here measures whether the colony
allocation is better; it establishes that the four cells are a legal factorial design
and that the colony arm can produce an allocation FIFO cannot. Everything is asserted
against the real ledger and the real CLI, never against a mock's call list.

The governing rule for this phase is the owner's: the workload changed, the policy
layer did not. So one test parses the policy-layer modules and asserts that the
experiment's name appears nowhere in their code - the fixture names the experiment,
the runtime never does.

Two deliberate scoping notes, stated here rather than hidden in a helper:

* The contamination scan excludes DOCSTRINGS. ``runner/runtime.py`` calls a resume
  "not a new experiment" in ``resume_run``'s prose. Prose about experiments is not an
  experiment-specific code branch, and the test asserts separately that every hit in
  the unparsed module lies inside a docstring.
* Agent ids, task ids and declared costs are READ FROM THE FIXTURE, never hard-coded.
  The workload schema has already been revised once during this phase; a test that
  pins names would then be asserting the fixture's history instead of its properties.
"""

import ast
import contextlib
from fractions import Fraction
import io
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from pheroos_interaction.runner import anthropic, audit, cli, contracts, runtime, runtime_policies, tools
from pheroos_interaction.runner.contracts import ContractError
from pheroos_interaction.runner.orchestration import OrchestrationSession

ROOT = Path(__file__).resolve().parents[2]
E4 = ROOT / "examples" / "e4"
SCRIPT = E4 / "script.json"
CELLS = {"A": "cell-a-fifo-fixed.json", "B": "cell-b-response-fixed.json",
         "C": "cell-c-fifo-evaporation.json", "D": "cell-d-response-evaporation.json"}
# The declared design: A/C are the baseline allocation, B/D the colony one; A/B the
# baseline lease, C/D the colony one. Asserted field by field in the single-factor test.
FIFO_CELLS, COLONY_CELLS = ("A", "C"), ("B", "D")
POLICY_MODULES = ("runtime.py", "runtime_policies.py", "orchestration.py",
                  "contracts.py", "audit.py")
EXPERIMENT_TERMS = ("e4", "experiment", "cell_a", "cell-a", "cell_b", "cell-b",
                    "cell_c", "cell-c", "cell_d", "cell-d", "fifo_fixed", "response_fixed")


# ---------------------------------------------------------------- fixture access

def raw(label):
    return json.loads((E4 / CELLS[label]).read_text())


def spec_of(label):
    return contracts.workflow_spec(raw(label))


def script():
    return anthropic.load_script(SCRIPT)


def eligible(task):
    """The agents a task declares as legal executors, in either schema spelling."""
    return list(task["agents"]) if "agents" in task else [task["agent"]]


def model_tasks(spec):
    return [task for task in spec["tasks"] if task["kind"] == "model"]


def worker_costs(spec):
    return {name: worker["cost"] for name, worker in spec["capacity"]["workers"].items()}


def cheaper_than(costs, agent, among):
    """The derivation the policy plane performs: how many eligible agents cost less."""
    return sum(costs[name] < costs[agent] for name in among)


# ---------------------------------------------------------------- ledger access

def ledger_dump(path):
    """Every row of every table, read-only: the fullest snapshot a replay could disturb."""
    connection = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: [dict(row) for row in connection.execute("SELECT * FROM " + name)]
                for name in names}
    finally:
        connection.close()


def claim_map(directory):
    """Which agent actually claimed each task, from each call's DURABLE permission.

    Not from the task's binding: the binding records the agent the runtime believed it
    was building a request for, while the permission is what the ledger admitted at
    dispatch. An offline reader recovers the claimant from the permission alone.
    """
    owners = {}
    for row in ledger_dump(directory / "session.sqlite")["calls"]:
        assert row["permission"] is not None, "a settled call carries no permission"
        owners.setdefault(row["work_id"], set()).add(json.loads(row["permission"])["owner"])
    assert all(len(seen) == 1 for seen in owners.values()), "a task was claimed by two agents"
    return {work: seen.pop() for work, seen in owners.items()}


def artifact_values(directory):
    return {row["work_id"]: json.loads(row["value"])
            for row in ledger_dump(directory / "session.sqlite")["artifacts"]}


def model_receipts(directory):
    """The recorded model message per task: what the provider actually returned."""
    out = {}
    for row in ledger_dump(directory / "session.sqlite")["calls"]:
        response = json.loads(row["response"])
        if "message" in response:
            out[row["work_id"]] = response["message"]
    return out


def system_headers(directory):
    return {row["work_id"]: json.loads(row["request"])["arguments"]["request"]["system"]
            for row in ledger_dump(directory / "session.sqlite")["calls"]}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Run all four cells once through the real CLI; every test reads these ledgers."""
    root = tmp_path_factory.mktemp("e4")
    out = {}
    for label, name in CELLS.items():
        directory = root / label
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main(["orchestrate", "--workflow", str(E4 / name),
                             "--output", str(directory), "--script", str(SCRIPT)])
        out[label] = {"code": code, "dir": directory,
                      "report": json.loads(buffer.getvalue().strip().splitlines()[-1]),
                      "frozen": json.loads((directory / "frozen.json").read_text())}
    return out


# ---------------------------------------------------------------- 1. identification

def test_two_tasks_and_two_agents_are_ready_at_the_same_moment(tmp_path):
    """An allocation experiment needs a real choice: a queue AND more than one claimant.

    Readiness is taken from the ledger's own ``ready_work``, not from the JSON: a task
    the platform would not offer an agent is not a decision point however the file
    declares it.
    """
    spec = spec_of("B")
    session = OrchestrationSession.create(tmp_path / "ready.sqlite", spec=spec)
    queues = {agent["id"]: [row["id"] for row in session.ready_work(agent["id"])]
              for agent in spec["agents"]}
    contested = [agent for agent, queue in queues.items() if len(queue) >= 2]
    assert len(contested) >= 2, queues
    shared = set.intersection(*(set(queues[agent]) for agent in contested))
    assert len(shared) >= 2, queues
    # The same moment, not two moments: one freshly created session was read.
    assert all(queues[agent] == queues[contested[0]] for agent in contested)


def test_at_least_one_task_declares_more_than_one_eligible_agent():
    spec = spec_of("B")
    widths = {task["id"]: len(eligible(task)) for task in model_tasks(spec)}
    assert max(widths.values()) > 1, widths
    declared = {agent["id"] for agent in spec["agents"]}
    for task in model_tasks(spec):
        assert set(eligible(task)) <= declared


def test_the_host_identity_is_not_part_of_the_allocation_choice(tmp_path):
    """No host task exists here, so nothing in the 2x2 rides on the host's ready order."""
    spec = spec_of("B")
    assert all(task["kind"] == "model" for task in spec["tasks"])
    session = OrchestrationSession.create(tmp_path / "host.sqlite", spec=spec)
    assert session.ready_work(contracts.HOST_AGENT) == []


# ---------------------------------------------------------------- 2. heterogeneity

def test_the_declared_worker_costs_are_not_all_identical():
    spec = spec_of("B")
    costs = worker_costs(spec)
    assert len(set(costs.values())) > 1, costs
    # The spread must fall inside a task's eligible set, which is where the decision is.
    assert any(len({costs[name] for name in eligible(task)}) > 1 for task in model_tasks(spec))


def test_one_agent_has_cheaper_capacity_and_the_cheapest_legitimately_has_none():
    """Both halves matter: a workforce where every agent is the cheapest has no choice."""
    spec = spec_of("B")
    costs = worker_costs(spec)
    task = next(task for task in model_tasks(spec) if len({costs[n] for n in eligible(task)}) > 1)
    names = eligible(task)
    derived = {name: cheaper_than(costs, name, names) for name in names}
    assert any(count > 0 for count in derived.values()), derived
    cheapest = min(names, key=lambda name: costs[name])
    assert derived[cheapest] == 0, derived
    assert costs[cheapest] == min(costs[name] for name in names)


def test_the_plane_defers_the_expensive_worker_and_lets_the_cheapest_claim(tmp_path):
    """The heterogeneity is not decorative: it changes what the policy returns.

    Driven through the public ``RuntimePolicies.select_work`` on a real ready queue,
    so this is the same decision the sweep makes, not a re-derivation of it.
    """
    spec = spec_of("B")
    session = OrchestrationSession.create(tmp_path / "defer.sqlite", spec=spec)
    plane = runtime_policies.RuntimePolicies.from_spec(spec)
    baseline = runtime_policies.RuntimePolicies.from_spec(spec_of("A"))
    costs = worker_costs(spec)
    task = next(task for task in model_tasks(spec) if len({costs[n] for n in eligible(task)}) > 1)
    names = eligible(task)
    dearest = max(names, key=lambda name: costs[name])
    cheapest = min(names, key=lambda name: costs[name])

    def decide(policies, agent):
        ready = session.ready_work(agent)
        for row in ready:                      # the sweep annotates each row with ITS task's set
            row["eligible"] = contracts.eligible_agents(session.task(row["id"]))
        return policies.select_work(ready, {"agent": agent, "spec_digest": contracts.digest(spec),
                                            "ledger_index": 0})

    assert decide(plane, dearest) is None
    assert decide(plane, cheapest) is not None
    # The very same queue under the baseline arm: FIFO never defers.
    assert decide(baseline, dearest) is not None
    assert decide(baseline, cheapest) is not None


def test_a_workforce_with_no_cost_spread_is_refused_at_spec_validation():
    flattened = raw("B")
    only = min(worker["cost"] for worker in flattened["capacity"]["workers"].values())
    for worker in flattened["capacity"]["workers"].values():
        worker["cost"] = only
    with pytest.raises(ContractError, match="differ in declared cost"):
        contracts.workflow_spec(flattened)


def test_a_cost_spread_no_task_can_use_is_refused_at_spec_validation():
    """Degeneracy is judged at the decision locus, so a spread outside every eligible
    set is refused too - otherwise the colony arm would be FIFO wearing a threshold."""
    narrowed = raw("B")
    costs = {name: worker["cost"] for name, worker in narrowed["capacity"]["workers"].items()}
    dearest = max(costs, key=lambda name: costs[name])
    for task in narrowed["tasks"]:
        if task["kind"] == "model":
            task["agents"] = [dearest]
    with pytest.raises(ContractError, match="differ in declared cost"):
        contracts.workflow_spec(narrowed)


def test_the_baseline_cells_need_no_capacity_declaration_to_validate():
    """FIFO makes no economic claim, so the fixture's capacity block is inert for A and C."""
    for label in FIFO_CELLS:
        stripped = raw(label)
        stripped.pop("capacity")
        assert contracts.workflow_spec(stripped)["policies"]["allocation"]["kind"] == "fifo"


# ---------------------------------------------------------------- 3. single factor

def test_the_four_cells_share_one_workload_once_the_policies_block_is_stripped():
    """The only declared difference is the arm. Checked on the raw files AND on the
    canonical records, because validation could in principle normalise a difference away."""
    raw_digests, canonical_digests = set(), set()
    for label in CELLS:
        document = raw(label)
        assert document.pop("policies")
        raw_digests.add(contracts.digest(document))
        canonical = spec_of(label)
        assert canonical.pop("policies")
        canonical_digests.add(contracts.digest(canonical))
    assert len(raw_digests) == 1
    assert len(canonical_digests) == 1


def test_the_policy_blocks_are_a_clean_two_by_two():
    blocks = {label: spec_of(label)["policies"] for label in CELLS}
    assert all(set(block) == {"allocation", "lease"} for block in blocks.values())

    def changed(left, right):
        return {slot for slot in ("allocation", "lease") if blocks[left][slot] != blocks[right][slot]}

    assert changed("A", "B") == {"allocation"}
    assert changed("A", "C") == {"lease"}
    assert changed("C", "D") == {"allocation"}
    assert changed("B", "D") == {"lease"}
    assert changed("A", "D") == {"allocation", "lease"}
    # Field by field, so "equal" is not hiding a reordered or renamed parameter.
    assert blocks["A"]["lease"] == blocks["B"]["lease"]
    assert blocks["C"]["lease"] == blocks["D"]["lease"]
    assert blocks["A"]["allocation"] == blocks["C"]["allocation"]
    assert blocks["B"]["allocation"] == blocks["D"]["allocation"]
    assert {blocks[label]["allocation"]["kind"] for label in FIFO_CELLS} == {"fifo"}
    assert {blocks[label]["allocation"]["kind"] for label in COLONY_CELLS} == {"response"}
    assert {blocks[label]["lease"]["kind"] for label in ("A", "B")} == {"fixed"}
    assert {blocks[label]["lease"]["kind"] for label in ("C", "D")} == {"evaporation"}


# ---------------------------------------------------------------- 4. validate, run, replay

@pytest.mark.parametrize("label", sorted(CELLS))
def test_each_cell_validates_and_revalidates_to_the_same_record(label):
    spec = spec_of(label)
    assert spec["format"] in contracts.SPEC_FORMATS
    assert contracts.digest(contracts.workflow_spec(spec)) == contracts.digest(spec)


@pytest.mark.parametrize("label", sorted(CELLS))
def test_each_cell_runs_to_success_with_three_artifacts_and_three_model_calls(runs, label):
    record = runs[label]
    report, metrics = record["report"], record["report"]["metrics"]
    assert (record["code"], report["status"]) == (0, "success")
    assert (metrics["model_calls"], metrics["tool_calls"], metrics["artifacts"]) == (3, 0, 3)
    assert metrics["unknown_calls"] == 0 and metrics["outstanding_reservations"] == 0
    assert metrics["accounting_violations"] == 0 and metrics["proposal_rejections"] == 0
    assert {task["status"] for task in report["tasks"].values()} == {"published"}
    assert record["frozen"]["spec_digest"] == contracts.digest(spec_of(label))


@pytest.mark.parametrize("label", sorted(CELLS))
def test_each_cell_replays_pass_with_no_new_calls_and_an_unchanged_ledger(runs, label):
    path = runs[label]["dir"] / "session.sqlite"
    before = ledger_dump(path)
    report = audit.replay_run(path)
    assert (report["status"], report["failures"]) == ("PASS", [])
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    assert report["checks"] > 0
    assert ledger_dump(path) == before


# ---------------------------------------------------------------- 5. manipulation check

def test_the_colony_allocation_claims_differently_from_fifo(runs):
    """The point of this round: a legally different allocation, not merely a deferral.

    The claim map is built from each call's durable permission owner, so it is what an
    offline reader recovers; the binding is not consulted.
    """
    claims = {label: claim_map(runs[label]["dir"]) for label in CELLS}
    assert all(set(value) == {task["id"] for task in model_tasks(spec_of("A"))}
               for value in claims.values())

    def differing(left, right):
        return sorted(task for task in claims[left] if claims[left][task] != claims[right][task])

    fifo_vs_colony = differing("A", "B")
    evaporation_pair = differing("C", "D")
    assert len(fifo_vs_colony) >= 1, claims
    assert len(evaporation_pair) >= 1, claims
    # Name them, so a later narrowing of the difference is visible as a failure here.
    assert fifo_vs_colony == ["t1", "t2", "t3"], claims
    assert evaporation_pair == ["t1", "t2", "t3"], claims
    # And the difference is a different WORKER, not a different task order.
    assert set(claims["A"].values()) != set(claims["B"].values()), claims


def test_every_claim_is_an_eligible_agent_and_fifo_claims_the_first_declared_one(runs):
    by_task = {task["id"]: eligible(task) for task in model_tasks(spec_of("A"))}
    for label in CELLS:
        for task, owner in claim_map(runs[label]["dir"]).items():
            assert owner in by_task[task], (label, task, owner)
    for label in FIFO_CELLS:
        for task, owner in claim_map(runs[label]["dir"]).items():
            assert owner == by_task[task][0], (label, task, owner)
    # The colony arm chose someone the baseline never chose: a real allocation decision.
    colony = {owner for label in COLONY_CELLS for owner in claim_map(runs[label]["dir"]).values()}
    baseline = {owner for label in FIFO_CELLS for owner in claim_map(runs[label]["dir"]).values()}
    assert colony - baseline, (colony, baseline)


def test_the_lease_factor_is_declared_and_different_but_changes_no_allocation(runs):
    """Honest limit of this fixture: L3 is delivered but inert.

    The two lease arms resolve to different TTLs, so the treatment is real. Nothing in
    this workload stalls or expires, so no claim, artifact or outcome differs between
    them - the lease dimension of the 2x2 currently carries no observable effect.
    """
    ttls = {label: runtime_policies.RuntimePolicies.from_spec(spec_of(label)).lease_duration()
            for label in CELLS}
    assert ttls["A"] == ttls["B"] and ttls["C"] == ttls["D"]
    assert ttls["A"] != ttls["C"], ttls
    assert claim_map(runs["A"]["dir"]) == claim_map(runs["C"]["dir"])
    assert claim_map(runs["B"]["dir"]) == claim_map(runs["D"]["dir"])
    for label in CELLS:
        events = {event["event_type"] for event in
                  (json.loads(row["value"]) for row in ledger_dump(
                      runs[label]["dir"] / "session.sqlite")["events"])}
        assert not any("expir" in name or "lost" in name for name in events), (label, events)
        arm = runs[label]["report"]["metrics"]["policies"]["runtime_policies"]["lease"]
        assert arm == spec_of(label)["policies"]["lease"]["kind"]


# ---------------------------------------------------------------- 6. workload held constant

def test_the_model_script_is_matched_by_task_and_step_and_never_by_agent():
    loaded = script()
    assert all(set(entry) == {"task", "step", "response"} for entry in loaded["responses"])
    assert "agent" not in json.dumps(loaded)
    # The routing key the transport reads is the host-written header line; it carries
    # the task, the version and the step, and no identity.
    assert anthropic.HEADER.pattern == r"^pheroos-orchestration task=(\S+) version=(\d+) step=(\d+)$"


def test_the_scripted_response_follows_the_task_and_step_and_ignores_everything_else():
    """A behavioural check on the real transport, not an assertion about a mock.

    The fixture gives both workers the SAME model config, so comparing two per-agent
    requests would compare two identical requests and prove nothing. The routing is
    therefore probed with a model string no agent declares: if the answer is unchanged
    the key really is ``(task, step)``, and changing that key really does change it.
    """
    spec = spec_of("B")
    transport = anthropic.FakeTransport(script())
    header = anthropic.HEADER_PREFIX + "task=t1 version=1 step=0\npolicy text"
    declared = transport({"system": header, "model": spec["agents"][0]["model"]["model"]})
    foreign = transport({"system": header, "model": "some-other-model", "max_tokens": 999})
    assert json.dumps(declared, sort_keys=True) == json.dumps(foreign, sort_keys=True)
    other_task = transport({"system": anthropic.HEADER_PREFIX + "task=t2 version=1 step=0\nx"})
    assert json.dumps(other_task, sort_keys=True) != json.dumps(declared, sort_keys=True)
    # The anti-confound rule: execution-resource identity varies, the model does NOT.
    # If the workers ran different models, Y(response) - Y(fifo) would confound an
    # allocation effect with a model effect and the cell difference would be unreadable.
    configs = {json.dumps(agent["model"], sort_keys=True) for agent in spec["agents"]}
    assert len(configs) == 1, configs
    assert len(spec["agents"]) > 1


def test_the_recorded_request_headers_name_no_agent(runs):
    identities = {agent["id"] for agent in spec_of("A")["agents"]}
    for label in CELLS:
        for task, system in system_headers(runs[label]["dir"]).items():
            line = system.split("\n", 1)[0]
            assert anthropic.HEADER.match(line), line
            assert line == anthropic.HEADER_PREFIX + "task=%s version=1 step=0" % task
            assert not any(name in line for name in identities), line


def test_the_recorded_model_output_is_identical_across_all_four_cells(runs):
    receipts = {label: model_receipts(runs[label]["dir"]) for label in CELLS}
    wire = {label: json.dumps(value, sort_keys=True) for label, value in receipts.items()}
    assert len(set(wire.values())) == 1, {label: sorted(value) for label, value in receipts.items()}
    assert len(receipts["A"]) == 3


def test_the_published_artifact_values_are_identical_across_all_four_cells(runs):
    values = {label: artifact_values(runs[label]["dir"]) for label in CELLS}
    assert len({json.dumps(value, sort_keys=True) for value in values.values()}) == 1, values
    assert len(values["A"]) == 3
    # One script, one digest, for every cell.
    assert len({runs[label]["frozen"]["script_digest"] for label in CELLS}) == 1
    assert runs["A"]["frozen"]["script_digest"] == contracts.digest(script())


# ---------------------------------------------------------------- 7. no contamination

def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.fix_missing_locations(tree)


def test_no_policy_layer_module_names_the_experiment_in_its_code():
    """`ast.unparse` drops comments, so only code counts; docstrings are excluded and
    the next assertion proves every remaining hit really is prose."""
    hits = {}
    for name in POLICY_MODULES:
        source = (ROOT / "runner" / name).read_text()
        code = ast.unparse(_strip_docstrings(ast.parse(source))).lower()
        found = [term for term in EXPERIMENT_TERMS if term in code]
        if found:
            hits[name] = found
    assert hits == {}


def test_any_experiment_word_left_in_a_policy_module_is_prose_only():
    for name in POLICY_MODULES:
        source = (ROOT / "runner" / name).read_text()
        whole = ast.unparse(ast.parse(source)).lower()
        code = ast.unparse(_strip_docstrings(ast.parse(source))).lower()
        for term in EXPERIMENT_TERMS:
            assert whole.count(term) == 0 or code.count(term) == 0, (name, term)


def test_the_fixture_names_the_experiment_and_the_runtime_does_not():
    """The contrast that makes the rule checkable: the name lives in the workload."""
    assert all("e4" in spec_of(label)["run_id"] for label in CELLS)
    runtime_code = ast.unparse(_strip_docstrings(ast.parse((ROOT / "runner" / "runtime.py").read_text())))
    assert "e4" not in runtime_code.lower()


# ---------------------------------------------------------------- 8. metric inventory

def test_metric_families_outcome_and_cost_are_present_allocation_and_lease_are_not(runs, tmp_path):
    """The honest inventory the next phase works from. NOTHING is added to the source
    here; this test records exactly which of the owner's four families the ledger
    already reports and which it does not.

    outcome     - NOT in ``Runtime.metrics()``; carried by the outcome record instead.
    cost        - present: model calls, tool calls, known tokens, sweeps. Control
                  operations are bounded but never counted into a metric.
    allocation  - ABSENT. Claims are recoverable from call permissions, but deferrals
                  and waiting leave no durable trace at all.
    lease       - ABSENT. The arm's NAME is reported; no grant, TTL or expiry is.
    """
    spec = spec_of("B")
    session = OrchestrationSession.create(tmp_path / "metrics.sqlite", spec=spec)
    engine = runtime.Runtime(session, registry=tools.build_registry(spec, E4),
                             transports={"fake": anthropic.FakeTransport(script())})
    outcome = engine.run()
    metrics = engine.metrics()

    # -- the exact inventory, pinned so an addition is a visible change here
    assert set(metrics) == {
        "model_calls", "tool_calls", "known_tokens", "outstanding_reservations",
        "unknown_calls", "unknown_tokens", "accounting_violations", "proposal_rejections",
        "decisions", "late_reconciliations", "consumed_receipts", "artifacts",
        "blocked_dependencies", "policies"}
    assert set(outcome["metrics"]) == set(metrics) | {"sweeps", "max_sweeps"}

    # -- COST: present
    assert (metrics["model_calls"], metrics["tool_calls"]) == (3, 0)
    assert metrics["known_tokens"] > 0
    assert outcome["metrics"]["sweeps"] >= 3
    assert outcome["metrics"]["sweeps"] <= outcome["metrics"]["max_sweeps"]
    # Control operations bound the run but are never reported as a count.
    assert not {"control_operations", "platform_operations", "operations"} & set(metrics)

    # -- OUTCOME: not a metric; it is the record around the metrics
    assert not {"status", "outcome", "completed", "abstained", "terminal"} & set(metrics)
    assert outcome["status"] == "success"
    assert {task["status"] for task in outcome["tasks"].values()} == {"published"}
    assert metrics["artifacts"] == 3 and metrics["blocked_dependencies"] == 0

    # -- ALLOCATION: absent, and deferrals are not merely unreported, they are unrecorded
    assert not {"claims", "claimed", "deferrals", "deferred", "waiting", "wait_time",
                "queue_depth", "allocation_decisions"} & set(metrics)
    costs = worker_costs(spec)
    dearest = max(costs, key=lambda name: costs[name])
    owners = set(claim_map(runs["B"]["dir"]).values())
    assert dearest not in owners, owners
    events = [json.loads(row["value"]) for row in
              ledger_dump(runs["B"]["dir"] / "session.sqlite")["events"]]
    assert not any(event.get("details", {}).get("owner") == dearest for event in events)
    # The expensive worker deferred on every sweep and the ledger records no such event.
    assert not any("defer" in event["event_type"] for event in events)

    # -- LEASE: absent; only the arm's name survives into the report
    assert not {"lease_grants", "lease_expiries", "leases", "lease_seconds",
                "lease_ttl", "expiries"} & set(metrics)
    described = metrics["policies"]
    assert described["runtime_policies"] == {"allocation": "response", "lease": "fixed"}
    assert "seconds" not in json.dumps(described) and "ttl" not in json.dumps(described)
    assert described["platform_capabilities"]["commitment"]["active_decisions"] == 0


def test_the_claim_map_is_the_only_allocation_evidence_and_it_is_recoverable(runs):
    """Allocation is unreported but not unrecoverable: the permission owner survives.

    This is what the next phase can build an allocation metric from without adding any
    new write path - and it is also the boundary of what is recoverable, since a
    deferral produces no row to recover.
    """
    for label in CELLS:
        rows = ledger_dump(runs[label]["dir"] / "session.sqlite")["calls"]
        assert len(rows) == 3
        for row in rows:
            permission = json.loads(row["permission"])
            assert permission["owner"] == json.loads(row["request"])["binding"]["agent"]
            assert permission["task_id"] == row["work_id"]


# ---------------------------------------------------------------- 8. the manipulation, asserted at the mechanism

def hill_probability(arguments, exponent, backlog, service_time, latency_cost):
    """The response-threshold probability, in exact rational arithmetic.

    ``s`` is the time the cheaper capacity needs to drain the backlog and ``theta``
    the break-even delay of the deterministic step. Recomputed here from the frozen
    declaration rather than imported, so the test would notice the mechanism changing
    underneath it.
    """
    s = Fraction(backlog) * Fraction(service_time) / arguments["cheaper_workers"]
    theta = ((Fraction(arguments["worker_cost"]) - Fraction(arguments["cheapest_cost"]))
             / Fraction(latency_cost))
    return s ** exponent / (s ** exponent + theta ** exponent)


def test_the_response_defers_because_its_declared_draw_exceeds_the_hill_probability():
    """The manipulation asserted at the MECHANISM, not inferred from who executed.

    Reading "the policy must have deferred" back from the final executor would pass
    just as happily if the expensive worker had never been consulted, or if some other
    part of the runtime had excluded it. So this computes the Hill probability and the
    replayable draw from the frozen declaration and asserts the comparison that the
    mechanism actually performs.

    The seed is ``e4``, named in advance after the experiment itself. It was NOT
    searched for a seed that produces a deferral: the assertion below states whatever
    relation the declared seed yields, and a formal run would freeze its seeds and
    replications before looking at any of them.
    """
    spec = spec_of("B")
    plane = runtime_policies.RuntimePolicies.from_spec(spec)
    allocation = plane.allocation
    assert allocation.name == "response"
    capacity = spec["capacity"]
    costs = worker_costs(spec)
    tasks = [task["id"] for task in model_tasks(spec)]
    names = eligible(model_tasks(spec)[0])
    dearest = max(names, key=lambda name: costs[name])
    cheapest = min(names, key=lambda name: costs[name])
    context = {"agent": dearest, "spec_digest": contracts.digest(spec), "ledger_index": 0}

    arguments = allocation._arguments(names, dearest)
    probability = hill_probability(arguments, allocation.exponent, len(tasks),
                                   capacity["service_time"], capacity["latency_cost"])
    assert 0 < probability < 1, probability
    for task in tasks:
        draw = Fraction(allocation.draw(context, task))
        assert draw >= probability, (task, float(draw), float(probability))

    # The cheapest worker has no cheaper capacity at all, so the graded branch is not
    # reached for it and no draw can make it defer.
    assert allocation._arguments(names, cheapest)["cheaper_workers"] == 0

    # The plane's own answer on the same queue agrees with the arithmetic above.
    rows = [{"id": task, "age": index, "depth": 0, "eligible": names}
            for index, task in enumerate(tasks)]
    assert plane.select_work(rows, context) is None
    assert plane.select_work(rows, dict(context, agent=cheapest)) == tasks[0]


def test_the_declared_agent_order_decides_who_claims_and_is_frozen_in_the_digest(tmp_path):
    """Worker-enumeration order is workload identity, not presentation.

    Under the arm that never defers, whichever worker is offered a shared task first
    claims it. If canonicalization sorted the agent list, permuting the declaration
    would silently change an experimental condition without changing the arm, so this
    asserts the order reaches both the digest and the sweep.
    """
    source = raw("A")
    spec = contracts.workflow_spec(source)
    flipped = contracts.workflow_spec(dict(source, agents=list(reversed(source["agents"]))))
    assert contracts.worker_order(spec) == [agent["id"] for agent in source["agents"]]
    assert contracts.worker_order(flipped) == list(reversed(contracts.worker_order(spec)))
    assert contracts.digest(spec) != contracts.digest(flipped)

    chosen = {}
    for label, record in (("declared", spec), ("flipped", flipped)):
        session = OrchestrationSession.create(tmp_path / (label + ".sqlite"), spec=record)
        engine = runtime.Runtime(session, registry=tools.build_registry(record, E4),
                                 transports={"fake": anthropic.FakeTransport(script())})
        chosen[label] = engine._select_work()
    assert chosen["declared"]["agent"] == contracts.worker_order(spec)[0]
    assert chosen["flipped"]["agent"] == contracts.worker_order(flipped)[0]
    assert chosen["declared"]["agent"] != chosen["flipped"]["agent"]
    # Same task, different executor: the ORDER moved the decision, nothing else did.
    assert chosen["declared"]["work"] == chosen["flipped"]["work"]


def test_one_task_sits_in_both_workers_queues_and_is_never_deduplicated(tmp_path):
    """The decision object is the (agent, work) PAIR, so both opportunities must exist.

    Deduplicating the ready queues by work id would erase the second worker's legal
    execution opportunity - which is precisely the thing a shared-capacity workload
    exists to expose - and the sweep would silently become single-executor again.
    """
    spec = spec_of("B")
    session = OrchestrationSession.create(tmp_path / "pairs.sqlite", spec=spec)
    names = [agent["id"] for agent in spec["agents"]]
    queues = {name: [row["id"] for row in session.ready_work(name)] for name in names}
    shared = set.intersection(*(set(queue) for queue in queues.values()))
    assert len(shared) == len(model_tasks(spec)) >= 2, queues
    pairs = {(name, work) for name, queue in queues.items() for work in queue}
    assert len(pairs) == len(names) * len(shared), pairs


@pytest.mark.parametrize("label", sorted(CELLS))
def test_each_cell_resumes_without_dispatching_a_duplicate_call(runs, tmp_path_factory, label):
    """A resume of a completed cell re-opens the ledger and sends nothing.

    Resume is not a replay and not a new experiment: budgets are not reset, a settled
    receipt is consumed rather than repeated. The run is copied first so the shared
    module fixture the other tests read is never mutated.
    """
    source = runs[label]["dir"]
    target = tmp_path_factory.mktemp("resume-" + label) / "run"
    shutil.copytree(source, target)
    before = {row["id"]: row for row in ledger_dump(target / "session.sqlite")["calls"]}
    outcome = runtime.resume_run(target, script_path=SCRIPT)
    after = {row["id"]: row for row in ledger_dump(target / "session.sqlite")["calls"]}
    assert outcome["status"] == "success"
    assert set(after) == set(before), set(after) ^ set(before)
    assert all(after[key]["response"] == before[key]["response"] for key in before)
    assert claim_map(target) == claim_map(source)
    assert audit.replay_run(target / "session.sqlite", spec_dir=E4)["status"] == "PASS"
