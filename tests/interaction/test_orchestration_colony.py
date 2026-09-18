"""The colony policy plane: L2 and L3 active, L1 defined but not active.

The runtime asks one ``RuntimePolicies`` for its decisions and imports no colony
mechanism directly, so a baseline arm and a colony arm differ in the policy object
alone. L1 is validated against a platform session with genuine competing candidates;
it is not reachable from the orchestration runtime, which has no arbitration locus.
"""

import ast
import json
from pathlib import Path

import pytest

from pheroos_interaction import commitment as mechanism
from pheroos_interaction.records import StateError
from pheroos_interaction.runner import (anthropic, audit, contracts, runtime, runtime_policies,
                                        tools)
from pheroos_interaction.runner.contracts import ContractError
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.orchestration import OrchestrationSession
from pheroos_interaction.runner.platform import PlatformMixin, PlatformSession
from pheroos_interaction.runner.session import Session

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples" / "orchestration"
# Primitive workforce facts only; cheapest_cost and cheaper_workers are derived.
CAPACITY = {"workers": {"expensive": {"cost": 6.0}, "cheap": {"cost": 1.0}},
            "latency_cost": 1.0, "service_time": 1.0}
SHARED = ["expensive", "cheap"]


def raw(name="workflow.json"):
    return json.loads((EXAMPLES / name).read_text())


def spec_of(name="workflow.json"):
    return contracts.workflow_spec(raw(name))


def script_of(name="script.json"):
    return anthropic.load_script(EXAMPLES / name)


def engine_for(tmp_path, spec, script=None, **options):
    session = OrchestrationSession.create(tmp_path / "s.sqlite", spec=spec)
    return session, runtime.Runtime(
        session, registry=tools.build_registry(spec, EXAMPLES),
        transports={"fake": anthropic.FakeTransport(script or script_of())}, **options)


def artifact_of(session, work_id):
    row = next((item for item in session.snapshot()["artifacts"] if item["work_id"] == work_id), None)
    return None if row is None else json.loads(row["value"])


def ready(*ids, eligible=None):
    """Ready rows as the runtime supplies them: each carries its OWN task's eligibility."""
    return [{"id": name, "age": index, "depth": 0, "eligible": list(eligible or SHARED)}
            for index, name in enumerate(ids)]


def context(agent="expensive", index=0):
    return {"agent": agent, "spec_digest": "digest", "ledger_index": index}


def imports_of(path):
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


# ---------------------------------------------------------------- coupling


def test_the_runtime_imports_no_colony_mechanism_directly():
    """Every colony decision goes through the plane, so an arm can be swapped wholesale."""
    imported = imports_of(ROOT / "runner" / "runtime.py")
    for name in ("commitment", "leases", "sequential", "policies"):
        assert name not in imported, f"runtime.py reaches for {name} directly"
    assert "RuntimePolicies" in imported


def test_the_plane_adapts_the_existing_mechanisms_rather_than_reimplementing_them():
    imported = imports_of(ROOT / "runner" / "runtime_policies.py")
    assert {"commitment", "leases", "policies"} <= imported


def test_the_plane_module_name_does_not_collide_with_the_claim_policies_module():
    assert (ROOT / "runner" / "runtime_policies.py").exists()
    assert (ROOT / "runner" / "policies.py").exists()
    assert not (ROOT / "runner" / "policy.py").exists()


def test_the_orchestration_ledger_keeps_the_platform_mro():
    """Orchestration tables extend the platform ledger; they are not a layer beneath it."""
    assert [cls.__name__ for cls in OrchestrationSession.__mro__[:4]] == [
        "OrchestrationSession", "OrchestrationMixin", "PlatformMixin", "Session"]
    assert not issubclass(OrchestrationSession, PlatformSession)
    assert PlatformSession.__mro__[1:3] == (PlatformMixin, Session)


def test_the_pure_colony_mechanisms_import_no_runner_module():
    for name in ("sequential", "commitment", "leases"):
        assert not any("runner" in item
                       for item in imports_of(ROOT / "src" / "pheroos_interaction" / f"{name}.py"))


# ---------------------------------------------------------------- L2 allocation


def test_the_baseline_allocation_is_fifo():
    plane = runtime_policies.RuntimePolicies()
    assert plane.describe()["runtime_policies"]["allocation"] == "fifo"
    assert plane.select_work(ready("first", "second"), context()) == "first"
    assert plane.select_work([], context()) is None


