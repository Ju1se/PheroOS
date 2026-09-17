"""Lease TTL search over a declared stage-duration sample; no clock, no ledger."""
from math import log
import random
import statistics

import pytest

from pheroos_interaction import leases

Z95 = 1.6448536269514722  # standard normal 95th percentile
MU, SIGMA = log(12), log(33/12)/Z95  # lognormal with median 12 and 95th percentile 33
SEED = 0


def seeded_sample(seed=SEED, size=200):
    """A fixed sample from one generator; the seed is the only source of variation."""
    rng = random.Random(seed)
    return tuple(rng.lognormvariate(MU, SIGMA) for _ in range(size))


SAMPLE = seeded_sample()
SORTED = sorted(SAMPLE)


def objective(sample, T, p_fail, per_tick_cost, false_expiry_cost):
    """The documented loss, recomputed independently of the module."""
    survival = sum(1 for d in sample if d > T) / len(sample)
    return survival * false_expiry_cost + T * p_fail * per_tick_cost


def test_seeded_sample_has_the_declared_shape():
    assert len(SAMPLE) == 200 and SAMPLE == seeded_sample() and SAMPLE != seeded_sample(1)
    assert len(set(SAMPLE)) == 200
    assert abs(statistics.median(SAMPLE)-12) < 1
    assert abs(SORTED[190]-33) < 1
    assert min(SAMPLE) > 0


def test_rare_holder_failure_never_expires_a_live_lease():
    result = leases.lease_ttl(SAMPLE, 1e-3, 1., 5., candidates=(60,))
    assert result['ttl'] == max(SAMPLE)
    assert result['expected_loss'] == max(SAMPLE)*1e-3*1.
    assert result['searched'] == sorted(set(SAMPLE) | {60})
    assert 60 in result['searched']
    assert result['candidate_losses'] == {60: 60*1e-3*1.}
    assert result['candidate_losses'][60] > result['expected_loss']  # the incumbent loses to the support max
    assert all(objective(SAMPLE, T, 1e-3, 1., 5.) >= result['expected_loss'] for T in result['searched'])


def test_frequent_holder_failure_expires_strictly_earlier():
    frequent = leases.lease_ttl(SAMPLE, .1, 1., 5., candidates=(60,))
    assert frequent['ttl'] < max(SAMPLE) and frequent['ttl'] in SAMPLE
    assert frequent['expected_loss'] == pytest.approx(objective(SAMPLE, frequent['ttl'], .1, 1., 5.))
    assert all(objective(SAMPLE, T, .1, 1., 5.) >= frequent['expected_loss'] for T in frequent['searched'])
    ttls = [leases.lease_ttl(SAMPLE, p_fail, 1., 5.)['ttl'] for p_fail in (1e-3, 1e-2, .1)]
    assert ttls[0] > ttls[1] > ttls[2]
    assert frequent['candidate_losses'][60] > frequent['expected_loss']


def test_incumbent_candidate_is_searched_and_wins_only_below_the_support():
    below = leases.lease_ttl([100], 1, 1, 1, candidates=[60])
    assert below == {'ttl': 60, 'expected_loss': 61., 'searched': [60, 100], 'candidate_losses': {60: 61.}}
    # Above the support a candidate only adds tick cost; with no tick cost it ties and the smaller T stays.
    tied = leases.lease_ttl([1., 2., 4., 8.], .2, 0., 3., candidates=(60,))
    assert tied['ttl'] == 8. and tied['expected_loss'] == 0. and tied['candidate_losses'] == {60: 0.}
    assert leases.lease_ttl([1., 2., 4., 8.], .2, .5, 3.)['ttl'] == 8.
    assert leases.lease_ttl(SAMPLE, .1, 1., 5.)['candidate_losses'] == {}


def test_duplicates_count_in_the_survival_function():
    result = leases.lease_ttl([1., 1., 2.], .2, .5, 3.)
    assert result['searched'] == [1., 2.]
    assert result['ttl'] == 2. and result['expected_loss'] == pytest.approx(.2)
    assert objective([1., 1., 2.], 1., .2, .5, 3.) == pytest.approx(1.1)


