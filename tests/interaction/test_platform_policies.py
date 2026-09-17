"""Boundary and ordering checks for metadata-only claim policies."""

import copy
from fractions import Fraction
import math

import pytest

from pheroos_interaction.runner import policies


def queue():
    return [{"id": "first", "age": 3, "depth": 0},
            {"id": "second", "age": 9, "depth": 0}]


def threshold(ready, **overrides):
    options = dict(worker_cost=6, cheapest_cost=1, latency_cost=1,
                   service_time=4, cheaper_workers=2)
    return policies.pick_threshold(ready, **(options | overrides))


def test_fifo_preserves_supplied_queue_order_and_input():
    ready = queue()
    original = copy.deepcopy(ready)
    assert policies.pick_fifo(ready) == "first"
    assert policies.pick_fifo([]) is None
    assert ready == original


def test_depth_prefers_oldest_at_depth_then_queue_order():
    ready = queue() + [{"id": "deep-new", "age": 1, "depth": 1},
                       {"id": "deep-old", "age": 7, "depth": 1},
                       {"id": "deep-tie", "age": 7, "depth": 1}]
    assert policies.pick_by_depth(ready) == "deep-old"
    assert policies.pick_by_depth(queue()) == "second"
    assert policies.pick_by_depth([]) is None


@pytest.mark.parametrize("cost", [0, 1, 1e308])
@pytest.mark.parametrize("workers", [0, 3])
def test_homogeneous_costs_are_exactly_fifo(cost, workers):
    ready = queue()
    assert threshold(ready, worker_cost=cost, cheapest_cost=cost,
                     latency_cost=0, cheaper_workers=workers) == policies.pick_fifo(ready)


def test_threshold_strict_boundary_backlog_and_no_cheaper_capacity():
    assert threshold(queue()) is None                  # delay value 4 < extra 5
    assert threshold(queue() * 2) == "first"         # delay value 8 > extra 5
    assert threshold(queue(), worker_cost=5) is None   # equality waits
    assert threshold(queue(), cheaper_workers=0, latency_cost=0) == "first"
    assert threshold([], cheaper_workers=0) is None


def test_threshold_does_not_overflow_multiply_or_lose_tiny_extra_cost():
    assert threshold(queue(), worker_cost=1e308, cheapest_cost=0,
                     latency_cost=1e308, service_time=1e308) == "first"
    small = math.nextafter(0.0, 1.0)
    assert threshold(queue(), worker_cost=small, cheapest_cost=0,
                     latency_cost=small, service_time=0.5, cheaper_workers=1) is None


@pytest.mark.parametrize("name", ["worker_cost", "cheapest_cost", "latency_cost", "service_time"])
@pytest.mark.parametrize("value", [-1, float("inf"), -float("inf"), float("nan"), True, "1", None])
def test_invalid_numeric_inputs_rejected_even_for_empty_queue(name, value):
    with pytest.raises(ValueError):
        threshold([], **{name: value})


@pytest.mark.parametrize("value", [-1, True, 1.0, float("nan"), "1"])
def test_cheaper_worker_count_is_an_exact_nonnegative_integer(value):
    with pytest.raises(ValueError):
        threshold(queue(), cheaper_workers=value)


def test_service_time_must_be_positive_and_cheapest_cost_consistent():
    with pytest.raises(ValueError):
        threshold(queue(), service_time=0)
    with pytest.raises(ValueError):
        threshold(queue(), worker_cost=0)


@pytest.mark.parametrize("field,value", [("age", -1), ("age", float("nan")),
                                         ("depth", -1), ("depth", 0.5), ("depth", True)])
def test_invalid_depth_metadata_rejected(field, value):
    ready = queue()
    ready[0][field] = value
    with pytest.raises(ValueError):
        policies.pick_by_depth(ready)


SMALL = math.nextafter(0.0, 1.0)
STEP_FIXTURES = [
    (queue(), {}), (queue() * 2, {}), (queue(), {"worker_cost": 5}),
    (queue(), {"cheaper_workers": 0, "latency_cost": 0}), ([], {"cheaper_workers": 0}),
    (queue(), dict(worker_cost=1e308, cheapest_cost=0, latency_cost=1e308, service_time=1e308)),
    (queue(), dict(worker_cost=SMALL, cheapest_cost=0, latency_cost=SMALL,
                   service_time=0.5, cheaper_workers=1)),
] + [(queue(), dict(worker_cost=cost, cheapest_cost=cost, latency_cost=0, cheaper_workers=workers))
     for cost in (0, 1, 1e308) for workers in (0, 3)]


def response(ready, **overrides):
    options = dict(worker_cost=6, cheapest_cost=1, latency_cost=1,
                   service_time=4, cheaper_workers=2)
    return policies.pick_response(ready, **(options | overrides))


def hill(ready, exponent=8, **overrides):
    """The documented response probability, recomputed in exact rationals."""
    options = dict(worker_cost=6, cheapest_cost=1, latency_cost=1,
                   service_time=4, cheaper_workers=2) | overrides
    stimulus = Fraction(len(ready)) * Fraction(options["service_time"]) / options["cheaper_workers"]
    theta = (Fraction(options["worker_cost"]) - Fraction(options["cheapest_cost"])) \
        / Fraction(options["latency_cost"])
    return stimulus ** exponent / (stimulus ** exponent + theta ** exponent)


