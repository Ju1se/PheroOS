from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .e2_codec import BYTES_PER_RECORD, encode_direction, encode_record


ROUTE_COUNT = 128
WINDOW_OFFSETS = np.arange(-7, 9, dtype=np.int64)
DEGREE = 4
M = 48
OPTIMUM_COST = 0.80
MIN_POSITION = int(-WINDOW_OFFSETS.min())
MAX_POSITION = int(ROUTE_COUNT - 1 - WINDOW_OFFSETS.max())


@dataclass
class Communication:
    messages: int = 0
    bytes: int = 0

    def send(self, sender: int, step: int, value: int) -> None:
        # Exercise the codec at the accounting boundary. The resulting bytes
        # are intentionally not retained: E2 measures wire volume, not a log.
        encode_record(sender, step, value)
        self.messages += 1
        self.bytes += BYTES_PER_RECORD


@dataclass(frozen=True)
class World:
    seed: int
    population: int
    informed_fraction: float
    r_star: int
    costs: np.ndarray
    positions: np.ndarray
    informed: np.ndarray
    neighbors: np.ndarray


@dataclass(frozen=True)
class RunResult:
    arm: str
    population: int
    informed_fraction: float
    informed_count: int
    seed: int
    r_star: int
    final_regret: float
    steps_to_first_r_star_adoption: int | None
    messages: int
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "N": self.population,
            "informed_fraction": self.informed_fraction,
            "informed_count": self.informed_count,
            "seed": self.seed,
            "r_star": self.r_star,
            "global_regret": round(self.final_regret, 10),
            "steps_to_first_r_star_adoption": self.steps_to_first_r_star_adoption,
            "messages": self.messages,
            "bytes": self.bytes,
        }


def _rng(seed: int, salt: int) -> np.random.Generator:
    return np.random.default_rng(np.uint64(seed) ^ np.uint64(salt))


def _connected(adjacency: list[list[int]]) -> bool:
    seen = {0}
    stack = [0]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return len(seen) == len(adjacency)


def random_4_regular(population: int, seed: int, degree: int = DEGREE) -> np.ndarray:
    """Build a deterministic simple connected random regular graph.

    The configuration model is retried with a deterministic seed sequence so
    self-loops, parallel edges, and disconnected draws are rejected rather
    than silently changing the topology. The returned rows are sorted, which
    makes all arm comparisons and serialized results reproducible.
    """

    if population <= degree or degree % 2 and population % 2:
        raise ValueError("population cannot realize the requested regular graph")
    for attempt in range(10_000):
        rng = _rng(seed + attempt, 0x4E1607)
        stubs = np.repeat(np.arange(population, dtype=np.int64), degree)
        rng.shuffle(stubs)
        edges: set[tuple[int, int]] = set()
        adjacency = [[] for _ in range(population)]
        valid = True
        for left, right in stubs.reshape(-1, 2):
            left_i, right_i = int(left), int(right)
            edge = (min(left_i, right_i), max(left_i, right_i))
            if left_i == right_i or edge in edges:
                valid = False
                break
            edges.add(edge)
            adjacency[left_i].append(right_i)
            adjacency[right_i].append(left_i)
        if valid and _connected(adjacency) and all(len(row) == degree for row in adjacency):
            return np.asarray([sorted(row) for row in adjacency], dtype=np.int64)
    raise RuntimeError("could not draw a simple connected 4-regular graph")


