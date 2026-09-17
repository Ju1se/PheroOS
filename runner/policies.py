"""Deterministic claim choices using only ready-work metadata.

These policies have no durable state, read no work content, and perform no I/O.
The caller supplies queue order and the costs of its declared workload model.
"""

from fractions import Fraction
import math


def _nonnegative(value, name, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < 0 or (positive and value == 0):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a finite {requirement} number")
    return value


def pick_fifo(ready):
    """Choose the first item in the supplied creation-order queue."""
    return ready[0]["id"] if ready else None


def pick_by_depth(ready):
    """Choose deepest, then oldest; exact ties retain supplied queue order."""
    for item in ready:
        if type(item["depth"]) is not int or item["depth"] < 0:
            raise ValueError("depth must be an exact nonnegative integer")
        _nonnegative(item["age"], "age")
    return max(ready, key=lambda item: (item["depth"], item["age"]))["id"] if ready else None


def pick_threshold(ready, *, worker_cost, cheapest_cost, latency_cost,
                   service_time, cheaper_workers):
    """Claim FIFO when the declared backlog delay justifies extra worker cost.

    With cheaper capacity, claim iff ``latency_cost * backlog * service_time``
    is strictly greater than ``extra_cost * cheaper_workers``. At equality the
    expensive worker waits. Homogeneous costs reduce exactly to FIFO. With no
    cheaper workers there is no cheaper capacity to await, so claim FIFO too.

    This is a workload assumption, not an optimal scheduling guarantee. Exact
    arithmetic over the supplied numbers avoids overflow at the break-even test.
    """
    for name, value in (("worker_cost", worker_cost), ("cheapest_cost", cheapest_cost),
                        ("latency_cost", latency_cost)):
        _nonnegative(value, name)
    _nonnegative(service_time, "service_time", positive=True)
    if type(cheaper_workers) is not int or cheaper_workers < 0:
        raise ValueError("cheaper_workers must be an exact nonnegative integer")
    if worker_cost < cheapest_cost:
        raise ValueError("worker_cost cannot be below cheapest_cost")
    if not ready:
        return None
    if worker_cost == cheapest_cost or cheaper_workers == 0:
        return pick_fifo(ready)
    extra = Fraction(worker_cost) - Fraction(cheapest_cost)
    delay_cost = Fraction(latency_cost) * len(ready) * Fraction(service_time)
    return pick_fifo(ready) if delay_cost > extra * cheaper_workers else None


MAX_RESPONSE_EXPONENT = 64


def pick_response(ready, *, worker_cost, cheapest_cost, latency_cost,
                  service_time, cheaper_workers, exponent=None, draw=None):
    """Claim FIFO with a graded (Hill) response to the declared backlog.

    ``exponent=None`` is the deterministic step: the result is exactly that of
    ``pick_threshold``, which is called. An exact integer ``exponent`` in
    ``[1, MAX_RESPONSE_EXPONENT]`` claims iff ``draw < p`` where
    ``p = s**n / (s**n + theta**n)``, ``s = len(ready) * service_time /
    cheaper_workers`` is the time the cheaper capacity needs to drain the
    backlog and ``theta = (worker_cost - cheapest_cost) / latency_cost`` is the
    break-even delay of ``pick_threshold``. At ``s == theta`` the step waits
    while the graded response claims with probability one half.

    The caller supplies ``draw`` in ``[0, 1)`` as a declared, replayable number
    (a recorded uniform variate; nothing is drawn here), and an ``exponent``
    without a ``draw`` is rejected. Homogeneous costs or no cheaper workers
    reduce exactly to FIFO whatever the draw; ``latency_cost == 0`` with extra
    cost makes the break-even delay infinite and the response zero. The
    comparison is exact rational arithmetic on the supplied numbers, so large
    costs and tiny margins neither overflow nor round.

    This is a response-threshold heuristic from social-insect task allocation,
    not an optimal scheduler: no claim that any exponent lowers waiting cost
    on a given workload, and the deterministic step remains the default.
    """
    step = pick_threshold(ready, worker_cost=worker_cost, cheapest_cost=cheapest_cost,
                          latency_cost=latency_cost, service_time=service_time,
                          cheaper_workers=cheaper_workers)
    if exponent is not None and (type(exponent) is not int
                                 or not 1 <= exponent <= MAX_RESPONSE_EXPONENT):
        raise ValueError(f"exponent must be None or an exact integer in [1, {MAX_RESPONSE_EXPONENT}]")
    if draw is not None and _nonnegative(draw, "draw") >= 1:
        raise ValueError("draw must be a declared number in [0, 1)")
    if exponent is None:
        return step
    if draw is None:
        raise ValueError("a graded response needs a declared draw in [0, 1)")
    if not ready or worker_cost == cheapest_cost or cheaper_workers == 0:
        return step
    if latency_cost == 0:
        return None
    stimulus = Fraction(len(ready)) * Fraction(service_time) / cheaper_workers
    theta = (Fraction(worker_cost) - Fraction(cheapest_cost)) / Fraction(latency_cost)
    high, low = stimulus ** exponent, theta ** exponent
    return pick_fifo(ready) if Fraction(draw) * (high + low) < high else None