def test_heavier_tail_pushes_the_ttl_up_where_the_optimum_tracks_the_support_maximum():
    heavy = SORTED[:180] + [3*d for d in SORTED[180:]]  # stretch the top decile, same count
    base = leases.lease_ttl(SAMPLE, 1e-3, 1., 5.)
    stretched = leases.lease_ttl(heavy, 1e-3, 1., 5.)
    assert stretched['ttl'] > base['ttl'] == max(SAMPLE)
    assert stretched['ttl'] > max(SAMPLE) and stretched['ttl'] in heavy
    # The objective does not chase the tail unconditionally: at p_fail=.1 the argmin sits in the
    # unchanged lower support and the stretch leaves it where it was.
    assert leases.lease_ttl(heavy, .1, 1., 5.)['ttl'] == leases.lease_ttl(SAMPLE, .1, 1., 5.)['ttl']


def test_empty_sample_rejected_and_iterables_accepted():
    with pytest.raises(ValueError, match='at least one'):
        leases.lease_ttl([], .1, 1., 5.)
    with pytest.raises(ValueError, match='at least one'):
        leases.lease_ttl((), .1, 1., 5., candidates=(60,))
    assert leases.lease_ttl(iter([3., 4.]), .1, 1., 5.)['searched'] == [3., 4.]
    assert leases.lease_ttl({4., 3.}, .1, 1., 5.)['searched'] == [3., 4.]


@pytest.mark.parametrize('value', [True, False, float('nan'), float('inf'), -float('inf'), -1, '12', None])
def test_exact_type_validation_of_durations_rates_costs_and_candidates(value):
    with pytest.raises(ValueError):
        leases.lease_ttl([12., value], .1, 1., 5.)
    with pytest.raises(ValueError):
        leases.lease_ttl(SAMPLE, value, 1., 5.)
    with pytest.raises(ValueError):
        leases.lease_ttl(SAMPLE, .1, value, 5.)
    with pytest.raises(ValueError):
        leases.lease_ttl(SAMPLE, .1, 1., value)
    with pytest.raises(ValueError):
        leases.lease_ttl(SAMPLE, .1, 1., 5., candidates=(60, value))


def test_failure_rate_is_a_probability_and_zero_costs_are_allowed():
    with pytest.raises(ValueError, match=r'\[0,1\]'):
        leases.lease_ttl(SAMPLE, 1.5, 1., 5.)
    with pytest.raises(ValueError):
        leases.lease_ttl(SAMPLE, -.1, 1., 5.)
    assert leases.lease_ttl(SAMPLE, 1, 0, 0)['ttl'] == min(SAMPLE)  # all losses zero: smallest T
    assert leases.lease_ttl(SAMPLE, 0, 1., 5.)['ttl'] == max(SAMPLE)



def test_zero_durations_are_not_feasible_ttls_and_are_excluded_from_the_search():
    # T=0 would win this objective (.5 < 5) but claim/renew reject a zero duration, so it is not searched.
    assert leases.lease_ttl([0, 5], 1, 1, 1) == {'ttl': 5, 'expected_loss': 5., 'searched': [5], 'candidate_losses': {}}
    assert objective([0, 5], 0, 1, 1, 1) == .5
    with pytest.raises(ValueError, match='positive'):
        leases.lease_ttl([0, 0], 1, 1, 1)
    with pytest.raises(ValueError, match='positive'):
        leases.lease_ttl([0], 1, 1, 1, candidates=(0,))
    # A positive candidate rescues an all-zero sample; a zero candidate is still reported (its loss is the
    # degenerate 0: no lead time exceeds 0 and no tick accrues) but never searched.
    rescued = leases.lease_ttl([0], 1, 1, 1, candidates=(60, 0))
    assert rescued['ttl'] == 60 and rescued['searched'] == [60] and rescued['candidate_losses'] == {60: 60., 0: 0.}
