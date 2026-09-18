"""The colony policy plane: the runtime's only door to the colony mechanisms.

An adapter, not a reimplementation. Every decision here delegates to code that
already exists — ``runner.policies`` for allocation, ``pheroos_interaction.leases``
for the lease TTL, ``pheroos_interaction.commitment`` for candidate commitment — so
a baseline arm and a colony arm differ in the policy object alone, with model,
tools, context, budgets, task graph, provider and artifact semantics held constant.

    allocation (L2)   FIFOAllocation   ThresholdAllocation / ResponseThresholdAllocation
    lease      (L3)   FixedLease       EvaporationLease
    commitment (L1)   MinLossCommitment  OptimalStoppingCommitment / CrossInhibitionCommitment

Allocation and lease are active in the runtime. Commitment is a defined capability
that the runtime does not call: the current orchestration model gives each task one
agent and one candidate, so there is no arbitration locus for it. It is validated
directly against a platform session with genuine competing candidates, and it enters
the runtime only when such a locus exists.

Every policy is pure: it reads no ledger, performs no I/O, takes no clock reading
and holds no state between calls. Its inputs are declared in the frozen workflow
spec, so they are part of the run's identity and a replay cannot drift. None of
these is claimed to be optimal.
"""

from hashlib import sha256

from pheroos_interaction import commitment, leases
from . import policies
from .contracts import ContractError
from .session import _wire

DEFAULT_LEASE_SECONDS = 60


# ---------------------------------------------------------------- L2 allocation

class FIFOAllocation:
    """Claim the head of the enumerated ready queue; the baseline arm."""

    name = "fifo"

    def select(self, ready, context):
        return policies.pick_fifo(ready)


class ThresholdAllocation:
    """Claim only when the declared backlog delay outweighs the worker's extra cost.

    Only PRIMITIVE facts are declared: each worker's cost, one shared service time
    and one latency cost. ``cheapest_cost`` and ``cheaper_workers`` are DERIVED here,
    per candidate task, from that frozen model and THAT TASK'S eligible set. A cost
    spread among workers who cannot legally execute the task in hand counts for
    nothing: if agent A is the only eligible executor, a cheaper agent B is not
    cheaper capacity for it, and A claims.

    The decision object is the PAIR (agent, work), not work alone. The same task can
    sit in two workers' ready queues at once, so each candidate row is weighed on its
    own eligibility rather than on the queue head's. Nothing is inferred from run
    state: not who is idle, not who is online, not who claimed last.
    """

    name = "threshold"

    def __init__(self, capacity):
        self.capacity = capacity

    def _arguments(self, eligible, actor):
        workers = self.capacity["workers"]
        names = [name for name in eligible if name in workers]
        if actor not in workers or not names:
            raise ContractError("the declared capacity model omits an eligible agent")
        mine, costs = workers[actor]["cost"], [workers[name]["cost"] for name in names]
        return {"worker_cost": mine, "cheapest_cost": min(costs),
                "cheaper_workers": sum(cost < mine for cost in costs),
                "latency_cost": self.capacity["latency_cost"],
                "service_time": self.capacity["service_time"]}

    def _scan(self, ready, context, pick):
        """Offer each ready row in queue order; the first the mechanism claims wins.

        The backlog stays the agent's whole ready queue, so rotating the candidate to
        the head changes which task is under consideration without inflating or
        shrinking the pressure the mechanism reads.
        """
        for index, row in enumerate(ready):
            queue = [row] + [other for position, other in enumerate(ready) if position != index]
            chosen = pick(queue, self._arguments(row["eligible"], context["agent"]), row)
            if chosen is not None:
                return chosen
        return None

    def select(self, ready, context):
        return self._scan(ready, context,
                          lambda queue, arguments, row: policies.pick_threshold(queue, **arguments))


class ResponseThresholdAllocation(ThresholdAllocation):
    """The graded Hill response around the same threshold.

    ``pick_response`` requires a declared, replayable draw. It is derived from the
    frozen seed and spec digest, the acting agent, the candidate task and the
    ledger's own call count -- every one of them durable and identical on a resume or
    a replay of the same decision point. Nothing is drawn at random inside the
    runtime, and the draw is keyed to the (agent, work) pair because that pair, not
    the work alone, is what the policy decides.
    """

    name = "response"

    def __init__(self, capacity, exponent, seed="allocation"):
        super().__init__(capacity)
        self.exponent, self.seed = exponent, seed

    def draw(self, context, work_id):
        key = _wire([self.seed, context["spec_digest"], context["agent"], work_id,
                     context["ledger_index"]])
        return int(sha256(key.encode()).hexdigest(), 16) / 2 ** 256

    def select(self, ready, context):
        return self._scan(ready, context, lambda queue, arguments, row: policies.pick_response(
            queue, exponent=self.exponent, draw=self.draw(context, row["id"]), **arguments))


# ---------------------------------------------------------------- L3 lease

class FixedLease:
    """The incumbent constant lease; the baseline arm."""

    name = "fixed"

    def __init__(self, seconds=DEFAULT_LEASE_SECONDS):
        self.seconds = seconds

    def duration(self, task_kind=None, agent=None):
        return self.seconds


class EvaporationLease:
    """The TTL minimizing (1-F(T))*C_dup + T*p_fail*c_t over the declared support.

    Under the ledger's never-retry rule the declared stage durations must be
    claim-to-dispatch lead times, not full model response times: the TTL bounds no
    stall time and cannot resolve a call that was already dispatched. The sample is
    declared in the frozen spec and never read from live history, so the same
    workflow yields the same TTL on every resume and replay.
    """

    name = "evaporation"

    def __init__(self, stage_durations, p_fail, per_tick_cost, false_expiry_cost):
        self.chosen = leases.lease_ttl(stage_durations, p_fail, per_tick_cost, false_expiry_cost,
                                       candidates=(DEFAULT_LEASE_SECONDS,))

    def duration(self, task_kind=None, agent=None):
        return self.chosen["ttl"]