def test_the_threshold_derives_cheapest_and_cheaper_from_the_eligible_set():
    """Both derived from frozen facts plus this task's eligibility; never declared twice."""
    plane = runtime_policies.RuntimePolicies(
        allocation=runtime_policies.ThresholdAllocation(CAPACITY))
    derived = plane.allocation._arguments(SHARED, "expensive")
    assert derived == {"worker_cost": 6.0, "cheapest_cost": 1.0, "cheaper_workers": 1,
                       "latency_cost": 1.0, "service_time": 1.0}
    # backlog 3: delay 1*3*1 = 3 against extra 5 * 1 cheaper = 5, so the expensive defers
    assert plane.select_work(ready("a", "b", "c"), context()) is None
    # the cheapest worker has no cheaper alternative, so it claims regardless
    assert plane.allocation._arguments(SHARED, "cheap")["cheaper_workers"] == 0
    assert plane.select_work(ready("a", "b", "c"), context(agent="cheap")) == "a"


def test_a_cost_spread_among_agents_that_cannot_execute_this_task_counts_for_nothing():
    """Degeneracy is judged at the decision locus: the task's own eligible set."""
    plane = runtime_policies.RuntimePolicies(
        allocation=runtime_policies.ThresholdAllocation(CAPACITY))
    alone = plane.allocation._arguments(["expensive"], "expensive")
    assert alone["cheaper_workers"] == 0 and alone["cheapest_cost"] == 6.0
    assert plane.select_work(ready("a", "b", "c", eligible=["expensive"]), context()) == "a"


def test_the_plane_refuses_a_capacity_model_missing_an_eligible_agent():
    plane = runtime_policies.RuntimePolicies(
        allocation=runtime_policies.ThresholdAllocation(CAPACITY))
    with pytest.raises(ContractError, match="omits an eligible agent"):
        plane.select_work(ready("w", eligible=["stranger"]), context(agent="stranger"))


def test_a_threshold_where_no_task_lets_two_prices_compete_is_refused():
    """A cost spread is worth nothing if no task lets differently priced workers compete."""
    source = raw()          # every task declares exactly one eligible agent
    source["policies"]["allocation"] = {"kind": "threshold"}
    source["capacity"] = {"workers": {"producer": {"cost": 6.0}, "reviewer": {"cost": 1.0}},
                          "latency_cost": 1.0, "service_time": 1.0}
    with pytest.raises(ContractError, match="eligible agents differ in declared cost"):
        contracts.workflow_spec(source)


def test_a_threshold_allocation_needs_a_declared_capacity_model():
    source = raw()
    source["policies"]["allocation"] = {"kind": "threshold"}
    with pytest.raises(ContractError, match="needs a declared capacity model"):
        contracts.workflow_spec(source)


def test_the_capacity_model_must_cover_every_declared_agent():
    source = raw()
    source["policies"]["allocation"] = {"kind": "threshold"}
    source["capacity"] = {"workers": {"producer": {"cost": 6.0}},
                          "latency_cost": 1.0, "service_time": 1.0}
    with pytest.raises(ContractError, match="capacity model omits reviewer"):
        contracts.workflow_spec(source)


def test_an_agent_declares_no_derived_capacity_variables():
    """worker_cost/cheapest_cost/cheaper_workers are never written into a spec."""
    source = raw()
    source["agents"][0]["capacity"] = {"worker_cost": 6.0}
    with pytest.raises(ContractError, match="agent requires exactly"):
        contracts.workflow_spec(source)
    assert "capacity" not in contracts.agent_spec(raw()["agents"][0])


def test_the_runtime_never_invents_a_capacity_model():
    """cheaper_workers is declared, never derived from which agents happen to be idle."""
    # Unparsing drops comments, so this asserts the CODE never touches capacity fields.
    source = ast.unparse(ast.parse(ROOT.joinpath("runner", "runtime.py").read_text()))
    assert "cheaper_workers" not in source
    assert "cheapest_cost" not in source
    assert '"cost"' not in source