def initialize_world(population: int, informed_fraction: float, seed: int) -> World:
    if population <= 0 or not 0 < informed_fraction < 1:
        raise ValueError("population and informed fraction must be positive")
    rng = _rng(seed, 0xC0211A)
    r_star = int(rng.integers(16, 25))
    costs = rng.uniform(0.95, 1.05, size=ROUTE_COUNT).astype(np.float64)
    costs[r_star] = OPTIMUM_COST
    informed_count = int(round(population * informed_fraction))
    informed_count = max(1, min(population - 1, informed_count))
    positions = np.empty(population, dtype=np.int64)
    informed = np.zeros(population, dtype=bool)
    informed[:informed_count] = True
    informed_ranks = np.arange(informed_count, dtype=np.int64)
    positions[:informed_count] = r_star + 1 + informed_ranks % 7
    uninformed_count = population - informed_count
    uninformed_ranks = np.arange(uninformed_count, dtype=np.int64)
    positions[informed_count:] = r_star + 8 + (M * uninformed_ranks // uninformed_count)
    neighbors = random_4_regular(population, seed ^ 0x4E1607)
    world = World(seed, population, informed_fraction, r_star, costs, positions, informed, neighbors)
    assert_initial_invariants(world)
    return world


def visible_routes(positions: np.ndarray, route_count: int = ROUTE_COUNT) -> np.ndarray:
    routes = positions[:, None] + WINDOW_OFFSETS[None, :]
    if routes.min(initial=0) < 0 or routes.max(initial=0) >= route_count:
        raise RuntimeError("line window clipped; frozen geometry invariant violated")
    return routes


def local_best_routes(positions: np.ndarray, costs: np.ndarray) -> np.ndarray:
    routes = visible_routes(positions, len(costs))
    values = costs[routes] + routes * 1e-12
    return routes[np.arange(len(positions)), np.argmin(values, axis=1)]


def assert_initial_invariants(world: World) -> None:
    routes = visible_routes(world.positions, len(world.costs))
    if not np.all(world.positions > world.r_star):
        raise AssertionError("all initial positions must be to the right of r*")
    informed_visible = routes[world.informed]
    uninformed_visible = routes[~world.informed]
    if informed_visible.size and not np.all(np.any(informed_visible == world.r_star, axis=1)):
        raise AssertionError("every informed window must contain r*")
    if uninformed_visible.size and np.any(np.any(uninformed_visible == world.r_star, axis=1)):
        raise AssertionError("every uninformed window must exclude r*")
    if float(world.costs[world.r_star]) != OPTIMUM_COST:
        raise AssertionError("r* must have the frozen optimum cost")
    if np.any(np.delete(world.costs, world.r_star) <= OPTIMUM_COST):
        raise AssertionError("r* must be the unique optimum")


def _sign(target: np.ndarray, own: np.ndarray) -> np.ndarray:
    return np.sign(target - own).astype(np.int8)


def own_directions(world: World, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    best = local_best_routes(positions, world.costs)
    local_direction = _sign(best, positions)
    informed_direction = _sign(np.full(world.population, world.r_star, dtype=np.int64), positions)
    return np.where(world.informed, informed_direction, local_direction).astype(np.int8), best


def gossip_targets_from_snapshot(
    snapshot_best_routes: np.ndarray,
    neighbors: np.ndarray,
    neighbor_choices: np.ndarray,
) -> np.ndarray:
    """Return one neighbor's route using only the previous synchronous snapshot."""

    rows = np.arange(len(snapshot_best_routes), dtype=np.int64)
    selected_neighbor = neighbors[rows, neighbor_choices]
    return snapshot_best_routes[selected_neighbor].copy()


def _gossip_neighbor_choices(population: int, steps: int, seed: int) -> np.ndarray:
    return _rng(seed, 0x91551F).integers(0, DEGREE, size=(steps, population), dtype=np.int64)


def _count_neighbor_messages(communication: Communication, signals: np.ndarray, step: int, route_values: bool) -> None:
    for sender, signal in enumerate(signals):
        encoded = int(signal) if route_values else encode_direction(int(signal))
        # One directed message per edge endpoint. The same value is sent to
        # every neighbor; no implicit free broadcast is allowed.
        for _ in range(DEGREE):
            communication.send(sender, step, encoded)


def run_once(
    *,
    arm: str,
    population: int,
    informed_fraction: float,
    seed: int,
    steps: int = 500,
) -> RunResult:
    if arm not in {"oracle", "solitary", "naive_gossip", "couzin"}:
        raise ValueError(f"unsupported E2 arm: {arm}")
    world = initialize_world(population, informed_fraction, seed)
    positions = world.positions.copy()
    communication = Communication()
    regret_history: list[float] = []
    first_adoption: int | None = None
    choices = _gossip_neighbor_choices(population, steps, seed) if arm == "naive_gossip" else None

    for step in range(steps):
        snapshot_positions = positions.copy()
        if arm == "oracle":
            movement = _sign(np.full(population, world.r_star, dtype=np.int64), snapshot_positions)
        elif arm == "solitary":
            movement, _ = own_directions(world, snapshot_positions)
        else:
            own_direction, own_best = own_directions(world, snapshot_positions)
            if arm == "couzin":
                _count_neighbor_messages(communication, own_direction, step, route_values=False)
                neighbor_mean = own_direction[world.neighbors].mean(axis=1)
                omega = np.where(world.informed, 0.8, 0.2)
                combined = omega * own_direction + (1.0 - omega) * neighbor_mean
                movement = np.sign(combined).astype(np.int8)
            else:
                _count_neighbor_messages(communication, own_best, step, route_values=True)
                neighbor_best = gossip_targets_from_snapshot(own_best, world.neighbors, choices[step])
                target = np.where(world.costs[neighbor_best] < world.costs[own_best], neighbor_best, own_best)
                movement = _sign(target, snapshot_positions)

        positions = snapshot_positions + movement.astype(np.int64)
        # The route line has no wraparound. At an endpoint, movement outward
        # is absorbed rather than clipping the visible window. This makes the
        # no-clipping invariant explicit even for a long-lived local optimum.
        positions = np.clip(positions, MIN_POSITION, MAX_POSITION)
        chosen = local_best_routes(positions, world.costs)
        if first_adoption is None and np.any(chosen == world.r_star):
            first_adoption = step
        regret_history.append(float(np.mean(world.costs[chosen] - OPTIMUM_COST) / OPTIMUM_COST))

    final_regret = float(np.mean(np.asarray(regret_history[-50:], dtype=np.float64)))
    return RunResult(
        arm=arm,
        population=population,
        informed_fraction=informed_fraction,
        informed_count=int(np.count_nonzero(world.informed)),
        seed=seed,
        r_star=world.r_star,
        final_regret=final_regret,
        steps_to_first_r_star_adoption=first_adoption,
        messages=communication.messages,
        bytes=communication.bytes,
    )