# ---------------------------------------------------------------- L1 commitment

class MinLossCommitment:
    """Defer to the platform's own rule: the least declared loss, strictly below abstention."""

    name = "min_loss"

    def rule(self, abstain_loss):
        return None


class OptimalStoppingCommitment:
    """Optimal stopping with recall over competing candidates: publish, wait, or abstain.

    Optimal only under its declared arrival model, which is a caller assumption and
    not calibrated here.
    """

    name = "optimal_stopping"

    def __init__(self, latency_cost, deadline, arrival_prob, loss_support, loss_probs, elapsed=0):
        self.arguments = (latency_cost, deadline, arrival_prob, loss_support, loss_probs, elapsed)

    def rule(self, abstain_loss):
        latency, deadline, arrival, support, probs, elapsed = self.arguments
        return commitment.optimal_stopping_rule(abstain_loss, latency, deadline, arrival,
                                                support, probs, elapsed)


class CrossInhibitionCommitment:
    """The cross-inhibition ODE as a deterministic zero-byte filter over candidate metadata.

    A deadlock is a terminal abstention. Bounded work, no messages, no claim that the
    outcome is optimal or that any declared loss is true.
    """

    name = "cross_inhibition"

    def __init__(self, latency_cost, decision_time, quorum_frac=.45, margin=.05, seed="colony"):
        self.arguments = (latency_cost, decision_time, quorum_frac, margin, seed)

    def rule(self, abstain_loss):
        latency, decision_time, quorum, margin, seed = self.arguments
        return commitment.cross_inhibition_rule(commitment.CommitmentConfig(
            abstain_loss=abstain_loss, latency_cost=latency, decision_time=decision_time,
            quorum_frac=quorum, margin=margin, seed=seed))


# ---------------------------------------------------------------- the plane

ALLOCATIONS = {"fifo": FIFOAllocation, "threshold": ThresholdAllocation,
               "response": ResponseThresholdAllocation}
LEASES = {"fixed": FixedLease, "evaporation": EvaporationLease}
COMMITMENTS = {"min_loss": MinLossCommitment, "optimal_stopping": OptimalStoppingCommitment,
               "cross_inhibition": CrossInhibitionCommitment}


class RuntimePolicies:
    """Runtime allocation and lease policies, plus an available platform commitment adapter.

    The runtime asks for TWO decisions, not three: which ready work to claim and how
    long its lease runs. Commitment is a capability of the platform's own commit
    transition that this plane can supply a rule for; the runtime never reaches for
    it, so ``describe`` reports it apart from what actually ran.
    """

    def __init__(self, allocation=None, lease=None, commitment=None):
        self.allocation = allocation or FIFOAllocation()
        self.lease = lease or FixedLease()
        self.commitment = commitment or MinLossCommitment()

    @classmethod
    def from_spec(cls, spec):
        """Build the plane from the workflow's declared ``policies`` block, or the baseline."""
        declared = spec.get("policies") or {}
        slots = {}
        for slot, registry in (("allocation", ALLOCATIONS), ("lease", LEASES)):
            config = declared.get(slot)
            if config is None:
                continue
            options = {key: value for key, value in config.items() if key != "kind"}
            if config["kind"] in ("threshold", "response"):
                options["capacity"] = spec["capacity"]
            slots[slot] = registry[config["kind"]](**options)
        return cls(**slots)

    def describe(self, commitment_decisions=None):
        """What actually ran, kept apart from what was merely available.

        Reporting the commitment arm beside the allocation and lease arms would imply
        L1 was exercised. It is not: the runtime has no entry point for it. The arms
        that did run are also declared in the frozen spec, so they are part of the
        run's identity. ``commitment_decisions`` is the number of arbitration
        decisions the ledger actually recorded, which is zero while no arbitration
        locus exists.
        """
        capability = {"name": self.commitment.name}
        if commitment_decisions is not None:
            capability["active_decisions"] = commitment_decisions
        return {"runtime_policies": {"allocation": self.allocation.name,
                                     "lease": self.lease.name},
                "platform_capabilities": {"commitment": capability}}

    def select_work(self, ready, context):
        """Which ready work this agent claims now, or None to defer to cheaper capacity."""
        chosen = self.allocation.select(ready, context)
        if chosen is not None and chosen not in {row["id"] for row in ready}:
            raise ContractError("the allocation policy chose work outside the ready queue")
        return chosen

    def select_host_work(self, ready):
        """Ready order for the host finalizer.

        The host is a reserved identity with no model configuration, not a worker: it
        has no price, no cheaper alternatives and no response threshold. Inventing a
        cost for it just to reuse the worker interface would fabricate an economic
        parameter that does not exist, so this is a deliberate domain distinction.
        """
        return policies.pick_fifo(ready)

    def lease_duration(self, task_kind=None, agent=None):
        return self.lease.duration(task_kind, agent)

    def commitment_rule(self, abstain_loss):
        """The rule for ``PlatformSession.commit``: candidate arbitration only.

        Defined but not reached by the runtime: orchestration gives each task one
        agent and ``max_candidates`` of one, so no arbitration locus exists. It
        chooses among admissible candidates and never decides whether one is correct;
        a deterministic checker's verdict is not something it may overturn.
        """
        return self.commitment.rule(abstain_loss)