def test_the_graded_response_draw_is_replayable_from_the_ledger():
    allocation = runtime_policies.ResponseThresholdAllocation(CAPACITY, exponent=8, seed="example")
    twin = runtime_policies.ResponseThresholdAllocation(CAPACITY, exponent=8, seed="example")
    draws = [allocation.draw(context(index=n), "t1") for n in range(6)]
    assert draws == [twin.draw(context(index=n), "t1") for n in range(6)]
    assert all(0 <= value < 1 for value in draws) and len(set(draws)) == len(draws)
    assert allocation.draw(context(agent="a"), "t1") != allocation.draw(context(agent="b"), "t1")
    # the decision object is the (agent, work) PAIR, so the work id keys the draw too
    assert allocation.draw(context(), "t1") != allocation.draw(context(), "t2")
    other = runtime_policies.ResponseThresholdAllocation(CAPACITY, exponent=8, seed="other")
    assert allocation.draw(context(), "t1") != other.draw(context(), "t1")


def test_the_allocation_policy_cannot_choose_work_outside_the_ready_queue():
    class Rogue:
        name = "rogue"

        def select(self, ready_rows, context_row):
            return "somewhere-else"

    with pytest.raises(ContractError, match="outside the ready queue"):
        runtime_policies.RuntimePolicies(allocation=Rogue()).select_work(ready("w"), context())


def test_the_host_finalizer_takes_ready_order_and_is_never_priced():
    """A host is a reserved identity with no model config, not a worker with a cost."""
    plane = runtime_policies.RuntimePolicies(
        allocation=runtime_policies.ThresholdAllocation(CAPACITY))
    assert plane.select_work(ready("w"), context()) is None
    assert plane.select_host_work(ready("w")) == "w"
    source = ast.unparse(ast.parse(ROOT.joinpath("runner", "runtime.py").read_text()))
    assert "select_host_work" in source and "cheapest" not in source


def test_a_legal_threshold_declaration_can_never_stall_the_run(tmp_path):
    """Judging degeneracy at the decision locus makes the deferral deadlock unreachable.

    An agent defers only when a cheaper agent is eligible for the same task, and that
    cheaper agent is then the cheapest of that set, so it claims. The runtime keeps a
    reason for the stall as a net, but no validated spec can reach it.
    """
    plane = runtime_policies.RuntimePolicies(
        allocation=runtime_policies.ThresholdAllocation(CAPACITY))
    for eligible in (["expensive", "cheap"], ["cheap"], ["expensive"]):
        claims = [plane.select_work(ready("a", "b", "c", eligible=eligible), context(agent=name))
                  for name in eligible]
        assert any(claim is not None for claim in claims), eligible
    # and the declaration that would otherwise stall is refused before any ledger exists
    source = raw()
    source["policies"]["allocation"] = {"kind": "threshold"}
    source["capacity"] = {"workers": {"producer": {"cost": 6.0}, "reviewer": {"cost": 1.0}},
                          "latency_cost": 1.0, "service_time": 1.0}
    with pytest.raises(ContractError, match="eligible agents differ in declared cost"):
        contracts.workflow_spec(source)


def test_the_runtime_takes_its_allocation_from_the_declared_policy(tmp_path):
    session, engine = engine_for(tmp_path, spec_of())
    assert engine.policies.describe()["runtime_policies"]["allocation"] == "fifo"
    assert engine._select_work() == {"agent": "producer", "work": "produce"}


# ---------------------------------------------------------------- L3 lease


def test_the_baseline_lease_is_the_incumbent_constant():
    plane = runtime_policies.RuntimePolicies()
    assert plane.describe()["runtime_policies"]["lease"] == "fixed"
    assert plane.lease_duration() == runtime_policies.DEFAULT_LEASE_SECONDS == 60


def test_the_evaporation_lease_comes_from_the_frozen_spec_not_live_history(tmp_path):
    declared = raw()["policies"]["lease"]
    assert set(declared) == {"kind", "stage_durations", "p_fail", "per_tick_cost",
                             "false_expiry_cost"}
    session, engine = engine_for(tmp_path, spec_of())
    assert engine.policies.describe()["runtime_policies"]["lease"] == "evaporation"
    assert engine.lease_seconds == 120.0 != runtime_policies.DEFAULT_LEASE_SECONDS
    # The same frozen spec yields the same TTL every time: nothing is read from history.
    again = runtime_policies.RuntimePolicies.from_spec(session.spec())
    assert again.lease_duration() == engine.lease_seconds


