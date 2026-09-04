from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any

from .codec import encode


ROUTE_COUNT = 64
VISIBLE_WIDTH = 16
FAILURE_START = 330
FAILURE_STEPS = 30
RESOURCE_FAULT_START = 300
RESOURCE_FAULT_STEPS = 30
RESOURCE_FAULT_FRACTION = 0.25


@dataclass
class Communication:
    messages: int = 0
    bytes: int = 0
    reads: int = 0
    writes: int = 0
    failed_writes: int = 0

    def send(self, event: dict[str, Any], *, read: bool = False, write: bool = False, failed: bool = False) -> None:
        self.messages += 1
        self.bytes += len(encode(event))
        self.reads += int(read)
        self.writes += int(write)
        self.failed_writes += int(failed)


@dataclass(frozen=True)
class Agent:
    agent_id: int
    origin: int
    visible_routes: tuple[int, ...]


@dataclass
class RouteEnvironment:
    seed: int
    route_count: int = ROUTE_COUNT
    graph_nodes: int = 300
    base_costs: list[float] = field(default_factory=list)
    agents: tuple[Agent, ...] = ()
    shock_route: int = 0

    def __post_init__(self) -> None:
        rng = random.Random(self.seed ^ 0xA17C_4B29)
        costs = [0.78 + rng.random() * 0.65 for _ in range(self.route_count)]
        # A known but non-trivial first optimum makes the shock and recovery
        # observable without introducing a hidden answer into any controller.
        costs[0] = 0.52
        costs[1] = 0.61
        costs[2] = 0.67
        self.base_costs = costs

    def with_agents(self, count: int) -> RouteEnvironment:
        agents = []
        for agent_id in range(count):
            origin = (agent_id * self.route_count) // max(1, count)
            visible = tuple(
                sorted({(origin + offset) % self.route_count for offset in range(-VISIBLE_WIDTH // 2, VISIBLE_WIDTH // 2)})
            )
            agents.append(Agent(agent_id, origin, visible))
        return RouteEnvironment(
            seed=self.seed,
            route_count=self.route_count,
            graph_nodes=self.graph_nodes,
            base_costs=list(self.base_costs),
            agents=tuple(agents),
            shock_route=self.shock_route,
        )

    def active_base_cost(self, route: int, step: int) -> float:
        value = self.base_costs[route]
        if step >= 250 and route == self.shock_route:
            return 2.20
        return value

    def optimal_route(self, step: int) -> int:
        return min(range(self.route_count), key=lambda route: (self.active_base_cost(route, step), route))

    def optimal_cost(self, step: int) -> float:
        return self.active_base_cost(self.optimal_route(step), step)

    def local_optimal_route(self, agent: Agent, step: int) -> int:
        return min(
            agent.visible_routes,
            key=lambda route: (self.active_base_cost(route, step), route),
        )

    def observe(self, agent_id: int, route: int, step: int) -> float:
        rng = random.Random(
            self.seed * 1_000_003 + step * 10_007 + agent_id * 101 + route * 17
        )
        noise = (rng.random() - 0.5) * 0.06
        return max(0.05, self.active_base_cost(route, step) + noise)


@dataclass
class RunResult:
    arm: str
    density: float
    seed: int
    agent_count: int
    final_regret: float
    shock_recovery_steps: int | None
    spof_recovery_steps: int | None
    messages: int
    bytes: int
    reads: int
    writes: int
    failed_writes: int
    final_best_share: float
    spof_fault: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "density": self.density,
            "seed": self.seed,
            "agent_count": self.agent_count,
            "final_regret": round(self.final_regret, 8),
            "shock_recovery_steps": self.shock_recovery_steps,
            "spof_recovery_steps": self.spof_recovery_steps,
            "messages": self.messages,
            "bytes": self.bytes,
            "reads": self.reads,
            "writes": self.writes,
            "failed_writes": self.failed_writes,
            "final_best_share": round(self.final_best_share, 8),
            "spof_fault": self.spof_fault,
        }


def _event(*, kind: str, step: int, agent: int, route: int | None = None, cost: float | None = None, value: Any = None, target: int | None = None) -> dict[str, Any]:
    # Every arm serializes the same field set. Nulls are intentional: they
    # prevent a controller from winning through a bespoke compact wire shape.
    return {
        "agent": agent,
        "cost": None if cost is None else round(cost, 6),
        "kind": kind,
        "route": route,
        "step": step,
        "target": target,
        "value": (
            None
            if value is None
            else round(value, 6)
            if isinstance(value, (float, int))
            else value
        ),
    }


def _wire_value(route: int, value: float | None) -> list[list[float | int | None]]:
    """Use the same route/value list granularity for every wire event."""
    return [[route, None if value is None else round(value, 6)]]


class Controller:
    def __init__(self, arm: str, env: RouteEnvironment) -> None:
        self.arm = arm
        self.env = env
        self.rng = random.Random(env.seed ^ 0xD15EA5E)
        self.known: dict[int, dict[int, float]] = {a.agent_id: {} for a in env.agents}
        self.global_estimates: dict[int, float] = {}
        self.ephemeral: dict[int, float] = {}
        self.field: dict[int, dict[int, tuple[float, int]]] = {i: {} for i in range(4)}
        self.communication = Communication()
        self.best_route_history: list[int] = []
        self.regret_history: list[float] = []
        self.spof_fault = {
            "centralized_online": "coordinator",
            "field_local": "field_shard_0",
            "random_local": "agent_quarter",
            "greedy_local": "agent_quarter",
            "stateless_local_aggregate": "agent_quarter",
        }[arm]

    def _faulty_agent(self, agent: Agent, step: int) -> bool:
        resource_window = RESOURCE_FAULT_START <= step < RESOURCE_FAULT_START + RESOURCE_FAULT_STEPS
        local_spof_window = (
            self.spof_fault == "agent_quarter"
            and FAILURE_START <= step < FAILURE_START + FAILURE_STEPS
        )
        if not (resource_window or local_spof_window):
            return False
        cutoff = max(1, math.ceil(len(self.env.agents) * RESOURCE_FAULT_FRACTION))
        return agent.agent_id < cutoff

    def _coordinator_up(self, step: int) -> bool:
        return not FAILURE_START <= step < FAILURE_START + FAILURE_STEPS

    def _field_shard_up(self, shard: int, step: int) -> bool:
        if self.arm != "field_local":
            return True
        return not (shard == 0 and FAILURE_START <= step < FAILURE_START + FAILURE_STEPS)

    def _lazy_field_value(self, shard: int, route: int, step: int) -> float:
        prior = self.field[shard].get(route)
        if prior is None:
            return 0.0
        strength, updated = prior
        if not self._field_shard_up(shard, step):
            return 0.0
        return strength * (0.88 ** max(0, step - updated))

    def choose(self, agent: Agent, step: int) -> int:
        visible = agent.visible_routes
        known = self.known[agent.agent_id]
        if self.arm == "random_local":
            return visible[self.rng.randrange(len(visible))]

        if self.arm == "centralized_online" and self._coordinator_up(step):
            candidates = [(self.global_estimates.get(route, 1.0), route) for route in visible]
            route = min(candidates)[1]
            self.communication.send(
                _event(kind="command", step=step, agent=-1, value=_wire_value(route, None), target=agent.agent_id)
            )
            return route

        if self.arm == "stateless_local_aggregate":
            candidates = []
            for route in visible:
                values = [known.get(route), self.ephemeral.get(route)]
                values = [value for value in values if value is not None]
                candidates.append((fmean(values) if values else 1.0, route))
            route = min(candidates)[1]
            self.communication.send(
                _event(
                    kind="aggregate_read",
                    step=step,
                    agent=agent.agent_id,
                    value=[[route, self.ephemeral.get(route)] for route in visible],
                ),
                read=True,
            )
            return route

        if self.arm == "field_local":
            candidates = []
            sensed: list[list[float]] = []
            for route in visible:
                shard = route % 4
                field_value = self._lazy_field_value(shard, route, step)
                sensed.append([route, field_value])
                estimate = known.get(route, 1.0)
                # Pheromone is an attention multiplier, not a replacement for
                # the observed route cost. This lets a post-shock local report
                # overcome stale positive memory while still rewarding paths
                # that many independent agents have found useful.
                candidates.append((estimate / (1.0 + 0.35 * field_value), route))
            self.communication.send(
                _event(kind="field_read", step=step, agent=agent.agent_id, value=sensed),
                read=True,
            )
            return min(candidates)[1]

        route = min(((known.get(route, 1.0), route) for route in visible))[1]
        return route

    def observe(self, agent: Agent, route: int, cost: float, step: int) -> None:
        self.known[agent.agent_id][route] = cost
        if self.arm == "centralized_online" and self._coordinator_up(step):
            self.communication.send(
                _event(
                    kind="observation",
                    step=step,
                    agent=agent.agent_id,
                    cost=cost,
                    value=_wire_value(route, cost),
                ),
                read=False,
            )
            prior = self.global_estimates.get(route)
            self.global_estimates[route] = cost if prior is None else (prior * 0.7 + cost * 0.3)
        elif self.arm == "stateless_local_aggregate":
            self.communication.send(
                _event(
                    kind="local_observation",
                    step=step,
                    agent=agent.agent_id,
                    cost=cost,
                    value=_wire_value(route, cost),
                )
            )
            # The map is rebuilt after the turn; it is not replay or persistent
            # memory. Every local agent filters it by visibility at read time.
        elif self.arm == "field_local":
            shard = route % 4
            value = max(0.05, min(4.0, 1.0 / cost))
            failed = not self._field_shard_up(shard, step)
            self.communication.send(
                _event(
                    kind="field_write",
                    step=step,
                    agent=agent.agent_id,
                    cost=cost,
                    value=_wire_value(route, value),
                ),
                write=True,
                failed=failed,
            )
            if not failed:
                prior = self._lazy_field_value(shard, route, step)
                self.field[shard][route] = (min(4.0, prior + value), step)

    def run(self, steps: int) -> tuple[list[float], list[int]]:
        for step in range(steps):
            chosen: list[tuple[Agent, int]] = []
            current_observations: dict[int, list[tuple[int, float]]] = {}
            for agent in self.env.agents:
                if self._faulty_agent(agent, step):
                    continue
                route = self.choose(agent, step)
                cost = self.env.observe(agent.agent_id, route, step)
                chosen.append((agent, route))
                current_observations.setdefault(agent.agent_id, []).append((route, cost))
                self.observe(agent, route, cost, step)
            # For the stateless local arm, only the previous turn's reports are
            # visible. The controller stores no durable aggregate between turns.
            if self.arm == "stateless_local_aggregate":
                self.ephemeral = {
                    route: fmean(cost for values in current_observations.values() for observed_route, cost in values if observed_route == route)
                    for route in {route for values in current_observations.values() for route, _ in values}
                }
            if chosen:
                regret = fmean(
                    self.env.active_base_cost(route, step)
                    / self.env.active_base_cost(self.env.local_optimal_route(agent, step), step)
                    - 1.0
                    for agent, route in chosen
                )
                self.regret_history.append(max(0.0, regret))
                self.best_route_history.append(
                    sum(route == self.env.local_optimal_route(agent, step) for agent, route in chosen)
                    / len(chosen)
                )
        return self.regret_history, self.best_route_history


def _first_stable_step(values: list[float], *, threshold: float, start: int, window: int = 20) -> int | None:
    for index in range(max(start, 0), len(values) - window + 1):
        if all(value <= threshold for value in values[index : index + window]):
            return index
    return None


def _first_share_step(values: list[float], *, threshold: float, start: int, window: int = 20) -> int | None:
    for index in range(max(start, 0), len(values) - window + 1):
        if all(value >= threshold for value in values[index : index + window]):
            return index
    return None


def run_once(*, arm: str, density: float, seed: int, steps: int = 500, graph_nodes: int = 300) -> RunResult:
    count = max(1, round(density * graph_nodes))
    env = RouteEnvironment(seed).with_agents(count)
    controller = Controller(arm, env)
    regrets, shares = controller.run(steps)
    final_regret = fmean(regrets[-50:]) if regrets else 1.0
    shock_step = _first_share_step(shares, threshold=0.90, start=250)
    spof_recovery = _first_stable_step(regrets, threshold=0.15, start=FAILURE_START + FAILURE_STEPS)
    return RunResult(
        arm=arm,
        density=density,
        seed=seed,
        agent_count=count,
        final_regret=final_regret,
        shock_recovery_steps=None if shock_step is None else shock_step - 250,
        spof_recovery_steps=None if spof_recovery is None else spof_recovery - (FAILURE_START + FAILURE_STEPS),
        messages=controller.communication.messages,
        bytes=controller.communication.bytes,
        reads=controller.communication.reads,
        writes=controller.communication.writes,
        failed_writes=controller.communication.failed_writes,
        final_best_share=fmean(shares[-50:]) if shares else 0.0,
        spof_fault=controller.spof_fault,
    )