@pytest.mark.parametrize("ready,overrides", STEP_FIXTURES)
def test_step_response_is_exactly_the_threshold_rule(ready, overrides):
    original = copy.deepcopy(ready)
    expected = threshold(ready, **overrides)
    assert response(ready, **overrides) == expected
    assert response(ready, exponent=None, draw=0.5, **overrides) == expected
    assert ready == original


def test_graded_response_claims_iff_draw_is_below_the_hill_probability():
    ready = queue()                                   # s = 4, theta = 5
    p = hill(ready)
    assert p == Fraction(4 ** 8, 4 ** 8 + 5 ** 8)
    assert threshold(ready) is None                   # the step waits below break-even
    assert response(ready, exponent=8, draw=0) == "first"
    assert response([], exponent=8, draw=0) is None   # s = 0 -> p = 0
    below, above = math.nextafter(float(p), 0.0), math.nextafter(float(p), 1.0)
    assert Fraction(below) < p < Fraction(above)
    assert response(ready, exponent=8, draw=below) == "first"
    assert response(ready, exponent=8, draw=above) is None
    longer = queue() * 3                              # s = 12 > theta: p > 1/2 but still < 1
    assert Fraction(1, 2) < hill(longer) < 1
    assert response(longer, exponent=8, draw=math.nextafter(float(hill(longer)), 1.0)) is None
    assert response(longer, exponent=8, draw=0.5) == "first"


def test_graded_response_boundary_is_exact_at_the_break_even_delay():
    ready = queue()                                   # service_time 5 -> s = 5 = theta -> p = 1/2
    assert hill(ready, service_time=5) == Fraction(1, 2)
    assert threshold(ready, service_time=5) is None   # equality waits under the step
    for exponent in (1, 2, 8, policies.MAX_RESPONSE_EXPONENT):
        assert response(ready, service_time=5, exponent=exponent, draw=0.5) is None
        assert response(ready, service_time=5, exponent=exponent,
                        draw=math.nextafter(0.5, 0.0)) == "first"
        assert response(ready, service_time=5, exponent=exponent, draw=0) == "first"


def test_exponent_without_draw_rejected_even_for_an_empty_queue():
    with pytest.raises(ValueError):
        response(queue(), exponent=8)
    with pytest.raises(ValueError):
        response([], exponent=8)


@pytest.mark.parametrize("exponent", [0, -1, True, 2.0, 8.0, "8", float("nan"),
                                      policies.MAX_RESPONSE_EXPONENT + 1])
def test_exponent_must_be_an_exact_bounded_positive_integer(exponent):
    with pytest.raises(ValueError):
        response(queue(), exponent=exponent, draw=0.5)


@pytest.mark.parametrize("draw", [-1e-9, -1, 1, 1.0, math.nextafter(1.0, 2.0), float("nan"),
                                  float("inf"), -float("inf"), True, "0.5"])
def test_draw_outside_the_unit_interval_rejected_for_step_and_graded_response(draw):
    with pytest.raises(ValueError):
        response(queue(), exponent=8, draw=draw)
    with pytest.raises(ValueError):
        response(queue(), draw=draw)


@pytest.mark.parametrize("draw", [0, 0.5, math.nextafter(1.0, 0.0)])
@pytest.mark.parametrize("overrides", [dict(worker_cost=1, cheapest_cost=1),
                                       dict(worker_cost=1e308, cheapest_cost=1e308, latency_cost=0),
                                       dict(worker_cost=0, cheapest_cost=0, cheaper_workers=0),
                                       dict(cheaper_workers=0)])
def test_homogeneous_costs_or_no_cheaper_capacity_are_fifo_whatever_the_draw(draw, overrides):
    assert response(queue(), exponent=8, draw=draw, **overrides) == "first"
    assert response([], exponent=8, draw=draw, **overrides) is None


@pytest.mark.parametrize("draw", [0, math.nextafter(1.0, 0.0)])
def test_zero_latency_cost_with_extra_cost_never_claims_under_any_draw(draw):
    assert response(queue() * 4, latency_cost=0, exponent=8, draw=draw) is None


def test_graded_response_uses_exact_arithmetic_at_extreme_magnitudes():
    huge = dict(worker_cost=1e308, cheapest_cost=0, latency_cost=1e308, service_time=1e308)
    assert response(queue(), exponent=8, draw=math.nextafter(1.0, 0.0), **huge) == "first"
    tiny = dict(worker_cost=SMALL, cheapest_cost=0, latency_cost=SMALL, service_time=0.5,
                cheaper_workers=1)                    # theta = 1 = s: p is exactly one half
    assert hill(queue(), **tiny) == Fraction(1, 2)
    assert response(queue(), exponent=8, draw=0.5, **tiny) is None
    assert response(queue(), exponent=8, draw=0.49, **tiny) == "first"