def test_an_injected_baseline_plane_restores_the_constant_lease(tmp_path):
    session, engine = engine_for(tmp_path, spec_of(),
                                 policies=runtime_policies.RuntimePolicies())
    assert engine.lease_seconds == runtime_policies.DEFAULT_LEASE_SECONDS


@pytest.mark.parametrize("bad", [
    {"kind": "evaporation", "stage_durations": [], "p_fail": .1, "per_tick_cost": .1,
     "false_expiry_cost": 1.},
    {"kind": "evaporation", "stage_durations": [0.0], "p_fail": .1, "per_tick_cost": .1,
     "false_expiry_cost": 1.},
    {"kind": "evaporation", "stage_durations": [1.], "p_fail": 2., "per_tick_cost": .1,
     "false_expiry_cost": 1.},
    {"kind": "fixed", "seconds": 0},
    {"kind": "nonexistent"},
])
def test_an_invalid_lease_declaration_never_reaches_a_ledger(bad):
    source = raw()
    source["policies"]["lease"] = bad
    with pytest.raises(ContractError):
        contracts.workflow_spec(source)


# ---------------------------------------------------------------- policy identity


def test_the_policy_arm_is_part_of_the_run_identity(tmp_path):
    """Swapping the arm changes the spec digest, so a ledger cannot continue under another."""
    baseline = raw()
    baseline["policies"] = {"allocation": {"kind": "fifo"}}
    colony = raw()
    assert contracts.digest(contracts.workflow_spec(baseline)) != \
        contracts.digest(contracts.workflow_spec(colony))
    session, engine = engine_for(tmp_path, spec_of())
    assert session.snapshot()["orchestration"]["spec_digest"] == engine.spec_digest
    assert engine.run()["metrics"]["policies"] == {
        "runtime_policies": {"allocation": "fifo", "lease": "evaporation"},
        "platform_capabilities": {"commitment": {"name": "min_loss", "active_decisions": 0}}}


# ---------------------------------------------------------------- L1 defined, not active


def test_the_commitment_slot_is_not_declarable_in_a_workflow_yet():
    """No arbitration locus exists, so declaring a commitment rule would be decorative."""
    assert "commitment" not in contracts.POLICY_SLOTS
    source = raw()
    source["policies"]["commitment"] = {"kind": "min_loss"}
    with pytest.raises(ContractError, match="policies requires"):
        contracts.workflow_spec(source)


def test_orchestration_work_refuses_candidate_arbitration(tmp_path):
    session, engine = engine_for(tmp_path, spec_of())
    assert engine.run()["status"] == "success"
    assert session.snapshot()["platform"]["limits"]["max_candidates"] == 1
    with pytest.raises(StateError, match="does not use candidate arbitration"):
        session.commit("produce", "producer", verify=lambda work, value: True, abstain_loss=1.0)


def test_the_runtime_exposes_no_candidate_commitment_entry_point(tmp_path):
    session, engine = engine_for(tmp_path, spec_of())
    assert not hasattr(engine, "commit_candidates")
    assert "commit" not in imports_of(ROOT / "runner" / "runtime.py")
    assert callable(engine.policies.commitment_rule)


def competition(tmp_path, losses, agents=("a", "b", "c")):
    """A real candidate contest on the platform: several agents propose for one work."""
    session = PlatformSession.create(
        tmp_path / "contest.sqlite", "contest", agents=list(agents), token_cap=0, max_calls=10,
        work=[{"id": "w", "version": 1, "dependencies": [], "agents": list(agents),
               "actions": ["tool.evaluate"]}], platform={})
    driver = SessionDriver(session, tools={"m": lambda arguments: {"by": arguments["by"]}})
    for agent, loss in zip(agents, losses):
        lease = session.claim(agent, "w")
        driver.evaluate(lease, "w:" + agent, "m", {"by": agent})
        session.propose(lease, "w:" + agent, loss)
        session.release(lease)
    return session


def test_the_baseline_commitment_publishes_the_least_declared_loss(tmp_path):
    session = competition(tmp_path, [0.12, 0.08, 0.15])
    plane = runtime_policies.RuntimePolicies()
    assert plane.describe()["platform_capabilities"]["commitment"] == {"name": "min_loss"}
    assert plane.commitment_rule(0.20) is None
    result = session.commit("w", verify=lambda work, value: True, abstain_loss=0.20,
                            rule=plane.commitment_rule(0.20))
    assert (result["decision"], result["call_id"]) == ("publish", "w:b")


def test_optimal_stopping_commitment_matches_the_pure_mechanism(tmp_path):
    plane = runtime_policies.RuntimePolicies(commitment=runtime_policies.OptimalStoppingCommitment(
        latency_cost=0.01, deadline=1, arrival_prob=0.0, loss_support=[0.5], loss_probs=[1.0]))
    rule = plane.commitment_rule(0.20)
    reference = mechanism.optimal_stopping_rule(0.20, 0.01, 1, 0.0, [0.5], [1.0], 0)
    rows = [{"call_id": "w:b", "certified_loss": 0.08}]
    assert rule(rows, 0.20) == reference(rows, 0.20) == "w:b"
    session = competition(tmp_path, [0.12, 0.08, 0.15])
    result = session.commit("w", verify=lambda work, value: True, abstain_loss=0.20, rule=rule)
    assert (result["decision"], result["call_id"]) == ("publish", "w:b")


def test_a_commitment_rule_abstains_when_every_candidate_is_worse_than_abstaining(tmp_path):
    session = competition(tmp_path, [0.40, 0.55, 0.60])
    plane = runtime_policies.RuntimePolicies(commitment=runtime_policies.OptimalStoppingCommitment(
        latency_cost=0.01, deadline=1, arrival_prob=0.0, loss_support=[0.5], loss_probs=[1.0]))
    result = session.commit("w", verify=lambda work, value: True, abstain_loss=0.20,
                            rule=plane.commitment_rule(0.20))
    assert result["decision"] == "abstain"
    assert session.snapshot()["artifacts"] == []


def test_cross_inhibition_commitment_selects_a_winner_and_deadlocks_into_abstention(tmp_path):
    plane = runtime_policies.RuntimePolicies(commitment=runtime_policies.CrossInhibitionCommitment(
        latency_cost=0.01, decision_time=1.0))
    clear = competition(tmp_path, [0.40, 0.02, 0.45])
    result = clear.commit("w", verify=lambda work, value: True, abstain_loss=1.0,
                          rule=plane.commitment_rule(1.0))
    assert (result["decision"], result["call_id"]) == ("publish", "w:b")
    nested = tmp_path / "tied"
    nested.mkdir()
    tied = competition(nested, [0.90, 0.90, 0.90])
    deadlocked = tied.commit("w", verify=lambda work, value: True, abstain_loss=1.0,
                             rule=plane.commitment_rule(1.0))
    assert deadlocked["decision"] == "abstain" and tied.snapshot()["artifacts"] == []


# ---------------------------------------------------------------- the hard boundary


@pytest.mark.parametrize("commitment", [
    None,
    runtime_policies.CrossInhibitionCommitment(latency_cost=0.01, decision_time=1.0),
    runtime_policies.OptimalStoppingCommitment(latency_cost=0.01, deadline=1, arrival_prob=0.0,
                                               loss_support=[0.5], loss_probs=[1.0]),
])
def test_no_commitment_policy_can_turn_a_failing_checker_into_acceptance(tmp_path, commitment):
    """Host acceptance is a truth condition; commitment arbitrates candidates, not truth."""
    failing = json.loads(json.dumps(script_of()))
    failing["responses"][1]["response"]["content"][0]["input"]["total_cents"] = 1
    session, engine = engine_for(tmp_path, spec_of(), anthropic.validate_script(failing),
                                 policies=runtime_policies.RuntimePolicies(commitment=commitment))
    assert engine.run()["status"] == "rejected"
    result = artifact_of(session, "finalize")
    assert result["accepted"] is False and result["checker"]["result"]["pass"] is False
    assert session.snapshot()["platform"]["candidates"] == []


def test_host_acceptance_never_reaches_for_candidate_arbitration(tmp_path):
    session, engine = engine_for(tmp_path, spec_of())
    assert engine.run()["status"] == "success"
    snapshot = session.snapshot()
    assert snapshot["platform"]["candidates"] == []
    assert snapshot["platform"]["decisions"] == []
    assert [row["kind"] for row in session.artifact_records()] == ["output", "output", "result"]
    assert artifact_of(session, "finalize")["accepted"] is True
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"
